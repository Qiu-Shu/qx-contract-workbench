"""Frozen predecessors, additive native upgrade, and evidence tamper rejection."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from uuid import uuid4

import pytest
from sqlalchemy import text

from cn_contract import storage_schema, schema_migrations
from cn_contract.assistant.evidence_records import validate_evidence_records
from cn_contract.record_codec import encode, sha
from cn_contract.web import local_server
from test_assistant_routes import native, chat, sign_in
from test_evidence_worksheet import begin, statement, request

FROZEN=json.loads((Path(__file__).parents[1]/'fixtures/evidence_schema_predecessors.json').read_text())


def digest(value):return sha256(json.dumps(value,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()


@pytest.mark.parametrize('item',FROZEN)
def test_all_38_predecessor_structures_are_unchanged(item):
    assert digest(storage_schema.schema_rows(item['version'],native=item['native']))==item['schema_sha256']
    assert digest(storage_schema.normalized_schema(item['version'],native=item['native']))==item['normalized_sha256']


@pytest.mark.parametrize('native_mode',[False,True])
def test_exact_v19_additive_upgrade_keeps_old_records(native_mode):
    db=sqlite3.connect(':memory:')
    # Real previous objects, including immutable triggers, then generic upgrader.
    for kind,name,table,sql in storage_schema.schema_rows('weixin-generation-dispatch-v1',native=native_mode):
        if kind=='table':db.execute(sql)
    for kind,name,table,sql in storage_schema.schema_rows('weixin-generation-dispatch-v1',native=native_mode):
        if kind!='table' and sql:db.execute(sql)
    db.commit()
    assert schema_migrations.upgrade_database(db)=='assistant-evidence-v1'
    assert storage_schema.identify_schema(schema_migrations.database_rows(db),native=native_mode)=='assistant-evidence-v1'
    assert db.execute('SELECT count(*) FROM assistant_evidence_revisions').fetchone()==(0,)
    assert db.execute('PRAGMA foreign_key_check').fetchall()==[]


def test_native_upgrade_keeps_workspace_identity_and_prior_profile(native):
    from fastapi.testclient import TestClient
    app,root=native;db=app.state.database
    with TestClient(app) as client:
        h=sign_in(client);base,url=begin(client,h);fact=statement(client,h,base,url)
        original=client.get(base+'/reception-worksheet').json()['fields']
    # Simulate the precise predecessor, not a partially initialized fixture.
    db.engine.dispose()
    with sqlite3.connect(root/'workbench.db') as raw:
        for action in ('update','delete'):raw.execute('DROP TRIGGER immutable_assistant_evidence_revisions_'+action)
        raw.execute('DROP TABLE assistant_evidence_revisions')
        rows=raw.execute('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name').fetchall()
    marker=json.loads((root/'workspace.json').read_text());marker['schema_sha256']=digest(rows)
    (root/'workspace.json').write_text(json.dumps(marker))
    recovered=local_server.build_local_app(root,data_parent=root.parent.parent)
    try:
        assert list((root/'upgrade-backups').glob('assistant-evidence-*/before.db'))
        assert json.loads((root/'workspace.json').read_text())['workspace_id']==marker['workspace_id']
        with TestClient(recovered) as client:
            sign_in(client)
            assert client.get(base+'/reception-worksheet').json()['fields']==original
    finally:recovered.state.database.engine.dispose()


@pytest.mark.parametrize('fault',['quote','actor','scope','request'])
def test_rehashed_semantic_tamper_is_rejected(chat,fault):
    client,database,_=chat;h=sign_in(client);base,url=begin(client,h);row=statement(client,h,base,url)
    body=request(client.get(url).json(),[row]);assert client.post(url+'/commits',headers=h,json=body).status_code==200
    with database.session() as db:
        validate_evidence_records(db)
        db.execute(text('DROP TRIGGER immutable_assistant_evidence_revisions_update'))
        saved=db.execute(text('SELECT * FROM assistant_evidence_revisions')).mappings().one()
        req=json.loads(saved['request_json']);snap=json.loads(saved['snapshot_json'])
        if fault=='quote':
            req['rows'][0]['source']['quote']='伪造';req['rows'][0]['source']['end']=2;snap['rows']=req['rows']
        if fault=='scope':req['expected_scope']['materials_revision']=1;snap['scope']=req['expected_scope']
        if fault=='request':req['base_revision']=8
        if fault=='actor':db.execute(text("UPDATE assistant_evidence_revisions SET actor_id=(SELECT id FROM users WHERE id<>:owner LIMIT 1)"),{'owner':saved['actor_id']})
        db.execute(text('UPDATE assistant_evidence_revisions SET request_json=:r,request_sha256=:rs,snapshot_json=:s,snapshot_sha256=:ss'),{'r':encode(req),'rs':sha(req),'s':encode(snap),'ss':sha(snap)})
        with pytest.raises(ValueError) as error:validate_evidence_records(db)
        assert error.value is not None


def test_evidence_update_delete_are_immutable_and_failed_cas_keeps_history(chat):
    from sqlalchemy.exc import IntegrityError
    client,database,_=chat;h=sign_in(client);base,url=begin(client,h);row=statement(client,h,base,url)
    body=request(client.get(url).json(),[row]);assert client.post(url+'/commits',headers=h,json=body).status_code==200
    for sql in ['UPDATE assistant_evidence_revisions SET revision=2','DELETE FROM assistant_evidence_revisions']:
        with pytest.raises(IntegrityError):
            with database.session() as db:db.execute(text(sql))
    stale=deepcopy(body);stale['request_id']=str(uuid4());stale['rows']=[]
    assert client.post(url+'/commits',headers=h,json=stale).status_code==409
    assert client.get(url).json()['rows']==[row]
    assert client.get(url+'/revisions/1').json()['rows']==[row]


def test_removing_current_fact_keeps_history_and_backup_validator(chat):
    client,database,_=chat;h=sign_in(client);base,url=begin(client,h);row=statement(client,h,base,url)
    body=request(client.get(url).json(),[row]);assert client.post(url+'/commits',headers=h,json=body).status_code==200
    assert client.post(url+'/commits',headers=h,json=request(client.get(url).json(),[])).status_code==200
    assert client.get(url).json()['rows']==[]
    assert client.get(url+'/revisions/1').json()['rows']==[row]
    with database.session() as db:validate_evidence_records(db)
