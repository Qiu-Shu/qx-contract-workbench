"""Research adapters use real existing MCP notes; no model, search network or client data."""
import asyncio
import hashlib
import re
from pathlib import Path

import pytest
from docx import Document
from business_store import CaseStore
from reader import parse
from check_business_mcp import client, call


METHODS = ['authority_check', 'case_comparison', 'issue_memo', 'lecture_source_pack']
STATES = ['已核验', '部分核验', '未核验', '不适用']
ROOT = Path(__file__).resolve().parents[1]
QUOTE = '纯合成资料：虚构地区甲的演示规范第3条只适用于演示事项。'


def evidence_body(method):
    cards = []
    for index, state in enumerate(STATES):
        cards.append('\n'.join([
            f'sourceId: synthetic-{index}',
            'original: evidence.txt；https://example.invalid/synthetic-source',
            'title: 虚构演示规范；不是实际法律',
            'issuer: 虚构发布机关',
            'article: 第3条',
            'caseNo: 不适用（法规项）',
            'factDate: 2024-03-02',
            'researchDate: 2026-11-12',
            'region: 待判断地区甲；来源标示仅适用演示事项',
            'version: 虚构2024演示版；不代表现行法',
            'effect: 只核对虚构材料字面范围；没有真实法律效力评估',
            'applicability: ' + ('材料明确只适用于演示事项' if index in (0, 3) else '适用事实未知／待核'),
            f'evidence: {QUOTE}',
            f'status: {state}（仅用于测试四态原样保存，不认证法律结论）',
            'unresolved: ' + ('本条仅核材料字面限定，无该范围内缺口；不代表真实法律结论' if index in (0, 3)
                              else '未检出后续状态不等于未发生；全文检索未执行'),
        ]))
    return f'方法：{method}\n法律研究底稿；研究者评估待律师复核。\n' + '\n\n'.join(cards)


def material(cases, cid):
    source = cases.root / 'evidence.txt'
    source.write_text(QUOTE, encoding='utf-8')
    cases.store.register(source.name)
    parse(cases.store, source.name)
    cases.link_materials(cid, [source.name])
    return source, {'path': source.name, 'sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
                    'chunk': 0, 'quote': QUOTE}


def test_four_research_results_save_read_and_export_through_real_mcp(tmp_path):
    async def run():
        seed = CaseStore(tmp_path)
        cid = seed.create('独立虚构研究事项')['id']
        source, citation = material(seed, cid)
        original = source.read_bytes()
        async with client('business_server.py', tmp_path) as legal:
            tools = {tool.name for tool in (await legal.list_tools()).tools}
            reference = (ROOT / 'workspace-seed/legal-library/workbench/legal-research.md').read_text(encoding='utf-8')
            for name in re.findall(r'mcp__qx_legal__([a-z_]+)', reference):
                assert name in tools
            saved = []
            for method in METHODS:
                body = evidence_body(method)
                args = dict(case_id=cid, kind='legal_research_' + method, content=body,
                            source='synthetic-search-record; method commit 59f37f1c8851b8277e24f7a45f4e773bee97bab9',
                            citations=[citation], request_id='save-' + method)
                note = await call(legal, 'record_case_note', **args)
                assert (await call(legal, 'record_case_note', **args))['id'] == note['id']
                parts, start = [], 0
                while True:
                    page = await call(legal, 'read_case_note', case_id=cid, note_id=note['id'], start=start, limit=333)
                    parts.append(page['content'])
                    assert page['review_status'] == 'unverified'
                    assert page['citations'][0]['status'] == 'matched'
                    if page['next_start'] is None:
                        break
                    start = page['next_start']
                assert ''.join(parts) == body
                saved.append(note['id'])
            view = await call(legal, 'get_case', case_id=cid)
            assert len(view['notes']) == 4
            result = await call(legal, 'export_case', case_id=cid, note_ids=saved,
                                audience='internal', filename='合成研究底稿.docx')
            delivered = Path(result['path'])
            if not delivered.is_absolute():
                delivered = tmp_path / delivered
            text = '\n'.join(p.text for p in Document(delivered).paragraphs)
            for method in METHODS:
                assert method in text
            for field in ['original', 'title', 'issuer', 'article', 'caseNo', 'factDate',
                          'researchDate', 'region', 'version', 'effect', 'applicability', 'evidence', 'unresolved']:
                assert field + ':' in text
            for state in STATES:
                assert state in text
            assert source.read_bytes() == original
        # A new server/store must read the same evidence, not just a process cache.
        reopened = CaseStore(tmp_path)
        assert len(reopened.get(cid)['notes']) == 4
        assert reopened.read_note(cid, saved[0], limit=16000)['content'] == evidence_body(METHODS[0])
    asyncio.run(run())


@pytest.mark.parametrize('citation_kind', ['missing', 'fabricated', 'stale'])
def test_research_notes_keep_unknown_and_do_not_certify_missing_fabricated_or_stale_citations(tmp_path, citation_kind):
    cases = CaseStore(tmp_path)
    cid = cases.create('独立虚构证据范围')['id']
    source, citation = material(cases, cid)
    if citation_kind == 'missing':
        citations = [{'url': 'https://example.invalid/unread', 'status': 'matched'}]
    elif citation_kind == 'fabricated':
        citations = [{**citation, 'quote': '原文不存在：已经废止', 'status': 'matched'}]
    else:
        source.write_text('合成新版本，仅验证来源变更。', encoding='utf-8')
        citations = [citation]
    body = 'effect: 未知；没有查到后续变更不等于未变更。\nstatus: 未核验\nunresolved: 状态及适用性待人工核实。'
    note = cases.add_note(cid, 'legal_research_authority_check', body, citations=citations)
    assert note['content'] == body
    assert note['review_status'] == 'unverified' and note['verification'] == 'unverified'
    assert note['citations'][0]['status'] == 'unverified' and note['warnings']


def test_research_records_and_source_versions_remain_case_scoped_and_append_only(tmp_path):
    cases = CaseStore(tmp_path)
    a = cases.create('合成研究甲')['id']
    b = cases.create('合成研究乙')['id']
    source, citation = material(cases, a)
    old = cases.add_note(a, 'legal_research_issue_memo', '初次研究：缺少生效记录，未核验。', citations=[citation])
    with pytest.raises(ValueError):
        cases.read_note(b, old['id'])
    with pytest.raises(ValueError):
        cases.add_note(b, 'legal_research_issue_memo', '跨案引用', citations=[citation])
    corrected = cases.add_note(a, 'legal_research_issue_memo', '用户明确更正：地域为乙，需重新核查。', supersedes=old['id'])
    assert cases.read_note(a, old['id'])['content'] == '初次研究：缺少生效记录，未核验。'
    assert [note['id'] for note in cases.get(a)['notes']] == [corrected['id']]
    assert len(cases.get(a, include_history=True)['notes']) == 2
    source.write_text('新合成版本；旧引用不可复用为当前依据。', encoding='utf-8')
    assert cases.get(a)['materials'][0]['changed']
    assert cases.read_note(a, old['id'])['citations'][0]['sha256'] == citation['sha256']
