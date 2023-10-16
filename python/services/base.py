from flask import Flask

import logging


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
            self._logger.info(f'Run flask app with: host: {self._host}, port: {self._port}, debug: {debug}')

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
