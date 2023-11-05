def grater_zero(value):
    if value <= 0:
        return 'Value must be greater zero'

    return None

def greate_equal_zero(value):
    if value < 0:
        return 'Value must be qual or greater zero'

    return None

def json_content(content_type):
    if content_type != 'application/json':
        return 'Invalid header: \'Content-Type\''
    
    return None