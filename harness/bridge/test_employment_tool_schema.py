"""The live MCP schema exposes mandatory findings and nested money bindings."""
import asyncio
from check_business_mcp import client


def test_live_tool_schema_describes_finding_and_money_requirements(tmp_path):
    async def run():
        async with client('business_server.py',tmp_path) as legal:
            schema=next(t.input_schema for t in (await legal.list_tools()).tools if t.name=='save_employment_review')
            def resolve(value):
                if '$ref' in value:return schema['$defs'][value['$ref'].split('/')[-1]]
                return value
            finding=resolve(schema['properties']['findings']['items'])
            assert set(finding['required']) >= {'fact','basis','source','risk','action'}
            parameters=resolve(finding['properties']['parameters']['anyOf'][0])
            money=resolve(parameters['properties']['contract_pay']['anyOf'][0])
            assert set(money['required'])=={'amount','citation'}
            citation=resolve(money['properties']['citation'])
            assert set(citation['required'])=={'path','quote','sha256','chunk'}
            result=await legal.call_tool('save_employment_review',dict(case_id='invalid',stage='hiring',
                findings=[dict(fact='test',basis='test',risk='test',action='test')]))
            assert result.is_error
            assert 'source' in str(result.content)
    asyncio.run(run())
