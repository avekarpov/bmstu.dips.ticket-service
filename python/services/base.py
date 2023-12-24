from flask import Flask
from flask import make_response

import requests

import logging

import psycopg2

from errors import UserError
from getters import ServerValue, UserValue
import rules

from datetime import datetime
import time

from jose import jwt

class DbConnectorBase:
    def __init__(self, name, host, port, database, user, password, sslmode):
        self._logger = logging.getLogger(name)

        self._connection = self.create_connection(host, port, database, user, password, sslmode)

    def create_connection(self, host, port, database, user, password, sslmode, retry_number=10, reconnecting_delay_s=1):
        self._logger.info(
            f'Create connection on \'http://{host}:{port}\' to database \'{database}\' under user \'{user}\''
        )

        for i in range(retry_number):
            try:
                return psycopg2.connect(
                    host=host,
                    port=port,
                    database=database,
                    user=user,
                    password=password,
                    sslmode=sslmode
                )
            except Exception as exception:
                error = exception.args[0].replace('\n', ' ').strip()
                if error.find('Connection refused'):
                    logging.debug(f'Got error {error}, reconnecting in {reconnecting_delay_s} seconds')
                    time.sleep(reconnecting_delay_s)
        
        raise RuntimeError('Connection to database failed')
class ServiceBase:
    def __init__(self, name, host, port, db_connector:DbConnectorBase=None):
        self._service_name = name

        self._host = host
        self._port = port
        self._db_connector = db_connector

        self._flask_app = Flask(f'{self._service_name} flask')

        self._logger = logging.getLogger(self._service_name)

        self._register_manage_health()
        self._register_routes()

    def run(self, debug=False):
        self._logger.info(f'Run service on http://{self._host}:{self._port}')

        try:
            self._logger.info(f'Run flask app: host: {self._host}, port: {self._port}, debug: {debug}')

            self._flask_app.run(self._host, self._port, debug=debug)

            self._logger.info(f'End flask app run')

        except Exception as exception:
            self._logger.error(f'Failed while run flask app, error: {exception}')

            raise
        except:
            self._logger.error(f'Failed while run flask app, with unknown error')

            raise
            

        self._logger.info(f'End service run')

    def _manage_health(self):
        return make_response()
    
    def _register_manage_health(self):
        path = '/manage/health'
        methods = ['GET']

        self._logger.info(f'Register route for \'{path}\' with methods: {methods}')

        self._flask_app.add_url_rule(
            path,
            view_func=self._manage_health,
            methods=methods
        )

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

    @staticmethod
    def get_current_datetime():
        return datetime.today().strftime('%Y-%m-%d %H:%M:%S')

    @staticmethod
    def route(path, methods):
        def decorate(func):
            def wrapper(self, *args, **kwargs):
                self._logger.debug(f'Call handler for path: {path}')

                try:
                    return func(self=self, *args, **kwargs)
                
                except UserError as error:
                    error.message.update({'error': 'bad request'})
                    return make_response(error.message, error.code)

            setattr(wrapper, 'path', path)
            setattr(wrapper, 'methods', methods)

            wrapper.__name__ = func.__name__
            return wrapper

        return decorate


class AuthorizeServiceInfo:
    def __init__(self, api_key, secret_key, url):
        self.api_key = api_key
        self.secret_key = secret_key
        self.url = f'https://{url}'


class ServerBaseWithAuth0(ServiceBase):
    def __init__(
        self,
        authorize_service_api_key, 
        authorize_service_secret_key, 
        authorize_service_url,
        *args,
        **kwargs
    ):
        super().__init__(*args, **kwargs)

        self._authorize_service_info = AuthorizeServiceInfo(
            authorize_service_api_key, 
            authorize_service_secret_key, 
            authorize_service_url
        )
    
    def _get_user_token(self, request):
        token = UserValue.get_from(request.headers, 'Authorization', code=401).value
        token = token.split()

        if len(token) > 1:
            token = token[1]
        else:
            token = token[0]

        self._validate_token(token)

        return token

    def _get_username(self, token):
        response = requests.request(
            'GET',
            f'{self._authorize_service_info.url}/userinfo',
            headers={
                'Authorization': f'Bearer {token}'
            }
        )

        # ServerValue.get_from(response.headers, 'Content-Type').rule(rules.json_content)
        return ServerValue.get_from(response.json(), 'nickname').value

    def _validate_token(self, token):
        rsa_key = None

        try:
            jwks = requests.request('GET', f'{self._authorize_service_info.url}/.well-known/jwks.json').json()
            unverified_header = jwt.get_unverified_header(token)

            for key in jwks['keys']:
                if key['kid'] == unverified_header['kid']:
                    rsa_key = {
                        "kty": key["kty"],
                        "kid": key["kid"],
                        "use": key["use"],
                        "n": key["n"],
                        "e": key["e"]
                    }

                    break

        except Exception as error:
            raise UserError(
                    {'message': f'invalid header, {error}'}, 401
                )

        if rsa_key is not None:
            try:
                return jwt.decode(
                    token,
                    rsa_key,
                    algorithms=['RS256'],
                    audience=f'{self._authorize_service_info.url}/api/v2/',
                    issuer=f'{self._authorize_service_info.url}/'
                )

            except jwt.ExpiredSignatureError:
                raise UserError(
                    {'message': 'token expired'}, 401
                )
            except Exception as error:
                raise UserError(
                    {'message': f'invalid header, {error}'}, 401
                )
        
        raise UserError(
            {'message': 'invalid header'}, 401
        )