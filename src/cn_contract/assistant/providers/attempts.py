"""Durable single-call ledger. All functions use short caller-owned transactions."""
from decimal import Decimal
import secrets
from uuid import UUID, uuid4

from sqlalchemy import inspect, text

from ... import domain as d
from ...config import canonical_json
from ...ops.storage import require_active
from ...review.model_adapter import strict_json
from ...security import ServiceError
from .. import service
from ..attachment_records import items
from .policy import encoded, sha, prepare, require_policy, reservation, receipt, add_costs, validated


def _model(model, raw):
    return validated(model, strict_json(raw))


def _row(identifier, db):
    row = db.execute(text('SELECT * FROM assistant_model_attempts WHERE id=:id'),
                     {'id':str(identifier)}).mappings().first()
    if row is None:
        raise ServiceError('CROSS_MATTER_DENIED', 403)
    return row


def read_attempt(actor, identifier, db):
    row = _row(identifier, db)
    service._owned(actor, UUID(row['conversation_id']), db)
    prepared = _model(d.MainPreparedInput, row['input_json'])
    usage = db.scalar(text('SELECT receipt_json FROM assistant_model_receipts WHERE attempt_id=:id'), {'id':row['id']})
    output = db.scalar(text('SELECT output_json FROM assistant_model_outputs WHERE attempt_id=:id'), {'id':row['id']})
    return validated(d.MainAttemptView, dict(id=row['id'], run_id=row['run_id'], scope=prepared.request.scope,
        state=row['state'], reserved_usd=row['reserved_usd'],
        receipt=_model(d.MainReceipt, usage) if usage else None,
        output=_model(d.MainOutputView, output) if output else None))


def _event(run_id, event_type, payload, db):
    sequence = db.scalar(text('SELECT COALESCE(MAX(seq),0)+1 FROM assistant_run_events WHERE run_id=:id'),
                         {'id':str(run_id)})
    db.execute(text('''INSERT INTO assistant_run_events(run_id,seq,event_type,audience,payload_json,created_at)
        VALUES(:id,:seq,:type,'internal',:payload,:at)'''), {'id':str(run_id), 'seq':sequence,
        'type':event_type, 'payload':canonical_json(payload), 'at':service._at()})


def _budget(policy, db):
    rows = db.execute(text('''SELECT a.*,r.receipt_json FROM assistant_model_attempts a
        LEFT JOIN assistant_model_receipts r ON r.attempt_id=a.id WHERE a.policy_id=:id'''),
        {'id':str(policy.policy_id)}).mappings().all()
    costs, calls = [], 0
    for row in rows:
        if row['policy_sha256'] != sha(encoded(policy)):
            raise ServiceError('VERSION_CONFLICT', 409)
        if row['state'] == 'failed_before_send':
            continue
        calls += 1
        value = _model(d.MainReceipt, row['receipt_json']) if row['receipt_json'] else None
        costs.append(value.estimated_cost_usd if value and value.cost_status == 'estimated'
                     else Decimal(row['reserved_usd']))
    return add_costs(costs), calls


def enqueue_generation(actor, conversation_id, request, db, runtime):
    request = d.AssistantMessageInput.model_validate(request.model_dump(mode='python'))
    conversation = service._owned(actor, conversation_id, db)
    require_active(db)
    config, policy = runtime.snapshot()
    previous = db.execute(text('''SELECT r.id,a.id AS attempt_id FROM assistant_runs r
        LEFT JOIN assistant_model_attempts a ON a.run_id=r.id
        WHERE r.conversation_id=:cid AND r.request_id=:request'''),
        {'cid':str(conversation_id), 'request':str(request.request_id)}).mappings().first()
    if previous:
        # An old queued message never acquires execution eligibility on upgrade/retry.
        if previous['attempt_id'] is None:
            raise ServiceError('STATE_CONFLICT', 409)
        service.save_message(actor, conversation_id, request, db)
        row = _row(previous['attempt_id'], db)
        prepared = _model(d.MainPreparedInput, row['input_json'])
        if (policy is None or row['config_sha256'] != sha(encoded(config))
                or row['policy_sha256'] != sha(encoded(policy))
                or prepare(prepared.request, config).wire_payload_json != prepared.wire_payload_json):
            raise ServiceError('VERSION_CONFLICT', 409)
        return read_attempt(actor, UUID(row['id']), db)
    require_policy(config, policy, actor, service._snapshot(conversation), sha(request.content))
    if request.attachment_ids or items(conversation, db):
        raise ServiceError('BLOCKED_LIVE', 403)
    used, calls = _budget(policy, db)
    reserved = reservation(config)
    if add_costs((used,reserved)) > policy.max_total_usd:
        raise ServiceError('BUDGET_EXCEEDED', 403)
    if calls >= policy.max_calls:
        raise ServiceError('CALL_LIMIT_EXCEEDED', 403)
    with db.begin_nested():
        run = service.save_message(actor, conversation_id, request, db)
        prepared = prepare(d.MainRequest(run_id=run.id, scope=run.scope, message_id=run.message_id,
            content=request.content, source_sha256=sha(request.content)), config)
        identifier, at = uuid4(), service._at()
        db.execute(text('''INSERT INTO assistant_model_attempts
            (id,run_id,conversation_id,policy_id,config_sha256,policy_sha256,request_sha256,
             input_json,config_json,policy_json,reserved_usd,created_at,state,updated_at)
            VALUES(:id,:run,:cid,:policy,:config_sha,:policy_sha,:request_sha,:input,:config,:policy_json,
                   :reserved,:at,'reserved',:at)'''), {'id':str(identifier), 'run':str(run.id),
            'cid':str(conversation_id), 'policy':str(policy.policy_id), 'config_sha':sha(encoded(config)),
            'policy_sha':sha(encoded(policy)), 'request_sha':sha(prepared.wire_payload_json),
            'input':encoded(prepared), 'config':encoded(config), 'policy_json':encoded(policy),
            'reserved':str(reserved), 'at':at})
        db.execute(text('''UPDATE assistant_runs SET selected_provider=:provider,selected_model=:model,
            budget_json=:budget WHERE id=:id'''), {'id':str(run.id), 'provider':config.provider,
            'model':config.model, 'budget':canonical_json({'policy_id':str(policy.policy_id),
                'reserved_usd':str(reserved), 'unit':'USD'})})
        _event(run.id, 'model.reserved', {'attempt_id':str(identifier), 'state':'queued'}, db)
    return read_attempt(actor, identifier, db)


