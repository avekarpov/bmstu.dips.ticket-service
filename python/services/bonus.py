import logging

from base import ServiceBase
from base import DbConnectorBase

import tools

from flask import request
from flask import make_response

import argparse


class BonusDbConnector(DbConnectorBase):
    def __init__(self, host, port, database, user, password, sslmode='disable'):
        super().__init__('BounsDbConnector', host, port, database, user, password, sslmode)

    def get_user_privilege(self, user):
        query = tools.simplify_sql_query(
            f'SELECT id, username, status, balance FROM privilege WHERE username = \'{user}\''
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
            'username': row[1],
            'status': row[2],
            'balance': row[3]
        }
    
    def add_user_privilege(self, user):
        query = tools.simplify_sql_query(
            f'INSERT INTO privilege(username, status, balance) VALUES(\'{user}\', \'BRONZE\', 0)'
        )

        self._logger.debug(f'Execute query: {query}')
        cursor = self._connection.cursor()
        cursor.execute(query)

        cursor.close()
        self._connection.commit()

    def update_user_balance(self, user, ticket_uid, datetime, balance_diff, operation_type):
        user_privilege = self.get_user_privilege(user)

        assert user_privilege is not None
        privilege_id = user_privilege['id']

        if operation_type == 'DEBIT_THE_ACCOUNT':
            new_balance = user_privilege['balance'] - balance_diff
        else:
            new_balance = user_privilege['balance'] + balance_diff

        query = tools.simplify_sql_query(
            f'START TRANSACTION;'

            f'UPDATE privilege SET balance = {new_balance} WHERE username = \'{user}\';'

            f'INSERT INTO privilege_history(privilege_id, ticket_uid, datetime, balance_diff, operation_type) '
            f'VALUES({privilege_id}, \'{ticket_uid}\', \'{datetime}\', {balance_diff}, \'{operation_type}\');'

            f'COMMIT TRANSACTION;'
        )

        self._logger.debug(f'Execute query: {query}')
        cursor = self._connection.cursor()
        cursor.execute(query)

        cursor.close()
        self._connection.commit()
    
    def get_privilege_history(self, privilege_id):
        query = tools.simplify_sql_query(
            f'SELECT id, privilege_id, ticket_uid, datetime, balance_diff, operation_type FROM privilege_history '
            f'WHERE privilege_id = {privilege_id}'
        )

        self._logger.debug(f'Execute query: {query}')
        cursor = self._connection.cursor()
        cursor.execute(query)

        table = cursor.fetchall()
        cursor.close()

        if table is None:
            return None
        
        return [
            {
                'id': row[0],
                'privilege_id': row[1],
                'ticket_uid': row[2],
                'datetime': row[3],
                'balance_diff': row[4],
                'operation_type': row[5]
            }
            for row in table
        ]

