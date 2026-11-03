import pytest
from business_store import CaseStore
from reader import parse


def material(store, name='evidence.txt', text='虚构材料：付款金额35000元。验收后十日内付款。'):
    path=store.root/name;path.write_text(text,encoding='utf8')
    store.store.register(name);parse(store.store,name)
    return path


def test_cases_notes_and_corrections_survive_reopen_without_merging_names(tmp_path):
    s=CaseStore(tmp_path);a=s.create('同名案件',our_role='买方',request_id='create-1');b=s.create('同名案件')
    assert a['id']!=b['id']
    assert s.create('同名案件',our_role='买方',request_id='create-1')['id']==a['id']
    first=s.add_note(a['id'],'consultation','当事人原话，尚未核实。',request_id='note-1')
    corrected=s.add_note(a['id'],'consultation','更正：付款日期待核。',supersedes=first['id'])
    s.add_note(a['id'],'client_reply','您好，请补充付款凭证。');s.add_note(a['id'],'internal_note','内部底稿，勿向客户转发。')
    assert s.add_note(a['id'],'consultation','当事人原话，尚未核实。',request_id='note-1')['id']==first['id']
    with pytest.raises(ValueError):s.add_note(b['id'],'fact','不可跨案更正',supersedes=first['id'])
    reopened=CaseStore(tmp_path);view=reopened.get(a['id']);assert first['id'] not in [n['id'] for n in view['notes']]
    assert corrected['id'] in [n['id'] for n in view['notes']]
    assert reopened.read_note(a['id'],first['id'])['content']=='当事人原话，尚未核实。'
    assert len(reopened.get(a['id'],include_history=True)['notes'])==4
    assert s.list(query='同名')['total']==2


def test_case_material_membership_search_and_explicit_shared_file(tmp_path):
    s=CaseStore(tmp_path);a=s.create('甲案')['id'];b=s.create('乙案')['id'];material(s)
    s.link_materials(a,['evidence.txt'])
    assert '35000' in s.read_material(a,'evidence.txt')['chunks'][0]['text']
    assert s.search(a,'35000')['matches']
    assert not s.search(b,'35000')['matches']
    with pytest.raises(ValueError):s.read_material(b,'evidence.txt')
    with pytest.raises(ValueError):s.add_note(b,'fact','正文',citations=[{'path':'evidence.txt','quote':'35000'}])
    with pytest.raises(ValueError):s.link_materials(a,['../outside.txt'])
    s.link_materials(b,['evidence.txt']);assert s.read_material(b,'evidence.txt')['chunks']


def test_quote_mismatch_keeps_long_body_and_material_versions(tmp_path):
    s=CaseStore(tmp_path);cid=s.create('版本测试')['id'];path=material(s);s.link_materials(cid,['evidence.txt'])
    old=s.materials(cid)[0];body='完整未核实正文。'*5000
    bad=s.add_note(cid,'fact',body,citations=[{'path':'evidence.txt','quote':'不存在的引文'}])
    assert bad['warnings'] and bad['verification']=='unverified'
    restored='';start=0
    while True:
        part=s.read_note(cid,bad['id'],start=start);restored+=part['content']
        if part['next_start'] is None:break
        start=part['next_start']
    assert restored==body
    good=s.add_note(cid,'timeline','材料称35000元',citations=[{'path':'evidence.txt','quote':'付款金额35000元','chunk':0}])
    assert not good['warnings'] and good['review_status']=='unverified'
    malformed=s.add_note(cid,'fact','字段不规整仍保留正文',citations=[{'path':'evidence.txt','sha256':['bad'],'quote':'35000'}])
    assert malformed['warnings'] and malformed['content']=='字段不规整仍保留正文'
    path.write_text('虚构补件：金额改为36000元。',encoding='utf8')
    assert s.materials(cid)[0]['changed']
    s.link_materials(cid,['evidence.txt']);versions=s.materials(cid,include_history=True)
    assert len(versions)==2 and versions[0]['sha256']==old['sha256']
    assert s.materials(cid)[0]['version']==2
    assert s.read_note(cid,good['id'])['citations'][0]['sha256']==old['sha256']
    path.unlink();assert s.materials(cid)[0]['missing']


def test_request_reuse_with_different_content_fails_and_note_access_is_case_scoped(tmp_path):
    s=CaseStore(tmp_path);a=s.create('甲')['id'];b=s.create('乙')['id'];note=s.add_note(a,'todo','原文',request_id='once')
    with pytest.raises(ValueError):s.add_note(a,'todo','另一原文',request_id='once')
    with pytest.raises(ValueError):s.read_note(b,note['id'])
    assert s.get(a)['notes'][0]['content']=='原文'


def test_case_pages_and_shared_material_version_do_not_read_another_cases_new_binding(tmp_path):
    from store import MaterialStore
    s=CaseStore(MaterialStore(tmp_path));a=s.create('共享文件甲案')['id'];b=s.create('共享文件乙案')['id']
    path=material(s);s.link_materials(a,['evidence.txt']);s.link_materials(b,['evidence.txt']);old=s.materials(b)[0]
    for i in range(7):s.add_note(a,'todo',f'检索任务{i}')
    one=s.get(a,limit=3);two=s.get(a,offset=one['next_offset'],limit=3)
    assert len(one['notes'])==len(two['notes'])==3
    assert not {n['id'] for n in one['notes']}&{n['id'] for n in two['notes']}
    found=s.search(a,'检索',limit=2);again=s.search(a,'检索',offset=found['next_offset'],limit=2)
    assert len(found['matches'])==len(again['matches'])==2
    assert found['matches'][0]['note_id']!=again['matches'][0]['note_id']
    path.write_text('虚构新版本：金额36000元。',encoding='utf8')
    s.link_materials(a,['evidence.txt']);parse(s.store,'evidence.txt')
    assert s.search(a,'36000')['matches']
    assert s.read_material(b,'evidence.txt')['warnings']
    assert not s.search(b,'36000')['matches']
    checked=s.validate_citations(a,[{'path':'evidence.txt','sha256':old['sha256'],'quote':'付款金额35000元'}])
    assert checked['warnings'] and checked['citations'][0]['version']==1
    assert checked['citations'][0]['sha256']==old['sha256']


