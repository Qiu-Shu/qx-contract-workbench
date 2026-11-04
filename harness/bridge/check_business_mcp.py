"""Real stdio and DOCX roundtrip, synthetic workspace only; no model/network."""
import asyncio
from contextlib import asynccontextmanager
import hashlib
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from docx import Document


@asynccontextmanager
async def client(script, workspace):
    params = StdioServerParameters(command=sys.executable,
        args=[str(Path(__file__).with_name(script)), '--workspace', str(workspace)],
        env={'PYTHONIOENCODING': 'utf-8'})
    async with stdio_client(params) as streams:
        async with ClientSession(*streams) as session:
            await session.initialize()
            yield session


async def call(session, tool_name, **kwargs):
    result = await session.call_tool(tool_name, kwargs, read_timeout_seconds=60)
    assert not result.is_error, (tool_name, str(result))
    return result.structured_content or json.loads(next(c.text for c in result.content if c.type == 'text'))


async def run():
    checks = []
    with TemporaryDirectory(prefix='qx-business-check-') as temporary:
        workspace = Path(temporary)
        contract = workspace / '合同.txt'
        contract.write_text('虚构采购合同：总价35000元，预付款5000元，余款验收合格后十日内支付。', encoding='utf-8')
        other = workspace / '其他案件.txt'
        other.write_text('其他虚构案件独有标记乙案919。', encoding='utf-8')
        original = hashlib.sha256(contract.read_bytes()).hexdigest()
        async with client('server.py', workspace) as materials:
            for file in (contract, other):
                await call(materials, 'import_material', path=file.name)
                await call(materials, 'parse_material', path=file.name)
        async with client('business_server.py', workspace) as legal:
            tool_names = [tool.name for tool in (await legal.list_tools()).tools]
            assert {'calculate_calendar_date','get_workflow','create_case','record_case_note',
                    'read_case_material','ground_case_extractions','export_case',
                    'start_hearing','record_hearing_turn'} <= set(tool_names), tool_names
            for name in ('reception', 'contract', 'case', 'hearing'):
                method = await call(legal, 'get_workflow', name=name)
                assert method['output_protocol'] == 'natural_language'
                assert method['method'] and method['sources']
            checks.append('four sourced natural-language methods through MCP')
            created = await call(legal, 'create_case', title='虚构甲案', our_role='买方', request_id='case-a')
            case_id = created.get('id') or created['case']['id']
            retry = await call(legal, 'create_case', title='虚构甲案', our_role='买方', request_id='case-a')
            assert (retry.get('id') or retry['case']['id']) == case_id
            created_b = await call(legal, 'create_case', title='虚构乙案', request_id='case-b')
            case_b = created_b.get('id') or created_b['case']['id']
            await call(legal, 'link_case_materials', case_id=case_id, paths=[contract.name])
            await call(legal, 'link_case_materials', case_id=case_b, paths=[other.name])
            scoped = await call(legal, 'search_case_materials', case_id=case_id, query='乙案919')
            assert not scoped['matches']
            denied = await legal.call_tool('read_case_material', {'case_id': case_id, 'path': other.name})
            assert denied.is_error
            checks.append('case-scoped materials and request retry')
            initial = await call(legal, 'record_case_note', case_id=case_id, kind='consultation',
                content='客户原话：还没付款。', source='合成用户原话', request_id='original')
            note_id = initial.get('id') or initial['note']['id']
            await call(legal, 'record_case_note', case_id=case_id, kind='consultation',
                content='客户明确更正：已付5000元，凭证待补。', source='合成用户更正', supersedes=note_id,
                request_id='correction')
            pair = await call(legal, 'record_reception', case_id=case_id,
                client_reply='您好，请把付款凭证发来，我们结合合同核对付款情况。',
                internal_note='仅律师内部：内部策略标记771，付款状态需凭证核对。', request_id='reception')
            assert pair['recorded'] and pair['client_reply']['id'] != pair['internal_note']['id']
            bad_quote = await call(legal, 'record_case_note', case_id=case_id, kind='contract_review',
                content='这段审查正文保留，引用待核。', citations=[{'path': contract.name, 'quote': '原文不存在的句子'}],
                request_id='unverified')
            assert bad_quote.get('warnings') or bad_quote.get('note', {}).get('warnings'), bad_quote
            history = await call(legal, 'get_case', case_id=case_id, include_history=True)
            assert any(note['id'] == note_id for note in history['notes'])
            current = await call(legal, 'get_case', case_id=case_id)
            assert all(note['id'] != note_id for note in current['notes'])
            checks.append('append-only corrections and unresolved quote keeps prose')
            exported = await call(legal, 'export_case', case_id=case_id, audience='client', filename='客户回复.docx')
            rendered = '\n'.join(p.text for p in Document(exported['path']).paragraphs)
            assert '付款凭证' in rendered and '内部策略标记771' not in rendered
            again = await call(legal, 'export_case', case_id=case_id, audience='client', filename='客户回复.docx')
            assert exported['path'] != again['path']
            denied = await legal.call_tool('export_case', {'case_id': case_id, 'audience': 'client',
                'note_ids': [pair['internal_note']['id']]})
            assert denied.is_error
            checks.append('client-only actual DOCX and non-overwrite')
            hearing = await call(legal, 'start_hearing', case_id=case_id, our_role='plaintiff', focus='虚构余款争议', request_id='hearing')
            hearing_id = hearing.get('id') or hearing.get('hearing_id') or hearing['hearing']['id']
            sequence = [('issues', r) for r in ('moderator', 'plaintiff', 'defendant')]
            sequence += [('evidence', r) for r in ('plaintiff', 'defendant')]
            sequence += [('questions', r) for r in ('moderator', 'plaintiff', 'defendant')]
            sequence += [('debate', r) for r in ('plaintiff', 'defendant')] + [('review', 'reviewer')]
            long_text = '合成长篇发言，事实仍需回查材料。' * 1800
            for index, (stage, role) in enumerate(sequence):
                saved = await call(legal, 'record_hearing_turn', hearing_id=hearing_id, stage=stage, role=role,
                    text=long_text if index == 0 else f'合成发言{index}，付款和验收状态仍需核对。',
                    unresolved='不作为真实证据', request_id=f'turn-{index}')
                if index == 0: long_turn = saved['turn']['id']
            result = await call(legal, 'get_hearing', hearing_id=hearing_id)
            assert result.get('status') == 'completed', result
            checks.append('five stages / eleven turns persisted')
        async with client('business_server.py', workspace) as reopened:
            restored = await call(reopened, 'get_case', case_id=case_id, include_history=True)
            assert any(note['id'] == note_id for note in restored['notes'])
            restored_hearing = await call(reopened, 'get_hearing', hearing_id=hearing_id)
            assert restored_hearing.get('status') == 'completed'
            listed = await call(reopened, 'list_hearings', case_id=case_id)
            assert listed['hearings'][0]['id'] == hearing_id and listed['hearings'][0]['turn_count'] == 11
            restored_text = ''; start = 0
            while True:
                part = await call(reopened, 'read_hearing_turn', hearing_id=hearing_id, turn_id=long_turn, start=start)
                restored_text += part['text']
                if part['next_start'] is None: break
                start = part['next_start']
            assert restored_text == long_text
            snapshot = await call(reopened, 'read_case_material', case_id=case_id, path=contract.name, version=1)
            assert snapshot['historical_snapshot'] and snapshot['sha256'] == original
            checks.append('process restart restores case, hearing IDs, full long turn and material snapshot')
        assert hashlib.sha256(contract.read_bytes()).hexdigest() == original
        checks.append('original material bytes unchanged')
    report = {'status': 'passed', 'transport': 'real MCP stdio', 'model_requests': 0, 'tools': tool_names, 'checks': checks}
    destination = Path(__file__).resolve().parents[1] / 'docs/checks/legal-workflows/mcp.json'
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    asyncio.run(run())