def _current(actor, row, db, runtime):
    require_active(db)
    run = service._owned_run(actor, UUID(row['run_id']), db)
    conversation = service._owned(actor, UUID(row['conversation_id']), db)
    prepared = _model(d.MainPreparedInput, row['input_json'])
    config, policy = runtime.snapshot()
    require_policy(config, policy, actor, prepared.request.scope, prepared.request.source_sha256)
    if (str(actor.session_id) != run['session_id'] or run['actor_id'] != str(actor.user_id)
            or conversation['archived_at'] is not None or service._snapshot(conversation) != prepared.request.scope
            or row['config_sha256'] != sha(encoded(config)) or row['policy_sha256'] != sha(encoded(policy))
            or run['cancel_requested'] or run['state'] not in {'queued','generating'}
            or prepare(prepared.request, config).wire_payload_json != prepared.wire_payload_json):
        raise ServiceError('VERSION_CONFLICT', 409)
    if items(conversation, db):
        raise ServiceError('BLOCKED_LIVE', 403)
    return prepared.request, config


def _abandon_unsent(row, db):
    """Release only a reservation which has never acquired a send claim."""
    at = service._at()
    changed = db.execute(text('''UPDATE assistant_model_attempts SET state='failed_before_send',updated_at=:at
        WHERE id=:id AND state='reserved' AND claim_sha256 IS NULL'''),
        {'id':row['id'], 'at':at}).rowcount
    if changed != 1:
        raise ServiceError('STATE_CONFLICT', 409)
    value = receipt(d.MainReply(state='failed_before_send', error_code='BLOCKED_LIVE'),
                    _model(d.MainModelConfig, row['config_json']))
    db.execute(text('INSERT INTO assistant_model_receipts VALUES(:id,:receipt,:at)'),
               {'id':row['id'], 'receipt':encoded(value), 'at':at})
    cancelled = db.scalar(text('SELECT cancel_requested FROM assistant_runs WHERE id=:id'), {'id':row['run_id']})
    state = 'cancelled' if cancelled else 'failed'
    db.execute(text('UPDATE assistant_runs SET state=:state WHERE id=:id'), {'id':row['run_id'], 'state':state})
    _event(row['run_id'], 'model.finished', {'attempt_id':row['id'], 'state':state, 'output_id':None,
           'cost_status':'not_sent', 'error_code':value.error_code}, db)


def cancel_reserved_for_run(run_id, db):
    # Legacy service-only databases may not yet contain the model migration.
    if not inspect(db.connection()).has_table('assistant_model_attempts'):
        return
    row = db.execute(text("SELECT * FROM assistant_model_attempts WHERE run_id=:id AND state='reserved'"),
                     {'id':str(run_id)}).mappings().first()
    if row is not None:
        _abandon_unsent(row, db)


