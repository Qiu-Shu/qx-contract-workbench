"""Actual synthetic saved views feed offline preparation without a model attempt."""
from uuid import uuid4

import pytest
from sqlalchemy import inspect, text

from cn_contract import domain as d
from cn_contract.assistant import service, profile_schema
from cn_contract.assistant.providers import profile_preparation, profile_codec
from test_assistant_storage import workspace
from test_assistant_main_provider import config, KEY
from tests.unit.test_assistant_profile_codec import response


def test_saved_message_and_run_round_trip_to_c1_without_grant_or_archive(workspace):
    database, actors, _, _ = workspace
    actor = actors['lawyer']
    profile_schema.initialize_storage(database)
    with database.session() as db:
        conversation = service.create_conversation(actor, d.AssistantConversationCreateInput(request_id=uuid4()), db)
        submission = d.AssistantMessageInput(request_id=uuid4(), expected_scope=conversation.scope,
            expected_composer_revision=conversation.composer_revision, content='甲称借款35000元。')
    basis = profile_preparation.build_basis(submission, config(), base_profile_revision=0, project_intake=True)
    with database.session() as db:
        run = service.save_message(actor, conversation.scope.conversation_id, submission, db)
        after = service.read_conversation(actor, conversation.scope.conversation_id, db)
    prepared = profile_preparation.prepare(run, after.messages[-1], basis, config(),
        composer_revision=after.composer_revision)
    assert prepared.request.run_id == run.id
    assert prepared.request.message_id == run.message_id
    assert prepared.basis.request_id == submission.request_id
    assert prepared.request.scope == after.scope
    reply = profile_codec.decode_response(response(prepared.request), prepared.request, config(), KEY)
    ref = reply.output.profile_patch.changes[0].source_refs[0]
    assert (ref.message_id, ref.source_revision, ref.quote) == (run.message_id, after.scope.input_revision, '甲称借款35000元')
    with database.session() as db:
        assert service.get_run(actor, run.id, db).state == 'queued'
        # This minimal local fixture has no model ledger; preparation must not create one.
        assert not inspect(db.connection()).has_table('assistant_model_attempts')
        assert not inspect(db.connection()).has_table('assistant_model_receipts')
        for table in ('assistant_profile_revisions', 'assistant_profile_receipts', 'intake_cases'):
            assert db.scalar(text('SELECT count(*) FROM ' + table)) == 0
    with pytest.raises(ValueError):
        profile_preparation.prepare(run.model_copy(update={'request_id': uuid4()}), after.messages[-1],
            basis, config(), composer_revision=after.composer_revision)
