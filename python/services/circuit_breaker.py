import logging

from base import ServiceBase

import requests

from flask import request
from flask import make_response

import tools

import argparse

from time import time

class CircuitBreaker(ServiceBase):
    def __init__(self, host, port, service_host, service_port, valid_error_level, wait_before_retry):
        super().__init__('CircuitBreaker', host, port)

        self._service_url = f'http://{service_host}:{service_port}'

        self._valid_error_level = valid_error_level
        self._wait_before_retry = wait_before_retry
        self._error_level = 0
        self._last_error_time = None

    @ServiceBase.route(path='/', methods=['GET', 'POST', 'DELETE'])
    def _any(self):
        return self._resend()

    def run(self):
        super().run()        

    @ServiceBase.route(path='/<path:path>', methods=['GET', 'POST', 'DELETE'])
    def _any_aPath(self, path):
        return self._resend(f'{path}')
        
    def _resend(self, path=None):
        method = request.method

        if self._error_level > self._valid_error_level:
            if self._last_error_time + self._wait_before_retry > int(time()):
                self._logger.error(
                    f'Failed to resend, '
                    f'error level {self._error_level} > {self._valid_error_level} '
                    f'for {self._wait_before_retry}s from last {self._last_error_time}'
                )

                return make_response('Internal server error', 500)

        try:
            self._logger.debug('Send request')
            response = requests.request(
                method,
                f'{self._service_url}/{path}',
                headers=request.headers,
                params=request.args,
                data=request.data,
            )

            self._logger.debug(f'Get response from service, reset error level from {self._error_level} to 0')
            self._error_level = 0

            return make_response(response.text, response.status_code)

        except Exception as exception:
            self._logger.error(f'Failed to resend, error: {exception}')

            self._error_level = min(self._error_level, self._valid_error_level) + 1
            self._logger.debug(f'Error level: {self._error_level}')
            self._last_error_time = int(time())

            return make_response('Internal server error', 500)
            
            
    # Helpers
    ####################################################################################################################

    def _register_routes(self):
        self._register_route('_any')
        self._register_route('_any_aPath')

if __name__ == '__main__':
    tools.set_basic_logging_config()

    parser = argparse.ArgumentParser()
    parser.add_argument('--host', type=str, default='localhost')
    parser.add_argument('--port', type=int, default=8080)
    parser.add_argument('--service-host', type=str, required=True)
    parser.add_argument('--service-port', type=int, required=True)
    parser.add_argument('--valid-error-level', type=int, default=10)
    parser.add_argument('--wait-before-retry', type=int, default=10)
    parser.add_argument('--debug', action='store_true')

    cmd_args = parser.parse_args()

    if cmd_args.debug:
        tools.set_basic_logging_config(level=logging.DEBUG)
    else:
        tools.set_basic_logging_config(level=logging.INFO)

    circuit_breaker = CircuitBreaker(
        cmd_args.host,
        cmd_args.port,
        cmd_args.service_host,
        cmd_args.service_port,
        cmd_args.valid_error_level,
        cmd_args.wait_before_retry
    )

    circuit_breaker.run(cmd_args.debug)