"""Bounded read-only proof of the fixed profile save behind one model output."""
from uuid import UUID

from sqlalchemy import text

from ... import domain as d
from ...security import ServiceError
from .. import model_integrity as ledger, profile_model_integrity, profile_store, service
from . import profile_preparation
from .policy import encoded, sha


def _one(db, table, field, identifier):
    # Table and field names are fixed private call sites, never caller input.
    return db.execute(text(f'SELECT * FROM {table} WHERE {field}=:id'),
                      {'id':str(identifier)}).mappings().first()


def read_save(actor, row, prepared, view, db):
    """Called after conversation ownership; historical revisions stay historical."""
    try:
        return _read(actor, row, prepared, view, db)
    except (ValueError, TypeError, KeyError):
        raise ServiceError('VERSION_CONFLICT', 409) from None


def _handler_events(row, output, handler, db):
    events = db.execute(text('''SELECT * FROM assistant_run_events WHERE run_id=:run
        AND (lower(event_type)='response.ready' OR lower(event_type) LIKE 'profile.%')
        ORDER BY seq'''), {'run':row['run_id']}).mappings().all()
    if len(events) != 2:
        ledger._fail()
    ready, result = events
    outcome, reason, sequence = (handler[key] for key in ('outcome', 'reason_code', 'profile_receipt_sequence'))
    if (outcome == 'blocked' and (reason not in ('version_conflict', 'save_failed') or sequence is not None)
            or outcome != 'blocked' and (reason is not None or type(sequence) is not int or sequence < 1)):
        ledger._fail()
    payload = dict(attempt_id=row['id'], output_id=output['id'], handler_id='profile.save', handler_version='1')
    finished = db.execute(text("SELECT seq,created_at FROM assistant_run_events WHERE run_id=:run AND event_type='model.finished'"),
                          {'run':row['run_id']}).mappings().one()
    if (ready['event_type'] != 'response.ready' or ready['seq'] != handler['event_seq']
            or ledger._json(ready['payload_json'], 16384) != dict(payload, basis_sha256=handler['basis_sha256'])
            or result['event_type'] != {'applied':'profile.saved', 'unchanged':'profile.unchanged', 'blocked':'profile.blocked'}[outcome]
            or ledger._json(result['payload_json'], 16384) != dict(payload, event_seq=ready['seq'],
                outcome=outcome, reason_code=reason, profile_receipt_sequence=sequence)
            or not ready['seq'] < result['seq'] < finished['seq']
            or any(event['audience'] != 'internal' for event in events)
            or not ledger._at(output['created_at']) <= ledger._at(ready['created_at'])
                <= ledger._at(result['created_at']) <= ledger._at(finished['created_at'])
            or not ledger._at(output['created_at']) <= ledger._at(handler['created_at']) <= ledger._at(result['created_at'])):
        ledger._fail()


def _read(actor, row, prepared, view, db):
    handler = _one(db, 'assistant_profile_handlers', 'attempt_id', row['id'])
    if view is None:
        if handler is not None:
            ledger._fail()
        return None
    output = _one(db, 'assistant_model_outputs', 'attempt_id', row['id'])
    run = _one(db, 'assistant_runs', 'id', row['run_id'])
    conversation = _one(db, 'assistant_conversations', 'id', row['conversation_id'])
    message = _one(db, 'assistant_messages', 'id', prepared.request.message_id)
    if any(item is None for item in (handler, output, run, conversation, message)):
        ledger._fail()
    scope, basis = prepared.request.scope, prepared.basis
    fixed = ('workspace_id', 'conversation_id', 'scope_kind', 'scope_ref', 'binding_revision')
    if (any(getattr(scope, key) != getattr(service._snapshot(conversation), key) for key in fixed)
            or scope.input_revision > conversation['input_revision']
            or scope.materials_revision > conversation['materials_revision']
            or run['actor_id'] != str(actor.user_id) or run['conversation_id'] != row['conversation_id']
            or db.scalar(text('SELECT user_id FROM sessions WHERE id=:id'), {'id':run['session_id']}) != run['actor_id']
            or prepared.request.run_id != UUID(row['run_id'])
            or run['message_id'] != str(prepared.request.message_id)
            or message['conversation_id'] != row['conversation_id'] or message['role'] != 'user'
            or message['content'] != prepared.request.content or message['source_revision'] != scope.input_revision
            or ledger._model(d.ScopeSnapshot, run['scope_snapshot']) != scope
            or output['id'] != str(view.id) or output['run_id'] != row['run_id']
            or output['conversation_id'] != row['conversation_id'] or view.run_id != prepared.request.run_id
            or view.scope != scope or ledger._model(d.ScopeSnapshot, output['scope_json']) != scope
            or output['output_json'] != encoded(view) or output['created_at'] != row['updated_at']
            or ledger._at(output['created_at']) != view.created_at
            or handler['run_id'] != row['run_id'] or handler['conversation_id'] != row['conversation_id']
            or handler['output_id'] != output['id'] or handler['handler_id'] != 'profile.save'
            or handler['handler_version'] != '1'):
        ledger._fail()
    config = ledger._model(d.MainModelConfig, row['config_json'])
    policy = ledger._model(d.MainModelPolicy, row['policy_json'])
    if (sha(encoded(config)) != row['config_sha256'] or sha(encoded(policy)) != row['policy_sha256']
            or policy.config_sha256 != row['config_sha256'] or str(policy.policy_id) != row['policy_id']
            or policy.workspace_id != scope.workspace_id or policy.actor_id != actor.user_id):
        ledger._fail()
    profile_model_integrity.validate_input(db, row, prepared, config, policy, run, conversation)
    usage = _one(db, 'assistant_model_receipts', 'attempt_id', row['id'])
    receipt = ledger._receipt(row, usage, output, config, run,
                              ledger._at(row['created_at']), ledger._at(row['updated_at']))
    ledger._events(db, row, run, receipt, output)
    _handler_events(row, output, handler, db)
    profile_model_integrity.validate_output(db, row, prepared, view, run)
    request = profile_preparation.commit_request(prepared, view.candidate)
    saved = profile_store._existing(scope.conversation_id, request.request_id, db)
    result = profile_store._receipt(saved, actor, db) if saved else None
    if (result is not None and (result.sequence != handler['profile_receipt_sequence']
            or result.profile_revision != basis.base_profile_revision + int(result.profile_changed)
            or result.projection_changed and not basis.project_intake
            or basis.expected_intake_id is not None and result.intake_id != basis.expected_intake_id)):
        ledger._fail()
    return d.MainProfileSaveView(outcome=handler['outcome'], reason_code=handler['reason_code'], receipt=result)