def claim(actor, identifier, db, runtime):
    row = _row(identifier, db)
    service._owned(actor, UUID(row['conversation_id']), db)
    require_active(db)
    if row['state'] != 'reserved':
        return None
    try:
        request, config = _current(actor, row, db, runtime)
        policy = _model(d.MainModelPolicy, row['policy_json'])
        used, calls = _budget(policy, db)
        if used > policy.max_total_usd:
            raise ServiceError('BUDGET_EXCEEDED', 403)
        if calls > policy.max_calls:
            raise ServiceError('CALL_LIMIT_EXCEEDED', 403)
    except (ServiceError, ValueError):
        # Authorization may have ended its transaction to persist a denial audit.
        require_active(db)
        row = _row(identifier, db)
        with db.begin_nested():
            _abandon_unsent(row, db)
        return None
    token = secrets.token_hex(32)
    changed = db.execute(text('''UPDATE assistant_model_attempts SET state='sending',claim_sha256=:claim,
        updated_at=:at WHERE id=:id AND state='reserved' AND claim_sha256 IS NULL'''),
        {'claim':sha(token), 'at':service._at(), 'id':str(identifier)}).rowcount
    if changed != 1:
        raise ServiceError('STATE_CONFLICT', 409)
    db.execute(text("UPDATE assistant_runs SET state='generating' WHERE id=:id"), {'id':row['run_id']})
    _event(row['run_id'], 'model.started', {'attempt_id':row['id'], 'state':'generating'}, db)
    return token, request, config


def settle(actor, identifier, token, reply, db, runtime):
    require_active(db)
    row = _row(identifier, db)
    if row['state'] != 'sending' or row['claim_sha256'] != sha(token):
        raise ServiceError('STATE_CONFLICT', 409)
    reply = d.MainReply.model_validate(reply.model_dump(mode='python'))
    config = _model(d.MainModelConfig, row['config_json'])
    prepared = _model(d.MainPreparedInput, row['input_json'])
    candidate = reply.output
    outside_envelope = reply.usage is not None and (reply.usage.prompt_tokens > config.max_input_bytes
        or reply.usage.completion_tokens > config.max_output_tokens)
    if candidate and (outside_envelope or any(
            c.message_id != prepared.request.message_id or c.quote_sha256 != prepared.request.source_sha256
            for c in candidate.citations)):
        reply = d.MainReply(state='received', provider_request_id=reply.provider_request_id,
            usage=reply.usage, error_code='MODEL_OUTPUT_INVALID')
        candidate = None
    value = receipt(reply, config)
    adopt = False
    try:
        _current(actor, row, db, runtime)
        adopt = candidate is not None
    except (ServiceError, ValueError):
        pass
    # Some authorization denials commit their audit. Reacquire the write lock and
    # check the fence and one-time claim again before persisting in the new transaction.
    require_active(db)
    current_row = _row(identifier, db)
    if current_row['state'] != 'sending' or current_row['claim_sha256'] != sha(token):
        raise ServiceError('STATE_CONFLICT', 409)
    at = service._at()
    with db.begin_nested():
        db.execute(text('''INSERT INTO assistant_model_receipts VALUES(:id,:receipt,:at)'''),
            {'id':row['id'], 'receipt':encoded(value), 'at':at})
        db.execute(text('UPDATE assistant_model_attempts SET state=:state,updated_at=:at WHERE id=:id'),
            {'state':reply.state, 'at':at, 'id':row['id']})
        output_id = None
        if adopt:
            output = d.MainOutputView(id=uuid4(), run_id=row['run_id'], scope=prepared.request.scope,
                                     candidate=candidate, created_at=at)
            output_id = str(output.id)
            db.execute(text('''INSERT INTO assistant_model_outputs VALUES(:id,:attempt,:cid,:run,:scope,:output,:at)'''),
                {'id':output_id, 'attempt':row['id'], 'cid':row['conversation_id'], 'run':row['run_id'],
                 'scope':encoded(output.scope), 'output':encoded(output), 'at':at})
        cancelled = db.scalar(text('SELECT cancel_requested FROM assistant_runs WHERE id=:id'), {'id':row['run_id']})
        state = 'completed' if adopt else ('cancelled' if cancelled else 'failed')
        db.execute(text('UPDATE assistant_runs SET state=:state WHERE id=:id'), {'state':state, 'id':row['run_id']})
        _event(row['run_id'], 'model.finished', {'attempt_id':row['id'], 'state':state, 'output_id':output_id,
            'cost_status':value.cost_status, 'error_code':reply.error_code}, db)


def recover_attempts(db):
    """Trusted maintenance only; no network and no resurrection of old queued work."""
    rows = db.execute(text("SELECT * FROM assistant_model_attempts WHERE state IN ('reserved','sending')")).mappings().all()
    for row in rows:
        state = 'failed_before_send' if row['state'] == 'reserved' else 'sent_unknown'
        value = receipt(d.MainReply(state=state, error_code='BLOCKED_LIVE'), _model(d.MainModelConfig, row['config_json']))
        at = service._at()
        db.execute(text('INSERT INTO assistant_model_receipts VALUES(:id,:receipt,:at)'),
            {'id':row['id'], 'receipt':encoded(value), 'at':at})
        db.execute(text('UPDATE assistant_model_attempts SET state=:state,updated_at=:at WHERE id=:id'),
            {'state':state, 'at':at, 'id':row['id']})
        db.execute(text("UPDATE assistant_runs SET state='interrupted' WHERE id=:id"), {'id':row['run_id']})
        _event(row['run_id'], 'model.interrupted', {'attempt_id':row['id'], 'state':'interrupted',
            'cost_status':value.cost_status}, db)
    return len(rows)
