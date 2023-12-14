import json
import logging

from base import ServiceBase

import requests

from flask import request
from flask import make_response

import tools

import argparse

from time import time

class Gateway(ServiceBase):
    def __init__(
        self, 
        host, port, 
        flight_service_host, flight_service_port,
        ticket_service_host, ticket_service_port,
        bonus_service_host, bonus_service_port,
        valid_error_level, wait_before_retry
    ):
        super().__init__('Gateway', host, port)

        self._flight_service_url = f'http://{flight_service_host}:{flight_service_port}'
        self._ticket_service_url = f'http://{ticket_service_host}:{ticket_service_port}'
        self._bonus_service_url = f'http://{bonus_service_host}:{bonus_service_port}'

        self._valid_error_level = valid_error_level
        self._wait_before_retry = wait_before_retry
        self._error_level = 0
        self._last_error_time = None

        self._flight_queue = []
        self._ticket_queue = []
        self._bonus_queue = []

    ################################################################################################

    @ServiceBase.route(path='/api/v1/flights', methods=['GET', 'POST', 'DELETE'])
    def _flight(self):
        return self._resend(
            self._flight_service_url, f'/api/v1/flights', self._flight_queue, request
        )

    @ServiceBase.route(path='/api/v1/flights/<path:path>', methods=['GET', 'POST', 'DELETE'])
    def _flight_aPath(self, path):
        return self._resend(
            self._flight_service_url, f'/api/v1/flights/{path}', self._flight_queue, request
        )
    
    ################################################################################################
    
    @ServiceBase.route(path='/api/v1/privilege', methods=['GET', 'POST', 'DELETE'])
    def _privilege(self):
        return self._resend(
            self._bonus_service_url, f'/api/v1/privilege', self._ticket_queue, request
        )

    @ServiceBase.route(path='/api/v1/privilege/<path:path>', methods=['GET', 'POST', 'DELETE'])
    def _privilege_aPath(self, path):
        return self._resend(
            self._bonus_service_url, f'/api/v1/privilege/{path}', self._ticket_queue, request
        )   
        
    ################################################################################################

    @ServiceBase.route(path='/api/v1/tickets', methods=['GET', 'POST', 'DELETE'])
    def _tickets(self):
        return self._resend(
            self._ticket_service_url, f'/api/v1/tickets', self._bonus_queue, request
        )

    @ServiceBase.route(path='/api/v1/tickets/<path:path>', methods=['GET', 'POST', 'DELETE'])
    def _tickets_aPath(self, path):
        return self._resend(
            self._ticket_service_url, f'/api/v1/tickets/{path}', self._bonus_queue, request
        )   

    ################################################################################################

    def _resend(self, url, path, queue, request):
        response = None

        try:
            response = self._request(url, path, request)

        except Exception as exception:
            if request.method == 'DELETE':
                class RequestBackup:
                    def __init__(self, path, method, headers, args, data):
                        self.path = path
                        self.method = method
                        self.headers = headers
                        self.args = args
                        self.data = data
            
                queue.append(RequestBackup(path, request.method, request.headers, request.args, request.data))

                return make_response('', 200)

            return make_response('Internal server error', 500)

        try:
            for req in queue:
                self._request(url, req.path, req)
                queue.remove(req)

        finally:
            return response
        

    def _request(self, url, path, request):
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
                f'{url}/{path}',
                headers=request.headers,
                params=request.args,
                data=request.data
            )

            if 500 <= response.status_code <= 599:
                raise RuntimeError('Get 500 code from service')

            self._logger.debug(f'Get response from service, reset error level from {self._error_level} to 0')
            self._error_level = 0

            if tools.is_json_content(response):
                return make_response(response.json(), response.status_code)

            return make_response(response.text, response.status_code)

        except Exception as exception:
            self._logger.error(f'Failed to resend, error: {exception}')

            self._error_level = min(self._error_level, self._valid_error_level) + 1
            self._logger.debug(f'Error level: {self._error_level}')
            self._last_error_time = int(time())

            raise

    # Helpers
    ####################################################################################################################

    def _register_routes(self):
        self._register_route('_flight')
        self._register_route('_flight_aPath')
        self._register_route('_privilege')
        self._register_route('_privilege_aPath')
        self._register_route('_tickets')
        self._register_route('_tickets_aPath')

if __name__ == '__main__':
    tools.set_basic_logging_config()

    parser = argparse.ArgumentParser()
    parser.add_argument('--host', type=str, default='localhost')
    parser.add_argument('--port', type=int, default=8080)
    parser.add_argument('--flight-service-host', type=str, default='localhost')
    parser.add_argument('--flight-service-port', type=int, default=8060)
    parser.add_argument('--bonus-service-host', type=str, default='localhost')
    parser.add_argument('--bonus-service-port', type=int, default=8050)
    parser.add_argument('--ticket-service-host', type=str, default='localhost')
    parser.add_argument('--ticket-service-port', type=int, default=8070)
    parser.add_argument('--valid-error-level', type=int, default=10)
    parser.add_argument('--wait-before-retry', type=int, default=10)
    parser.add_argument('--debug', action='store_true')

    cmd_args = parser.parse_args()

    if cmd_args.debug:
        tools.set_basic_logging_config(level=logging.DEBUG)
    else:
        tools.set_basic_logging_config(level=logging.INFO)

    gateway = Gateway(
        cmd_args.host,
        cmd_args.port,
        cmd_args.flight_service_host,
        cmd_args.flight_service_port,
        cmd_args.ticket_service_host,
        cmd_args.ticket_service_port,
        cmd_args.bonus_service_host,
        cmd_args.bonus_service_port,
        cmd_args.valid_error_level,
        cmd_args.wait_before_retry
    )

    gateway.run(cmd_args.debug)