class BonusService(ServiceBase):
    def __init__(self, host, port, db_connector):
        super().__init__('BounsService', host, port, db_connector)

    # API requests handlers
    ####################################################################################################################

    @tools.static_vars(path='/api/v1/privilege', methods=['GET', 'POST'])
    def _handler_privilge(self):
        self._logger.debug(
            f'Call handler for path: {self._handler_privilge.path} '
            f'with request = {request}'
        )

        method = request.method

        if method == 'GET':
            username = request.headers['X-User-Name']

            user_privilege = self._db_connector.get_user_privilege(username)

            if user_privilege is None:
                self._db_connector.add_user_privilege(username)
                user_privilege = self._db_connector.get_user_privilege(username)
            
            user_privilege_history = self._db_connector.get_privilege_history(user_privilege['id'])

            return make_response(
                {
                    'balance': user_privilege['balance'],
                    'status': user_privilege['status'],
                    'history': [
                        {
                            'date': i['datetime'],
                            'ticketUid': i['ticket_uid'],
                            'balanceDiff': i['balance_diff'],
                            'operationType': i['operation_type']
                        }
                        for i in user_privilege_history
                    ]
                },
                200
            )
        
        if method == 'POST':
            '''
            Request:
                headers:
                    Content-Type: application/json
                    X-User-Name: username

                body:
                    {
                        "paidFromBalance": true,
                        "datetime": "2023-10-04 15:00:00",
                        "ticketUid": "08d83d92-485c-4dd9-b8e6-2e0ec83d7f08",
                        "balanceDiff": 100
                    }
            '''

            if request.headers['Content-Type'] != 'application/json':
                return make_response({'message': 'invalid header \'Content-Type\''}, 400)

            username = request.headers['X-User-Name']

            user_privilege = self._db_connector.get_user_privilege(username)

            if user_privilege is None:
                self._db_connector.add_user_privilege(username)
                user_privilege = self._db_connector.get_user_privilege(username)

            body = request.json

            errors = []

            paid_from_balance = tools.get_required_arg_from(body, 'paidFromBalance')[0]
            if paid_from_balance is None:
                errors.append({'paidFromBalance': 'expected paidFromBalance'})
            elif not tools.is_valid(paid_from_balance, bool):
                errors.append({'paidFromBalance': 'invalid paidFromBalance'})

            datetime = tools.get_required_arg_from(body, 'datetime')[0]
            if datetime is None:
                errors.append({'paidFromBalance': 'expected paidFromBalance'})
            elif not tools.is_valid(datetime, str):
                errors.append({'paidFromBalance': 'invalid paidFromBalance'})
            # TODO: check is valid datetime

            ticket_uid = tools.get_required_arg_from(body, 'ticketUid')[0]
            if ticket_uid is None:
                errors.append({'paidFromBalance': 'expected ticketUid'})
            elif not tools.is_valid(ticket_uid, str):
                errors.append({'paidFromBalance': 'invalid ticketUid'})

            balance_diff = tools.get_required_arg_from(body, 'balanceDiff')[0]
            if balance_diff is None:
                errors.append({'paidFromBalance': 'expected balanceDiff'})
            elif not tools.is_valid(balance_diff, int):
                errors.append({'paidFromBalance': 'invalid balanceDiff'})

            if len(errors) != 0:
                return make_response({'message': 'invalid request', 'errors': errors}, 400)
            
            if not paid_from_balance:
                operation_type = 'FILL_IN_BALANCE'
            else:
                operation_type = 'DEBIT_THE_ACCOUNT'

            self._db_connector.update_user_balance(username, ticket_uid, datetime, balance_diff, operation_type)

            return make_response()
            

        assert False, 'Invalid request method'

    # Helpers
    ####################################################################################################################

    def _register_routes(self):
        self._register_route('_handler_privilge')

if __name__ == '__main__':
    tools.set_basic_logging_config()

    parser = argparse.ArgumentParser()
    parser.add_argument('--host', type=str, default='localhost')
    parser.add_argument('--port', type=int, default=8050)
    parser.add_argument('--db-host', type=str, default='localhost')
    parser.add_argument('--db-port', type=int, default=5432)
    parser.add_argument('--db', type=str, default='flights')
    parser.add_argument('--db-user', type=str, required=True)
    parser.add_argument('--db-password', type=str, required=True)
    parser.add_argument('--db-sslmode', type=str, default='disable')
    parser.add_argument('--debug', action='store_true')

    cmd_args = parser.parse_args()

    if cmd_args.debug:
        tools.set_basic_logging_config(level=logging.DEBUG)
    else:
        tools.set_basic_logging_config(level=logging.INFO)

    service = BonusService(
        cmd_args.host,
        cmd_args.port,
        BonusDbConnector(
            cmd_args.db_host,
            cmd_args.db_port,
            cmd_args.db,
            cmd_args.db_user,
            cmd_args.db_password,
            cmd_args.db_sslmode
        )
    )

    service.run(cmd_args.debug)
