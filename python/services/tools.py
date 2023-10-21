from flask import request

import logging


def static_vars(**kwargs):
    def decorate(func):
        for k in kwargs:
            setattr(func, k, kwargs[k])
        return func

    return decorate


def simplify_sql_query(query):
    return " ".join(query.split())


def set_basic_logging_config(level=logging.DEBUG):
    logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=level)


def get_required_arg_from(source, name):
    if name not in source.keys():
        return None, f'"{name}" is required arg', 400

    return source[name], None, None


def get_required_arg(name):
    return get_required_arg_from(request.args, name)


def is_valid(value, expected_type):
    return type(value) is expected_type
