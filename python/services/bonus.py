import logging

from base import ServiceBase
from base import DbConnectorBase

import tools
import rules
import errors

from flask import request
from flask import make_response

import argparse

from getters import UserValue
from getters import ServerValue

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
            f'START TRANSACTION;\n'

            f'UPDATE privilege SET balance = {new_balance} WHERE username = \'{user}\';\n'

            f'INSERT INTO privilege_history(privilege_id, ticket_uid, datetime, balance_diff, operation_type) '
            f'VALUES({privilege_id}, \'{ticket_uid}\', \'{datetime}\', {balance_diff}, \'{operation_type}\');\n'

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

    @ServiceBase.route(path='/api/v1/privilege', methods=['GET', 'POST'])
    def _api_v1_privilege(self):
        method = request.method

        if method == 'GET':
            username = UserValue.get_from(request.headers, 'X-User-Name').value

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
            username = UserValue.get_from(request.headers, 'X-User-Name').value

            user_privilege = self._db_connector.get_user_privilege(username)

            if user_privilege is None:
                self._db_connector.add_user_privilege(username)
                user_privilege = self._db_connector.get_user_privilege(username)

            UserValue.get_from(request.headers, 'Content-Type').rule(rules.json_content)
            body = request.json

            with UserValue.ErrorChain() as error_chain:
                paid_from_balance = UserValue.get_from(body, 'paidFromBalance', error_chain).expected(bool).value
                datetime = UserValue.get_from(body, 'datetime', error_chain).expected(str).value
                ticket_uid = UserValue.get_from(body, 'ticketUid', error_chain).expected(str).value
                balance_diff = UserValue.get_from(body, 'balanceDiff', error_chain).expected(int).rule(rules.greate_equal_zero).value
            
            if not paid_from_balance:
                operation_type = 'FILL_IN_BALANCE'
            else:
                operation_type = 'DEBIT_THE_ACCOUNT'

            self._db_connector.update_user_balance(username, ticket_uid, datetime, balance_diff, operation_type)
            user_privilege = self._db_connector.get_user_privilege(username)

            return make_response(
                {
                    'status': user_privilege['status'],
                    'balance': user_privilege['balance'],
                }
            )
            

        assert False, 'Invalid request method'

    # Helpers
    ####################################################################################################################

    def _register_routes(self):
        self._register_route('_api_v1_privilege')

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
