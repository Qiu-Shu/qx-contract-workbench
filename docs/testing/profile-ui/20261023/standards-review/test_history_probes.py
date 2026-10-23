"""Independent history proof probes; synthetic SQLite and in-memory provider only."""
import json
import pytest
from sqlalchemy import text
from cn_contract.assistant.providers import attempts
from cn_contract.security import ServiceError
from tests.integration.test_assistant_generation import world
from tests.integration.test_assistant_profile_execution import profile_world
from tests.integration.test_assistant_profile_model_integrity import profile_history
from tests.integration.test_assistant_attachment_backup import corrupt
from tests.integration.test_assistant_profile_sources import state


@pytest.mark.parametrize('target', ['cost', 'config', 'ready_time', 'finished_missing', 'ready_audience'])
def test_saved_ui_outcome_does_not_survive_corrupt_underlying_proof(profile_world, target):
    database, actor, *_ = profile_world
    view, _, _ = profile_history(profile_world)
    assert view.profile_save.outcome == 'applied'
    if target == 'cost':
        with database.session() as db:
            payload = json.loads(db.scalar(text('SELECT receipt_json FROM assistant_model_receipts')))
        payload['estimated_cost_usd'] = '0'
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
        corrupt(database, 'assistant_model_receipts', 'UPDATE assistant_model_receipts SET receipt_json=?', (raw,))
    elif target == 'config':
        corrupt(database, 'assistant_model_attempts', 'UPDATE assistant_model_attempts SET config_sha256=?', ('e'*64,))
    elif target == 'ready_time':
        corrupt(database, 'assistant_run_events', "UPDATE assistant_run_events SET created_at=? WHERE event_type='response.ready'", ('2000-01-01T00:00:00+00:00',))
    elif target == 'finished_missing':
        corrupt(database, 'assistant_run_events', "DELETE FROM assistant_run_events WHERE event_type='model.finished'")
    else:
        corrupt(database, 'assistant_run_events', "UPDATE assistant_run_events SET audience='client' WHERE event_type='response.ready'")
    before = state(database)
    with database.session() as db, pytest.raises(ServiceError) as exc:
        attempts.read_attempt(actor, view.id, db)
    assert exc.value.code == 'VERSION_CONFLICT'
    assert state(database) == before, 'read failure must not repair, register or modify the evidence'
