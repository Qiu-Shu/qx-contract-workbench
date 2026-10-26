from copy import deepcopy
from uuid import uuid4
import pytest
from sqlalchemy import text
from test_assistant_routes import native, chat, sign_in
from test_followup_worksheet import setup, item, body, commit
from test_evidence_worksheet import material, request as evidence_request
from test_reception_worksheet import save


def test_stale_current_fact_open_warns_and_complete_denied(chat):
    client, db, _ = chat
    h = sign_in(client); base, url, ev, fact = setup(client, h)
    save(client, h, base + '/reception-worksheet', consultation='新的陈述已改变，旧引用仍留作历史。')
    row = item(client.get(url).json(), fact)
    commit(client, h, url, [row])
    v = client.get(url).json()
    assert v['attention'] and v['items'][0]['status'] == 'open'
    row.update(status='completed', result='试图凭旧陈述完成')
    assert client.post(url + '/commits', headers=h, json=body(v, [row])).status_code == 409
    row.update(id=str(uuid4()))
    assert client.post(url + '/commits', headers=h, json=body(v, [row])).status_code == 409


def test_new_item_cannot_reuse_old_version_even_if_fact_still_current(chat):
    client, db, _ = chat
    h = sign_in(client); base, url, ev, fact = setup(client, h)
    row = item(client.get(url).json(), fact)
    commit(client, h, url, [row])
    other = deepcopy(fact); other['id'] = str(uuid4()); other['content'] = '另一个独立陈述'
    assert client.post(ev + '/commits', headers=h, json=evidence_request(client.get(ev).json(), [fact, other])).status_code == 200
    v = client.get(url).json()
    assert v['attention'] == []
    fresh = {**row, 'id': str(uuid4())}
    assert client.post(url + '/commits', headers=h, json=body(v, [row, fresh])).status_code == 409


def test_completed_fact_correction_old_result_only_is_denied(chat):
    client, db, _ = chat
    h = sign_in(client); base, url, ev, fact = setup(client, h)
    row = item(client.get(url).json(), fact, status='completed', result='旧处理结果')
    commit(client, h, url, [row])
    fact['content'] = '客户现更正金额不明'
    assert client.post(ev + '/commits', headers=h, json=evidence_request(client.get(ev).json(), [fact])).status_code == 200
    v = client.get(url).json(); assert v['attention']
    row['result'] = '仅改处理结果并未更新引用'
    assert client.post(url + '/commits', headers=h, json=body(v, [row])).status_code == 409
    row['status'] = 'open'; commit(client, h, url, [row])
    v = client.get(url).json(); assert v['attention']
    row['status'] = 'completed'
    assert client.post(url + '/commits', headers=h, json=body(v, [row])).status_code == 409


def test_adding_valid_looking_title_only_actual_http_is_422(chat):
    client, db, _ = chat
    h = sign_in(client); base, url, ev, fact = setup(client, h)
    row = item(client.get(url).json(), fact, reason='', impact='')
    response = client.post(url + '/commits', headers=h, json=body(client.get(url).json(), [row]))
    assert response.status_code == 422
    assert client.get(url).json()['revision'] == 0


def test_new_material_reference_cannot_reuse_unselected_old_material(chat):
    client, db, _ = chat
    h = sign_in(client); base, url, ev, fact = setup(client, h)
    a, p, _ = material(client, h, base, db)
    row = item(client.get(url).json(), fact, facts=[], materials=[{'attachment_id':a['id'],'original_sha256':a['sha256'],'parse_revision':p['revision']}])
    commit(client, h, url, [row])
    scope = client.get(base).json()['scope']
    assert client.put(base + '/materials', headers=h, json={'request_id':str(uuid4()),'expected_scope':scope,'items':[]}).status_code == 200
    v = client.get(url).json(); assert v['attention']
    commit(client, h, url, [row])
    extra = {**row, 'id':str(uuid4())}
    assert client.post(url + '/commits', headers=h, json=body(client.get(url).json(), [row,extra])).status_code == 409


@pytest.mark.parametrize('which', ['profile','evidence','future_fact'])
def test_rehashed_asof_history_rejects_later_source_version(chat, which):
    import json
    from cn_contract.assistant.followup_records import history
    from cn_contract.record_codec import encode, sha
    client, db, _ = chat
    h = sign_in(client); base, url, ev, fact = setup(client, h)
    row = item(client.get(url).json(), fact)
    commit(client, h, url, [row])
    save(client, h, base + '/reception-worksheet', consultation='改后的陈述')
    fact['content'] = '晚于跟进保存的事实更正'
    assert client.post(ev + '/commits', headers=h, json=evidence_request(client.get(ev).json(), [fact])).status_code == 200
    v = client.get(url).json()
    with db.session() as session:
        assert len(history(session, v['scope']['conversation_id'])) == 1
        record = session.execute(text('SELECT * FROM assistant_followup_revisions')).mappings().one()
        request = json.loads(record['request_json']); snap = json.loads(record['snapshot_json'])
        if which == 'profile':
            request['expected_profile_revision'] = v['profile_revision']; snap['profile_revision'] = v['profile_revision']
        elif which == 'evidence':
            request['expected_evidence_revision'] = v['evidence_revision']; snap['evidence_revision'] = v['evidence_revision']
        else:
            request['items'][0]['facts'][0]['evidence_revision'] = v['evidence_revision']; snap['items'] = request['items']
        session.execute(text('DROP TRIGGER immutable_assistant_followup_revisions_update'))
        session.execute(text('UPDATE assistant_followup_revisions SET request_json=:r,request_sha256=:rh,snapshot_json=:s,snapshot_sha256=:sh'), {'r':encode(request),'rh':sha(request),'s':encode(snap),'sh':sha(snap)})
        with pytest.raises(ValueError):
            history(session, v['scope']['conversation_id'])
