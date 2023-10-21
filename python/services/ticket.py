import logging

import psycopg2

from base import ServiceBase
from base import DbConnectorBase

import tools

from flask import request
from flask import make_response

import argparse

import requests

import uuid


class TicketDbConnector(DbConnectorBase):
    def __init__(self, host, port, database, user, password, sslmode='disable'):
        super().__init__('TicketDbConnector', host, port, database, user, password, sslmode)

    def get_user_tickets(self, user):
        query = tools.simplify_sql_query(
            f'SELECT id, uid, username, flight_number, price, status FROM ticket WHERE username = \'{user}\''
        )

        self._logger.debug(f'Execute query: {query}')
        cursor = self._connection.cursor()
        cursor.execute(query)

        table = cursor.fetchall()
        cursor.close()

        return [
            {
                'id': row[0],
                'uid': row[1],
                'username': row[2],
                'flight_number': row[3],
                'price': row[4],
                'status': row[5]
            }
            for row in table
        ]

    def get_ticket_by_uid(self, uid):
        query = tools.simplify_sql_query(
            f'SELECT id, uid, username, flight_number, price, status FROM ticket WHERE uid = \'{uid}\''
        )

        self._logger.debug(f'Execute query: {query}')
        cursor = self._connection.cursor()
        cursor.execute(query)

        row = cursor.fetchone()
        cursor.close()

        if row is None:
            return None

        return {
            'id': row[0],
            'uid': row[1],
            'username': row[2],
            'flight_number': row[3],
            'price': row[4],
            'status': row[5]
        }

    def add_user_ticket(self, user, uid, flight_number, price, status):
        query = tools.simplify_sql_query(
            f'INSERT INTO ticket(username, uid, flight_number, price, status)'
            f'VALUES (\'{user}\', \'{uid}\', \'{flight_number}\', {price}, \'{status}\')'
        )

        self._logger.debug(f'Execute query: {query}')
        cursor = self._connection.cursor()
        cursor.execute(query)

        cursor.close()


class TicketService(ServiceBase):
    def __init__(self, host, port, db_connector, flight_service_host, flight_service_port):
        super().__init__('TicketService', host, port, db_connector)

        self._flight_service_url = f'http://{flight_service_host}:{flight_service_port}'

    # API requests handlers
    ####################################################################################################################

    @tools.static_vars(path='/api/v1/tickets', methods=['GET', 'POST'])
    def _handler_tickets(self):
        self._logger.debug(
            f'Call handler for path: {self._handler_tickets.path} '
            f'with request = {request}'
        )

        method = request.method

        if method == 'GET':
            table = self._db_connector.get_user_tickets(request.headers['X-User-Name'])

            url_base = f'{self._flight_service_url}/api/v1/flights'

            response = []
            for row in table:
                flight = requests.request('GET', f'{url_base}/{row["flight_number"]}').json()

                response.append(
                    {
                        'ticketUid': row['uid'],
                        'fromAirport': flight['fromAirport'],
                        'toAirport': flight['toAirport'],
                        'date': flight['date'],
                        'price': row['price'],
                        'status': row['status']
                    }
                )

            return make_response(response, 200)

        if method == 'POST':
            if request.headers['Content-Type'] != 'application/json':
                return make_response({'message': 'invalid header \'Content-Type\''})

            body = request.json

            errors = []

            flight_number = tools.get_required_arg_from(body, 'flightNumber')[0]
            if flight_number is None:
                errors.append({'flightNumber': 'expected flight number'})
            elif not tools.is_valid(flight_number, str):
                errors.append({'flightNumber': 'invalid flight number'})

            price = tools.get_required_arg_from(body, 'price')[0]
            if price is None:
                errors.append({'price': 'expected price'})
            elif not tools.is_valid(price, int) or price < 0:
                errors.append({'price': 'invalid price'})

            paid_from_balance = tools.get_required_arg_from(body, 'paidFromBalance')[0]
            if paid_from_balance is None:
                errors.append({'paidFromBalance': 'expected paid from balance'})
            elif not tools.is_valid(paid_from_balance, bool):
                errors.append({'paidFromBalance': 'invalid paid from balance'})

            if len(errors) != 0:
                return make_response({'message': 'invalid request', 'errors': errors}, 400)

            flight = requests.request('GET', f'{self._flight_service_url}/api/v1/flights/{flight_number}').json()

            if 'message' in flight.keys():
                return make_response(flight, 400)

            uid = uuid.uuid4()

            # TODO: request to bonus service

            self._db_connector.add_user_ticket(request.headers['X-User-Name'], uid, flight_number, price, 'PAID')

            return make_response(
                {
                    'ticketUid': uid,
                    'flightNumber': flight_number,
                    'fromAirport': flight['fromAirport'],
                    'toAirport': flight['toAirport'],
                    'data': flight['date'],
                    'price': price,
                    'paidByMoney': None,
                    'paidByBonuses': None,
                    'status': 'PAID',
                    'privilege': None
                },
                200
            )

        assert False, 'Invalid request method'

    @tools.static_vars(path='/api/v1/tickets/<string:uid>', methods=['GET'])
    def _handler_ticket_by_uid(self, uid):
        self._logger.debug(
            f'Call handler for path: {self._handler_ticket_by_uid.path} '
            f'with request = {request}'
        )

        method = request.method

        if method == 'GET':
            ticket = self._db_connector.get_ticket_by_uid(uid)

            if ticket is None:
                return make_response({'message': 'non existent ticket'}, 404)

            url_base = f'{self._flight_service_url}/api/v1/flights'

            flight = requests.request('GET', f'{url_base}/{ticket["flight_number"]}').json()

            return make_response(
                {
                    'ticketUid': ticket['uid'],
                    'fromAirport': flight['fromAirport'],
                    'toAirport': flight['toAirport'],
                    'date': flight['date'],
                    'price': ticket['price'],
                    'status': ticket['status']
                },
                200
            )

        assert False, 'Invalid request method'

    # Helpers
    ####################################################################################################################

    def _register_routes(self):
        self._register_route('_handler_tickets')
        self._register_route('_handler_ticket_by_uid')


if __name__ == '__main__':
    tools.set_basic_logging_config()

    parser = argparse.ArgumentParser()
    parser.add_argument('--host', type=str, default='localhost')
    parser.add_argument('--port', type=int, default=8070)
    parser.add_argument('--flight-service-host', type=str, default='localhost')
    parser.add_argument('--flight-service-port', type=int, default=8060)
    parser.add_argument('--db-host', type=str, default='localhost')
    parser.add_argument('--db-port', type=int, default=5432)
    parser.add_argument('--db', type=str, default='tickets')
    parser.add_argument('--db-user', type=str, required=True)
    parser.add_argument('--db-password', type=str, required=True)
    parser.add_argument('--db-sslmode', type=str, default='disable')
    parser.add_argument('--debug', action='store_true')

    cmd_args = parser.parse_args()

    if cmd_args.debug:
        tools.set_basic_logging_config(level=logging.DEBUG)
    else:
        tools.set_basic_logging_config(level=logging.INFO)

    service = TicketService(
        cmd_args.host,
        cmd_args.port,
        TicketDbConnector(
            cmd_args.db_host,
            cmd_args.db_port,
            cmd_args.db,
            cmd_args.db_user,
            cmd_args.db_password,
            cmd_args.db_sslmode
        ),
        cmd_args.flight_service_host,
        cmd_args.flight_service_port
    )

    service.run(cmd_args.debug)
