import json
from uuid import uuid4

import pytest
from sqlalchemy import text

from cn_contract import domain as d
from cn_contract.assistant import service
from cn_contract.assistant.library_handlers import begin_library_call, execute_library_handler, read_saved_citation
from cn_contract.assistant.library_records import sha
from cn_contract.assistant.tools.library import LegalLibraryAdapter
from cn_contract.config import canonical_json
from cn_contract.ops import backup
from cn_contract.security import ServiceError
from tests.integration.test_assistant_library_backup import ledger, search
from tests.integration.test_assistant_library_adapter import library
from tests.integration.test_assistant_attachment_backup import corrupt


def test_new_call_samples_composer_but_history_and_archive_keep_old_call(ledger, library):
    _, database, actor, run = ledger
    first = search(ledger, library)
    with database.session() as db:
        view = service.read_conversation(actor, run.scope.conversation_id, db)
        service.save_draft(actor, run.scope.conversation_id, d.AssistantDraftInput(
            expected_scope=view.scope, expected_composer_revision=view.composer_revision,
            content='独立复核草稿'), db)
    with pytest.raises(ServiceError) as caught:
        execute_library_handler(actor, run.id, first.receipt.event_seq, database, LegalLibraryAdapter(library[0]))
    assert caught.value.code == 'VERSION_CONFLICT'
    second = search(ledger, library)
    assert second.receipt.event_seq > first.receipt.event_seq
    with database.session() as db:
        assert read_saved_citation(actor, first.receipt.result.citation_ids[0], db).run_id == run.id
        assert backup._file_references(db) == []


def test_mismatched_content_identity_is_rejected(ledger, library):
    _, database, actor, run = ledger
    first = search(ledger, library)
    with database.session() as db:
        receipt = dict(db.execute(text('SELECT * FROM assistant_handler_receipts')).mappings().one())
        citation = dict(db.execute(text('SELECT * FROM assistant_library_citations WHERE ordinal=0')).mappings().one())
    value = json.loads(citation['citation_json'])
    value['citation_id'] = '0' * 64
    raw = canonical_json(value)
    result = json.loads(receipt['result_json'])
    result['result']['page']['citations'][0] = value
    result_raw = canonical_json(result)
    corrupt(database, 'assistant_library_citations',
        'UPDATE assistant_library_citations SET citation_json=?,citation_sha256=? WHERE id=?',
        (raw, sha(raw), citation['id']))
    corrupt(database, 'assistant_handler_receipts',
        'UPDATE assistant_handler_receipts SET result_json=?,result_sha256=? WHERE id=?',
        (result_raw, sha(result_raw), receipt['id']))
    with database.session() as db, pytest.raises(ServiceError) as caught:
        read_saved_citation(actor, citation['id'], db)
    assert caught.value.code == 'LIBRARY_RECORD_INVALID'
    with database.session() as db, pytest.raises(ValueError, match='ASSISTANT_LIBRARY_INTEGRITY'):
        backup._file_references(db)
