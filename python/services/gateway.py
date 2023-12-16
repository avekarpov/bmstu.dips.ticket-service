import json
import logging

from base import ServiceBase

import requests

from flask import request as flask_request
from flask import make_response

import tools

import argparse

from time import time

class ServiceInfo:
    def __init__(self, url):
        self.url = url
        self.queue = []
        self.error_level = 0
        self.last_error_time = 0

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

        self._flight_service_info = ServiceInfo(f'http://{flight_service_host}:{flight_service_port}')
        self._ticket_service_info = ServiceInfo(f'http://{ticket_service_host}:{ticket_service_port}')
        self._bonus_service_info = ServiceInfo(f'http://{bonus_service_host}:{bonus_service_port}')

        self._valid_error_level = valid_error_level
        self._wait_before_retry = wait_before_retry

    ################################################################################################

    @ServiceBase.route(path='/api/v1/flights', methods=['GET', 'POST', 'DELETE'])
    def _flight(self):
        return self._resend(
            self._flight_service_info, f'/api/v1/flights', flask_request
        )

    @ServiceBase.route(path='/api/v1/flights/<path:path>', methods=['GET', 'POST', 'DELETE'])
    def _flight_aPath(self, path):
        return self._resend(
            self._flight_service_info, f'/api/v1/flights/{path}', flask_request
        )
    
    ################################################################################################
    
    @ServiceBase.route(path='/api/v1/privilege', methods=['GET', 'POST', 'DELETE'])
    def _privilege(self):
        return self._resend(
            self._bonus_service_info, f'/api/v1/privilege', flask_request
        )

    @ServiceBase.route(path='/api/v1/privilege/<path:path>', methods=['GET', 'POST', 'DELETE'])
    def _privilege_aPath(self, path):
        return self._resend(
            self._bonus_service_info, f'/api/v1/privilege/{path}', flask_request
        )   
        
    ################################################################################################

    @ServiceBase.route(path='/api/v1/tickets', methods=['GET', 'POST', 'DELETE'])
    def _tickets(self):
        return self._resend(
            self._ticket_service_info, f'/api/v1/tickets', flask_request
        )

    @ServiceBase.route(path='/api/v1/tickets/<path:path>', methods=['GET', 'POST', 'DELETE'])
    def _tickets_aPath(self, path):
        return self._resend(
            self._ticket_service_info, f'/api/v1/tickets/{path}', flask_request
        )   
    
    @ServiceBase.route(path='/api/v1/me', methods=['GET', 'POST', 'DELETE'])
    def _me(self):
        return self._resend(
            self._ticket_service_info, f'/api/v1/me', flask_request
        )

    ################################################################################################

    def _resend(self, service_info, path, request):
        try:
            if len(service_info.queue) != 0:
                if not self._check_service_health(service_info):
                    raise RuntimeError('Service is unavailable')

                for request_backup in service_info.queue:
                    self._request(service_info, request_backup.path, request_backup)
                    service_info.queue.remove(request_backup)

            return self._request(service_info, path, request)
        
        except Exception:
            if request.method == 'DELETE':
                class RequestBackup:
                    def __init__(self, path, method, headers, args, data):
                        self.path = path
                        self.method = method
                        self.headers = headers
                        self.args = args
                        self.data = data

                service_info.queue.append(RequestBackup(path, request.method, request.headers, request.args, request.data))

                return make_response('', 200)
            
        return make_response('Internal server error', 500)
        

    def _request(self, service_info, path, request):
        method = request.method

        try:
            self._logger.debug('Send request')
            response = requests.request(
                method,
                f'{service_info.url}{path}',
                headers=request.headers,
                params=request.args,
                data=request.data
            )

            # if 500 <= response.status_code <= 599:
            #     raise RuntimeError('Get 500 code from service')

            self._logger.debug(f'Got response from service, reset error level from {service_info.error_level} to 0')
            service_info.error_level = 0

            if tools.is_json_content(response):
                return make_response(response.json(), response.status_code)

            return make_response(response.text, response.status_code)

        except Exception as exception:
            self._logger.error(f'Failed to send request, error: {exception}')

            service_info.error_level = min(service_info.error_level, self._valid_error_level) + 1
            self._logger.debug(f'Error level: {service_info.error_level}')
            self._last_error_time = int(time())

            raise

    def _check_service_health(self, service_info: ServiceInfo):
        if service_info.error_level > self._valid_error_level:
            if service_info.last_error_time + self._wait_before_retry > int(time()):
                self._logger.error(
                    f'Failed to send request to {service_info.url}, '
                    f'error level {service_info.error_level} > {self._valid_error_level} '
                    f'for {self._wait_before_retry}s from last {service_info.last_error_time}'
                )
            
                return False
         
        try:
            requests.request('GET', f'{service_info.url}/manage/health')

        except:
            return False
        
        return True

    # Helpers
    ####################################################################################################################

    def _register_routes(self):
        self._register_route('_flight')
        self._register_route('_flight_aPath')
        self._register_route('_privilege')
        self._register_route('_privilege_aPath')
        self._register_route('_tickets')
        self._register_route('_tickets_aPath')
        self._register_route('_me')

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