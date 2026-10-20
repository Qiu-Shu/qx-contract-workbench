"""Independent checks of the archive identity fix, preserving the original reproduction."""
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path.cwd()/'tests'/'integration'))
from uuid import uuid4
import pytest
from sqlalchemy import text
from cn_contract import domain as d
from cn_contract.assistant import research, service, library_handlers
from cn_contract.assistant.tools.library import LegalLibraryAdapter
from cn_contract.config import canonical_json
from cn_contract.ops import backup, workspace_backup
from cn_contract.persistence import Database
from cn_contract.security import authenticate, login
from tests.integration.test_assistant_generation import world
from tests.integration.test_assistant_attachment_backup import corrupt
from tests.helpers.legacy_assistant_backup import PASSPHRASE


def completed(world):
    database,actor,view,request,_=world
    request=request.model_copy(update={'content':'合成租赁','requested_skill':'legal_research'})
    with database.session() as db:
        accepted=research.enqueue_research(actor,view.scope.conversation_id,request,db)
    return research.execute_research(actor,accepted.run.id,database,LegalLibraryAdapter(None))


@pytest.mark.parametrize('field', ['call_id','request_sha256'])
def test_archive_rejects_corrupt_research_identity_at_create_and_restore(world,tmp_path,monkeypatch,field):
    database,_,_,_,_=world
    result=completed(world)
    root=Path(database.engine.url.database).parent
    with database.session() as db:
        raw=db.scalar(text("SELECT payload_json FROM assistant_run_events WHERE run_id=:run AND event_type='research.accepted'"),{'run':str(result.run.id)})
    payload=json.loads(raw);payload[field]=str(uuid4()) if field=='call_id' else 'f'*64
    corrupt(database,'assistant_run_events',"UPDATE assistant_run_events SET payload_json=? WHERE run_id=? AND event_type='research.accepted'",(canonical_json(payload),str(result.run.id)))
    archive=tmp_path/'bad.qxbak'
    with pytest.raises(ValueError,match='ASSISTANT_LIBRARY_INTEGRITY'):
        workspace_backup.create_workspace_backup(root,archive,PASSPHRASE,data_parent=tmp_path)
    assert not archive.exists()
    # Only bypass CREATE's validator to form authenticated corrupt test input.
    # RESTORE runs with every original validator intact.
    with monkeypatch.context() as patch:
        patch.setattr(workspace_backup,'_file_references',lambda db: [])
        workspace_backup.create_workspace_backup(root,archive,PASSPHRASE,data_parent=tmp_path)
    destination=tmp_path/'rejected'
    original=(root/'workbench.db').read_bytes();encrypted=archive.read_bytes()
    with pytest.raises(ValueError,match='ASSISTANT_LIBRARY_INTEGRITY'):
        workspace_backup.restore_workspace_backup(archive,destination,PASSPHRASE)
    assert not destination.exists() or not any(destination.iterdir())
    assert original==(root/'workbench.db').read_bytes() and encrypted==archive.read_bytes()


def test_revoked_session_newer_draft_and_offline_library_preserve_history(world,tmp_path,monkeypatch):
    database,actor,_,_,_=world
    result=completed(world);root=Path(database.engine.url.database).parent
    with database.session() as db:
        current=service.read_conversation(actor,result.run.scope.conversation_id,db)
        service.save_draft(actor,current.scope.conversation_id,d.AssistantDraftInput(expected_scope=current.scope,expected_composer_revision=current.composer_revision,content='后来新增的合成草稿'),db)
        db.execute(text('UPDATE sessions SET revoked=1'))
    def no_io(*args,**kwargs): pytest.fail('history/archive must not call external library')
    monkeypatch.setattr(LegalLibraryAdapter,'search',no_io)
    monkeypatch.setattr(LegalLibraryAdapter,'read_original',no_io)
    archive=tmp_path/'valid.qxbak'
    workspace_backup.create_workspace_backup(root,archive,PASSPHRASE,data_parent=tmp_path)
    target=Path(workspace_backup.restore_workspace_backup(archive,tmp_path/'restored',PASSPHRASE)['restored_root'])
    recovered=Database('sqlite:///'+str(target/'workbench.db'),target/'protected',database.settings,initialize_schema=False)
    backup._mark_storage_flags(recovered)
    try:
        with recovered.session() as db:
            token,_=login('lawyer','fixture123',db)
            fresh=authenticate(token,db)
            assert research.read_research(fresh,result.run.id,db)==result
    finally: recovered.engine.dispose()


def test_legacy_b1_keyword_is_data_even_when_it_equals_workflow_marker(world):
    database,actor,view,request,_=world
    request=request.model_copy(update={'content':'local-research-v1','requested_skill':'legal_research'})
    with database.session() as db:
        run=service.save_message(actor,view.scope.conversation_id,request,db)
    call=library_handlers.begin_library_call(actor,run.id,uuid4(),d.LibraryHandlerRequest(tool='legal_library.search',query=d.AssistantLibraryQuery(text=request.content)),database)
    library_handlers.execute_library_handler(actor,run.id,call.event_seq,database,LegalLibraryAdapter(None))
    with database.session() as db:
        assert backup._file_references(db)==[]
        current=service._owned(actor,view.scope.conversation_id,db)
        assert research.read_history(actor,current,d.MainGenerationHistoryQuery(message_ids=(run.message_id,)),db).items==()