def test_concurrent_corrections_preserve_one_current_tip_and_return_unsaved_text(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    s = CaseStore(tmp_path); cid = s.create('并发更正')['id']
    original = s.add_note(cid, 'timeline', '客户最初陈述')
    def correct(text):
        return CaseStore(tmp_path).add_note(cid, 'timeline', text, supersedes=original['id'])
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(correct, ['客户更正一', '客户更正二']))
    current = s.get(cid)['notes']
    assert len(current) == 1
    rejected = next(item for item in results if item.get('recorded') is False)
    assert rejected['current_note_ids'] == [current[0]['id']]
    assert rejected['unsaved_note']['content'] in {'客户更正一', '客户更正二'}
    assert len(s.get(cid, include_history=True)['notes']) == 2
    assert s.read_note(cid, original['id'])['content'] == '客户最初陈述'


def test_correction_cannot_reclassify_internal_notes_as_client_reply(tmp_path):
    s = CaseStore(tmp_path); cid = s.create('分类保护')['id']
    original = s.add_note(cid, 'internal_note', '内部策略')
    result = s.add_note(cid, 'client_reply', '内部策略', supersedes=original['id'])
    assert result['recorded'] is False and result['reason'] == 'correction_kind_mismatch'
    assert result['unsaved_note']['content'] == '内部策略'
    assert s.get(cid)['notes'][0]['kind'] == 'internal_note'


def test_reception_pair_is_atomic_idempotent_and_survives_restart(tmp_path):
    import sqlite3
    from concurrent.futures import ThreadPoolExecutor
    s = CaseStore(tmp_path); cid = s.create('接待')['id']
    with ThreadPoolExecutor(max_workers=2) as pool:
        pairs = list(pool.map(lambda _: s.record_reception(cid, '您好，请补充合同。', '内部分析771', request_id='pair'), range(2)))
    assert pairs[0]['reception_id'] == pairs[1]['reception_id']
    reopened = CaseStore(tmp_path)
    assert {n['kind'] for n in reopened.get(cid)['notes']} == {'client_reply', 'internal_note'}
    assert reopened.get(cid)['total_notes'] == 2
    with pytest.raises(ValueError, match='请求编号'):
        s.record_reception(cid, '不同回复', '内部分析771', request_id='pair')
    with s.db() as db:
        db.execute("CREATE TRIGGER simulate_disk_failure BEFORE INSERT ON legal_notes WHEN NEW.kind='internal_note' BEGIN SELECT RAISE(ABORT, 'synthetic disk failure'); END")
    with pytest.raises(sqlite3.IntegrityError):
        s.record_reception(cid, '不应孤立保存的回复', '第二段内部分析', request_id='failed')
    assert reopened.get(cid)['total_notes'] == 2


def test_linked_parsed_material_snapshot_survives_replacement_and_reopen(tmp_path):
    s = CaseStore(tmp_path); cid = s.create('附件历史')['id']
    path = material(s, text='旧附件全文35000元。' * 3000)
    s.link_materials(cid, [path.name]); old = s.materials(cid)[0]
    path.write_text('新附件全文36000元。', encoding='utf8')
    s.store.register(path.name); parse(s.store, path.name); s.link_materials(cid, [path.name])
    reopened = CaseStore(tmp_path); chunks = []; start = 0
    while True:
        part = reopened.read_material(cid, path.name, start=start, limit=1, version=1)
        assert part['sha256'] == old['sha256'] and part['historical_snapshot'] is True
        chunks.extend(item['text'] for item in part['chunks'])
        if part['next_start'] is None: break
        start = part['next_start']
    assert ''.join(chunks) == '旧附件全文35000元。' * 3000
    assert '新附件' in reopened.read_material(cid, path.name)['chunks'][0]['text']
    path.unlink()
    assert reopened.read_material(cid, path.name, version=1)['chunks']


def test_material_replacement_during_read_cannot_return_unlinked_new_text(tmp_path, monkeypatch):
    s = CaseStore(tmp_path); cid = s.create('读取途中更新')['id']
    path = material(s); s.link_materials(cid, [path.name])
    original_read = s.store.read
    def replace_then_read(*args, **kwargs):
        path.write_text('不属于已关联版本的新正文887', encoding='utf8')
        s.store.register(path.name); parse(s.store, path.name)
        return original_read(*args, **kwargs)
    monkeypatch.setattr(s.store, 'read', replace_then_read)
    result = s.read_material(cid, path.name)
    assert result['chunks'] == [] and result['warnings']


def test_material_replacement_during_search_cannot_return_unlinked_new_text(tmp_path, monkeypatch):
    s = CaseStore(tmp_path); cid = s.create('检索途中更新')['id']
    path = material(s); s.link_materials(cid, [path.name])
    original_search = s.store.search
    def replace_then_search(*args, **kwargs):
        path.write_text('不属于已关联版本的新正文887', encoding='utf8')
        s.store.register(path.name); parse(s.store, path.name)
        return original_search(*args, **kwargs)
    monkeypatch.setattr(s.store, 'search', replace_then_search)
    result = s.search(cid, '887')
    assert result['matches'] == [] and result['warnings']
