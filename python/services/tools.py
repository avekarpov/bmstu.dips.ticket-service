import logging


def simplify_sql_query(query):
    return " ".join(query.split())


def set_basic_logging_config(level=logging.DEBUG):
    logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=level)

def is_json_content(request):
    return request.headers['Content-Type'] == 'application/json'