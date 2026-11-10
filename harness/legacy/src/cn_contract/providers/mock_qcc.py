"""Original static synthetic schema; no QCC compatibility claim or I/O."""
from ..domain import ToolCatalog, ToolDefinition


def catalog(variant='base'):
    input_schema = {'type': 'object', 'properties': {'name': {'type': 'string', 'minLength': 1, 'maxLength': 80}},
                    'required': ['name'], 'additionalProperties': False}
    output_schema = {'type': 'object', 'properties': {'synthetic': {'const': True}, 'state': {'type': 'string'},
        'trace': {'type': 'string'}, 'pages_complete': {'type': 'boolean'}},
        'required': ['synthetic', 'state', 'trace', 'pages_complete'], 'additionalProperties': False}
    if variant == 'output_changed':
        output_schema['description'] = 'Independent synthetic schema revision'
    elif variant == 'input_changed':
        input_schema['description'] = 'Independent synthetic schema revision'
    elif variant != 'base':
        raise ValueError('unknown static variant')
    return ToolCatalog(provider='synthetic_mock_qcc', tools=(ToolDefinition(name='synthetic_identity',
        input_schema_snapshot=input_schema, output_schema_snapshot=output_schema),))


class MockQccTransport:
    async def invoke(self, tool_name, arguments, correlation_id):
        if tool_name != 'synthetic_identity':
            raise ValueError('unknown static tool')
        return {'synthetic': True, 'state': 'unknown', 'trace': str(correlation_id), 'pages_complete': False}
