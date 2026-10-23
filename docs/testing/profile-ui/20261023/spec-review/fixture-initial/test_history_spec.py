import json
from uuid import UUID

import pytest
from sqlalchemy import text

from cn_contract import domain as d
from cn_contract.assistant.providers import attempts
from cn_contract.config import canonical_json
from cn_contract.intake import service as intake
from cn_contract.security import ServiceError, authenticate, login, revoke_session
from cn_contract.assistant.providers.policy import sha
from tests.integration.test_assistant_generation import world
from tests.integration.test_assistant_profile_execution import profile_world
from tests.integration.test_assistant_profile_model_integrity import profile_history
from tests.integration.test_assistant_attachment_backup import corrupt
from tests.integration.test_assistant_profile_sources import state


def read(database, actor, identifier):
    with database.session() as db:
        return attempts.read_attempt(actor, identifier, db)


def test_receipt_survives_edit_conversion_and_new_session_without_regrant(profile_world):
    database, actor, *_ = profile_world
    original, _, _ = profile_history(profile_world)
    with database.session() as db:
        record = intake.read(original.profile_save.receipt.intake_id, actor, db)
        draft = d.IntakeDraft.model_validate(record.model_dump(include=set(d.IntakeDraft.model_fields)))
        changed = intake.save(record.id, d.IntakeUpdateInput(expected_revision=record.revision,
            draft=draft.model_copy(update={'consultation':'后续律师独立更正，不改变原保存回执。'})), actor, db)
        intake.convert(changed.id, d.IntakeConvertInput(expected_revision=changed.revision,
            matter=d.MatterCreateInput(title='合成转换', contract_type='unknown', review_mode='pre_sign',
                position='party_a', objectives=('独立历史复核',))), actor, db)
        revoke_session(actor.session_id, db)
        token, _ = login('lawyer', 'fixture123', db)
        current = authenticate(token, db)
    before = state(database)
    actual = read(database, current, original.id)
    assert actual.profile_save == original.profile_save
    assert actual.output == original.output
    assert state(database) == before
    with pytest.raises(ServiceError) as denied:
        read(database, actor, original.id)
    assert denied.value.code == 'AUTHORIZATION_REQUIRED'


def test_rehashed_wire_only_permission_cannot_support_profile_save_history(profile_world):
    database, actor, *_ = profile_world
    original, prepared, _ = profile_history(profile_world)
    with database.session() as db:
        raw = json.loads(db.scalar(text('SELECT policy_json FROM assistant_model_attempts')))
    raw['allowed_content_sha256s'] = [prepared.basis.wire_sha256]
    serialized = canonical_json(raw)
    corrupt(database, 'assistant_model_attempts',
        'UPDATE assistant_model_attempts SET policy_json=?,policy_sha256=?', (serialized, sha(serialized)))
    with pytest.raises(ServiceError) as denied:
        read(database, actor, original.id)
    assert denied.value.code == 'VERSION_CONFLICT'


def test_removed_finish_event_does_not_leave_an_applied_ui_receipt(profile_world):
    database, actor, *_ = profile_world
    original, _, _ = profile_history(profile_world)
    corrupt(database, 'assistant_run_events', "DELETE FROM assistant_run_events WHERE event_type='model.finished'")
    with pytest.raises(ServiceError) as denied:
        read(database, actor, original.id)
    assert denied.value.code == 'VERSION_CONFLICT'
