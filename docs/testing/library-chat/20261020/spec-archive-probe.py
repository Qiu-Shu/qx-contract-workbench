"""Independent archive probe: mutate only synthetic research.accepted payload."""
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path.cwd()/'tests'/'integration'))
from uuid import uuid4

import pytest
from sqlalchemy import text

from cn_contract.assistant import research, service
from cn_contract.assistant.tools.library import LegalLibraryAdapter
from cn_contract.config import canonical_json
from cn_contract.ops import backup, workspace_backup
from cn_contract.persistence import Database
from cn_contract.security import ServiceError, authenticate, login
from tests.integration.test_assistant_generation import world
from tests.integration.test_assistant_attachment_backup import corrupt
from tests.helpers.legacy_assistant_backup import PASSPHRASE


def test_changed_acceptance_call_passes_archive_validation_but_breaks_restored_history(world,tmp_path):
    database,actor,view,request,_=world
    root=Path(database.engine.url.database).parent
    request=request.model_copy(update={'content':'合成租赁','requested_skill':'legal_research'})
    with database.session() as db:
        registered=research.enqueue_research(actor,view.scope.conversation_id,request,db)
    completed=research.execute_research(actor,registered.run.id,database,LegalLibraryAdapter(None))
    assert completed.run.state=='completed' and len(completed.receipts)==1
    with database.session() as db:
        accepted=json.loads(db.scalar(text("SELECT payload_json FROM assistant_run_events WHERE run_id=:run AND event_type='research.accepted'"),{'run':str(registered.run.id)}))
    accepted['call_id']=str(uuid4())
    corrupt(database,'assistant_run_events',
        "UPDATE assistant_run_events SET payload_json=? WHERE run_id=? AND event_type='research.accepted'",
        (canonical_json(accepted),str(registered.run.id)))
    with database.session() as db:
        assert backup._file_references(db)==[]
        with pytest.raises(ServiceError) as before:
            research.read_research(actor,registered.run.id,db)
        assert before.value.code=='LIBRARY_RECORD_INVALID'
    archive=tmp_path/'invalid-research-acceptance.qxbak'
    workspace_backup.create_workspace_backup(root,archive,PASSPHRASE,data_parent=tmp_path)
    restored=workspace_backup.restore_workspace_backup(archive,tmp_path/'restored',PASSPHRASE)
    target=Path(restored['restored_root'])
    recovered=Database('sqlite:///'+str(target/'workbench.db'),target/'protected',database.settings,initialize_schema=False)
    backup._mark_storage_flags(recovered)
    try:
        with recovered.session() as db:
            token,_=login('lawyer','fixture123',db)
            current=authenticate(token,db)
            assert backup._file_references(db)==[]
            with pytest.raises(ServiceError) as after:
                research.find_research(current,view.scope.conversation_id,request.request_id,db)
            assert after.value.code=='LIBRARY_RECORD_INVALID'
            assert db.scalar(text('SELECT COUNT(*) FROM assistant_handler_receipts'))==1
    finally:
        recovered.engine.dispose()
    print('CONFIRMED: qxbak creation and restore succeed with mismatched research.accepted call_id; restored research lookup fails LIBRARY_RECORD_INVALID.')
