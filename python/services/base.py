from flask import Flask

import logging

import psycopg2


class DbConnectorBase:
    def __init__(self, name, host, port, database, user, password, sslmode):
        self._logger = logging.getLogger(name)

        self._connection = self.create_connection(host, port, database, user, password, sslmode)

    def create_connection(self, host, port, database, user, password, sslmode):
        self._logger.info(
            f'Create connection on \'http://{host}:{port}\' to database \'{database}\' under user \'{user}\''
        )

        return psycopg2.connect(
            host=host,
            port=port,
            database=database,
            user=user,
            password=password,
            sslmode=sslmode
        )


class ServiceBase:
    def __init__(self, name, host, port, db_connector):
        self._service_name = name

        self._host = host
        self._port = port
        self._db_connector = db_connector

        self._flask_app = Flask(self._service_name)

        self._logger = logging.getLogger(self._service_name)

        self._register_routes()

    def run(self, debug=False):
        self._logger.info(f'Run service on http://{self._host}:{self._port}')

        try:
            self._logger.info(f'Run flask app: host: {self._host}, port: {self._port}, debug: {debug}')

            self._flask_app.run(self._host, self._port, debug=debug)

            self._logger.info(f'End flask app run')

        except Exception as exception:
            self._logger.error(f'Failed while run flask app was running, error: {exception}')

            raise

        self._logger.info(f'End service run')

    def _register_routes(self):
        pass

    def _register_route(self, handler):
        handler = getattr(self, handler)

        self._logger.info(f'Register route for \'{handler.path}\' with methods: {handler.methods}')

        self._flask_app.add_url_rule(
            handler.path,
            view_func=handler,
            methods=handler.methods
        )
