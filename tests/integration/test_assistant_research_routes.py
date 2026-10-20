"""Synthetic HTTP research, source snapshots and recovery remain local."""
from contextlib import contextmanager
from pathlib import Path
import time
from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest

from cn_contract import domain as d
from cn_contract.ops import workspace_backup
from cn_contract.security import provision_user
from cn_contract.web import local_server
from tests.helpers.legacy_assistant_backup import PASSPHRASE
from tests.integration.test_assistant_generation import world
from tests.integration.test_assistant_generation_routes import signin, count
from tests.integration.test_assistant_library_adapter import library


@contextmanager
def boot(world, tmp_path, library_root=None, root=None):
    root = root or Path(world[0].engine.url.database).parent
    app = local_server.build_local_app(root, data_parent=tmp_path, library_root=library_root)
    with TestClient(app) as client:
        headers = signin(client)
        yield SimpleNamespace(client=client, headers=headers, app=app, root=root,
            database=app.state.database, url='/api/assistant/conversations/'+str(world[2].scope.conversation_id),
            body=world[3].model_copy(update={'content':'租赁','requested_skill':'legal_research'}).model_dump(mode='json'))


def settle(http, request_id):
    deadline = time.monotonic()+5
    while time.monotonic() < deadline:
        response = http.client.get(http.url+'/researches/by-request/'+str(request_id))
        assert response.status_code == 200, response.text
        view = response.json()
        if view and view['run']['state'] not in {'queued','retrieving'}:
            return view
        time.sleep(.01)
    pytest.fail('synthetic local research did not settle')


def submit(http):
    response = http.client.post(http.url+'/researches', headers=http.headers, json=http.body)
    assert response.status_code == 202, response.text
    return settle(http, http.body['request_id'])


def test_local_no_model_replay_history_and_citation_do_not_reread_library(world, tmp_path, library, monkeypatch):
    from cn_contract.assistant.tools.library import LegalLibraryAdapter
    with boot(world,tmp_path,library[0]) as http:
        result = submit(http)
        assert result['run']['state'] == 'completed' and len(result['receipts']) == 1
        receipt = result['receipts'][0]
        assert receipt['result']['result']['page']['state'] == 'ready'
        saved_id = receipt['result']['citation_ids'][0]
        def forbidden(*args, **kwargs):
            pytest.fail('history must not re-read library')
        monkeypatch.setattr(LegalLibraryAdapter,'search',forbidden)
        monkeypatch.setattr(LegalLibraryAdapter,'read_original',forbidden)
        replay = http.client.post(http.url+'/researches', headers=http.headers, json=http.body)
        assert replay.status_code == 202 and replay.json() == result
        history = http.client.get(http.url+'/research-history', params={'message_id':result['run']['message_id']})
        assert history.status_code == 200 and history.json()['items'][0]['research'] == result
        citation = http.client.get('/api/assistant/library-citations/'+saved_id)
        assert citation.status_code == 200 and citation.json()['citation']['support_status'] == 'unverified'
        assert count(http.database,'assistant_handler_receipts') == 1
        for name in ('assistant_model_attempts','assistant_model_outputs','assistant_judge_attempts'):
            assert count(http.database,name) == 0
        assert world[-1].provider.calls == []


@pytest.mark.parametrize('change,status', [('csrf',403),('origin',403),('skill',422),('long',422),('path',422)])
def test_invalid_research_never_registers_or_runs(world,tmp_path,change,status):
    with boot(world,tmp_path) as http:
        body, headers = dict(http.body), dict(http.headers)
        if change == 'csrf': headers = {}
        elif change == 'origin': headers['Origin'] = 'https://fiction.invalid'
        elif change == 'skill': body['requested_skill'] = None
        elif change == 'long': body['content'] = '租'*201
        else: body['root'] = 'F:/fiction-forbidden'
        result = http.client.post(http.url+'/researches',headers=headers,json=body)
        assert result.status_code == status, result.text
        assert count(http.database,'assistant_runs') == 0


def test_not_configured_is_persisted_and_unknown_request_is_read_only(world,tmp_path):
    with boot(world,tmp_path) as http:
        missing = http.client.get(http.url+'/researches/by-request/'+str(uuid4()))
        assert missing.status_code == 200 and missing.json() is None
        assert count(http.database,'assistant_runs') == 0
        result = submit(http)
        assert result['receipts'][0]['result']['result']['page']['state'] == 'not_configured'
        assert http.client.get(http.url+'/generation-capability').json()['state'] == 'unconfigured'


def test_cross_user_history_and_citation_are_denied(world,tmp_path,library):
    with boot(world,tmp_path,library[0]) as http:
        result = submit(http)
        saved = result['receipts'][0]['result']['citation_ids'][0]
        with http.database.session() as db:
            provision_user('other','fixture123',{d.Role.HANDLING_LAWYER},db,local_workbench_password=True)
        signin(http.client,'other')
        for url in (http.url+'/researches/by-request/'+http.body['request_id'],
                    http.url+'/research-history?message_id='+result['run']['message_id'],
                    '/api/assistant/library-citations/'+saved):
            response = http.client.get(url)
            assert response.status_code == 403 and response.json()['code'] == 'CROSS_MATTER_DENIED'


def test_history_rejects_unknown_foreign_or_unbounded_message_queries(world,tmp_path):
    with boot(world,tmp_path) as http:
        for query in ({'message_id':str(uuid4())}, {'message_id':[str(uuid4())]*51}, {'root':'anything'}):
            response = http.client.get(http.url+'/research-history',params=query)
            assert response.status_code in {403,422}
        assert count(http.database,'assistant_runs') == 0


def test_legacy_saved_message_never_becomes_executable(world,tmp_path):
    with boot(world,tmp_path) as http:
        old = http.client.post(http.url+'/messages',headers=http.headers,json=http.body)
        assert old.status_code in {200,201,202},old.text
        response = http.client.post(http.url+'/researches',headers=http.headers,json=http.body)
        assert response.status_code == 409
        assert count(http.database,'assistant_handler_receipts') == 0


def test_qxbak_recovery_reads_saved_snapshot_without_live_library(world,tmp_path,library,monkeypatch):
    from cn_contract.assistant.tools.library import LegalLibraryAdapter
    with boot(world,tmp_path,library[0]) as http:
        result = submit(http)
        source_root = http.root
        saved = result['receipts'][0]['result']['citation_ids'][0]
    archive = tmp_path/'research.qxbak'
    workspace_backup.create_workspace_backup(source_root,archive,PASSPHRASE,data_parent=tmp_path)
    restored = workspace_backup.restore_workspace_backup(archive,tmp_path/'restore',PASSPHRASE)
    def forbidden(*args,**kwargs):
        pytest.fail('recovery cannot call current library')
    monkeypatch.setattr(LegalLibraryAdapter,'search',forbidden)
    monkeypatch.setattr(LegalLibraryAdapter,'read_original',forbidden)
    with boot(world,tmp_path,root=Path(restored['restored_root'])) as http:
        response = http.client.get('/api/assistant/library-citations/'+saved)
        assert response.status_code == 200,response.text
        history = http.client.get(http.url+'/research-history',params={'message_id':result['run']['message_id']})
        assert history.status_code == 200,history.text
        assert http.client.get(http.url+'/researches/by-request/'+http.body['request_id']).status_code == 200
        assert http.client.post(http.url+'/researches',headers=http.headers,json=http.body).status_code == 409
        assert not http.app.state.assistant_generation_tasks.accepting
