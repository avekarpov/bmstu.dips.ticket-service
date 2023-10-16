import logging

from base import ServiceBase
import tools

from flask import request
from flask import make_response

import psycopg2


class FlightDbConnector:
    def __init__(self, host, port, database, user, password, sslmode='disable'):
        self._logger = logging.getLogger('FlightDbConnector')

        self._connection = self.create_connection(host, port, database, user, password, sslmode)

    def create_connection(self, host, port, database, user, password, sslmode):
        self._logger.info(f'Create connection on http://{host}:{port} to database: {database} under user: {user}')

        return psycopg2.connect(
            host=host,
            port=port,
            database=database,
            user=user,
            password=password,
            sslmode=sslmode
        )

    def get_flights(self, page_numer, page_size):
        query = tools.simplify_sql_query(
            f'SELECT id, number, datetime, price, from_airport, to_airport FROM('
            f'    SELECT '
            f'        flight.id, '
            f'        number, '
            f'        datetime, '
            f'        price, '
            f'        CONCAT(from_airport.city, \' \' , from_airport.name) as from_airport, '
            f'        CONCAT(to_airport.city, \' \', to_airport.name) as to_airport, '
            f'        ROW_NUMBER() OVER (ORDER BY flight.id) as row '
            f'    FROM flight '
            f'    JOIN airport as from_airport ON flight.from_airport_id = from_airport.id '
            f'    JOIN airport as to_airport ON flight.to_airport_id = to_airport.id'
            f') as flight_with_row '
            f'WHERE {(page_numer - 1) * page_size + 1} <= row AND row < {page_numer * page_size + 1}'
        )

        self._logger.debug(f'Execute query: {query}')
        cursor = self._connection.cursor()
        cursor.execute(query)

        page = cursor.fetchall()
        cursor.close()

        return {
            'number': page_numer,
            'size': page_size,
            'totalElements': len(page),
            'items': [{
                'flightNumber': i[1],
                'fromAirport': i[4],
                'toAirport': i[5],
                'date': i[2],
                'price': i[3]
            } for i in page]
        }


class FlightService(ServiceBase):
    def __init__(self, host, port, db_connector):
        super().__init__('FlightService', host, port, db_connector)

    # API requests handlers
    ####################################################################################################################

    @tools.static_vars(path='/api/v1/flights', methods=['GET'])
    def _handler_flights(self):
        self._logger.debug(
            f'Call handler for path: {self._handler_flights.path} '
            f'with request = {request}'
        )

        method = request.method

        if method == 'GET':
            args = request.args

            page = self._db_connector.get_flights(int(args['page']), int(args['size']))

            return make_response(
                {
                    'page': page['number'],
                    'pageSize': page['size'],
                    'totalElements': len(page['items']),
                    'items': page['items']
                },
                200
            )

        assert False, 'Invalid request method'

    # Helpers
    ####################################################################################################################

    def _register_routes(self):
        self._register_route('_handler_flights')


if __name__ == '__main__':
    tools.set_basic_logging_config()

    service = FlightService(
        'localhost',
        8060,
        FlightDbConnector('localhost', 5432, 'flights', 'program', 'program_password')
    )

    service.run()
