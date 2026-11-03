"""Actual Word exports from synthetic temporary cases; no model or live workspace."""
from docx import Document
import pytest

import business_server as api
from business_store import CaseStore
from reader import parse


@pytest.fixture
def cases(tmp_path, monkeypatch):
    store = CaseStore(tmp_path)
    monkeypatch.setattr(api, 'cases', store)
    monkeypatch.setattr(api.material_server, 'store', store.store)
    return store


def word_text(result):
    return '\n'.join(paragraph.text for paragraph in Document(result['path']).paragraphs)


def test_internal_export_distinguishes_old_citation_from_current_material(cases):
    case_id = cases.create('虚构版本案例')['id']
    path = cases.root / 'evidence.txt'
    path.write_text('虚构原件：金额35000元。', encoding='utf-8')
    cases.store.register(path.name)
    parse(cases.store, path.name)
    cases.link_materials(case_id, [path.name])
    note = cases.add_note(case_id, 'fact', '仅记录原件陈述。', citations=[
        {'path': path.name, 'quote': '金额35000元', 'chunk': 0}])
    citation = note['citations'][0]

    path.write_text('虚构新版：金额36000元。', encoding='utf-8')
    cases.store.register(path.name)
    parse(cases.store, path.name)
    cases.link_materials(case_id, [path.name])
    current = cases.materials(case_id)[0]
    text = word_text(api.export_case(case_id, 'versions.docx', note_ids=[note['id']]))
    old_section, current_section = text.split('当前关联材料版本', 1)

    assert (citation['sha256'] in old_section and current['sha256'] not in old_section
            and '引用版本：1' in old_section and '片段：0' in old_section
            and '记录时原文匹配：matched' in old_section and '金额35000元' in old_section
            and current['sha256'] in current_section and '版本 2' in current_section)


def test_client_export_contains_only_latest_client_body(cases):
    case_id = cases.create('虚构客户案例')['id']
    cases.add_note(case_id, 'internal_note', '内部策略标记771。')
    cases.add_note(case_id, 'client_reply', '旧回复标记772。')
    cases.add_note(case_id, 'client_reply', '您好，请补充付款凭证。', source='内部来源标记773')
    text = word_text(api.export_case(case_id, 'client.docx', audience='client'))

    assert ('您好，请补充付款凭证。' in text
            and all(marker not in text for marker in ('771', '772', '773', '当前关联材料版本')))


def test_client_export_rejects_selected_internal_note(cases):
    from mcp.server.mcpserver.exceptions import ToolError
    cid = cases.create('虚构客户导出隔离')['id']
    internal = cases.add_note(cid, 'internal_note', '内部策略不可导出')
    client = cases.add_note(cid, 'client_reply', '您好，请补材料。')
    with pytest.raises(ToolError, match='客户版只能'):
        api.export_case(cid, audience='client', note_ids=[client['id'], internal['id']])


def test_export_uses_one_current_record_snapshot_despite_correction(cases, monkeypatch):
    cid = cases.create('导出快照')['id']
    first = cases.add_note(cid, 'timeline', '旧日期记录')
    for number in range(105):
        cases.add_note(cid, 'todo', f'任务{number}唯一标记')
    original_get = cases.get
    def correct_between_pages(*args, **kwargs):
        page = original_get(*args, **kwargs)
        if page['next_offset'] is not None:
            cases.add_note(cid, 'timeline', '新日期记录', supersedes=first['id'])
        return page
    monkeypatch.setattr(cases, 'get', correct_between_pages)
    text = word_text(api.export_case(cid, filename='snapshot.docx'))
    assert all(f'任务{number}唯一标记' in text for number in range(105))
    assert ('旧日期记录' in text) != ('新日期记录' in text)
