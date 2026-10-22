"""Independent, synthetic-only CH-07B1 probes; no production files or network."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sys
from threading import Event
from uuid import uuid4

import pytest
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'tests' / 'integration'))
from test_assistant_storage import workspace, add_matter, add_intake
from test_assistant_attachments import material_workspace
from test_assistant_profile_sources import parsed_source, patch, read
from cn_contract import domain as d
from cn_contract.assistant import attachments, attachment_files
from cn_contract.assistant.profiles import merge_profile
from cn_contract.security import ServiceError


def assert_conflict(database, actor, proposal):
    with pytest.raises(ServiceError) as error:
        read(database, actor, proposal)
    assert error.value.code == 'VERSION_CONFLICT'


def test_duplicate_selected_parse_versions_fail_closed(material_workspace):
    database, actors, _, _, _ = material_workspace
    proposal, old = parsed_source(material_workspace)
    actor, cid = actors['lawyer'], proposal.scope.conversation_id
    ref = proposal.changes[0].source_refs[0]
    attachments.parse_attachment(actor, cid, ref.attachment_id,
        d.AssistantAttachmentParseInput(request_id=uuid4(), expected_scope=proposal.scope), database=database)
    scope = attachments.read_materials(actor, cid, database=database).scope
    duplicate = [{'attachment_id':str(ref.attachment_id),'parse_revision':2},
                 {'attachment_id':str(ref.attachment_id),'parse_revision':1}]
    with database.session() as db:
        db.execute(text('DROP TRIGGER immutable_assistant_material_snapshots_update'))
        db.execute(text('UPDATE assistant_material_snapshots SET items_json=:items WHERE revision=:rev'),
            {'items':json.dumps(duplicate), 'rev':scope.materials_revision})
    assert_conflict(database, actor, patch(scope, (ref,)))


@pytest.mark.parametrize('forgery', ['original_sha256', 'result_sha256'])
def test_forged_document_hash_is_not_trusted(material_workspace, forgery):
    database, actors, _, _, _ = material_workspace
    proposal, parsed = parsed_source(material_workspace)
    ref = proposal.changes[0].source_refs[0].model_copy(update={forgery:'f'*64})
    forged = patch(proposal.scope, (ref,))
    snapshot = read(database, actors['lawyer'], forged)
    assert getattr(snapshot.documents[0], forgery) != 'f'*64
    assert snapshot.documents[0].result == parsed.result
    with pytest.raises(ValueError, match='source mismatch'):
        merge_profile(None, forged, snapshot)


def test_wrong_reference_conversation_rejected(material_workspace):
    database, actors, _, _, _ = material_workspace
    proposal, _ = parsed_source(material_workspace)
    ref = proposal.changes[0].source_refs[0].model_copy(update={'conversation_id':uuid4()})
    assert_conflict(database, actors['lawyer'], patch(proposal.scope, (ref,)))


def test_two_parse_versions_for_same_document_rejected(material_workspace):
    database, actors, _, _, _ = material_workspace
    proposal, _ = parsed_source(material_workspace)
    ref = proposal.changes[0].source_refs[0]
    assert_conflict(database, actors['lawyer'], patch(proposal.scope, (ref, ref.model_copy(update={'parse_revision':2}))))


@pytest.mark.parametrize('change', ['new_projection_denied', 'projection_converted_membership_removed'])
def test_final_gate_rechecks_projection_access_without_scope_change(material_workspace, monkeypatch, change):
    database, actors, _, _, _ = material_workspace
    proposal, _ = parsed_source(material_workspace)
    actor, cid = actors['lawyer'], proposal.scope.conversation_id
    matter = add_matter(database, actor)
    intake = add_intake(database, actor)
    if change == 'projection_converted_membership_removed':
        with database.session() as db:
            db.execute(text('UPDATE assistant_conversations SET projection_intake_id=:id WHERE id=:cid'),
                {'id':str(intake),'cid':str(cid)})
    entered, resume = Event(), Event()
    original = attachment_files.read_checked
    def held(*args):
        entered.set()
        assert resume.wait(12)
        return original(*args)
    monkeypatch.setattr(attachment_files, 'read_checked', held)
    with ThreadPoolExecutor(max_workers=1) as executor:
        pending = executor.submit(read, database, actor, proposal)
        assert entered.wait(12)
        try:
            with database.session() as db:
                if change == 'new_projection_denied':
                    db.execute(text('UPDATE intake_cases SET owner_id=:owner WHERE id=:id'),
                        {'owner':str(actors['reviewer'].user_id),'id':str(intake)})
                    db.execute(text('UPDATE assistant_conversations SET projection_intake_id=:id WHERE id=:cid'),
                        {'id':str(intake),'cid':str(cid)})
                else:
                    db.execute(text('UPDATE intake_cases SET matter_id=:matter WHERE id=:id'),
                        {'matter':str(matter),'id':str(intake)})
                    db.execute(text('DELETE FROM matter_memberships WHERE matter_id=:id'), {'id':str(matter)})
        finally:
            resume.set()
        with pytest.raises(ServiceError) as error:
            pending.result(timeout=15)
        assert error.value.code == 'CROSS_MATTER_DENIED'
