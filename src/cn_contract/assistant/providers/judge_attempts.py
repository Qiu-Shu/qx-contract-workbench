"""Durable Jev accounting on an owned run; every transaction is caller-owned."""
from datetime import datetime
from decimal import Decimal
import secrets
from typing import get_args
from uuid import UUID, uuid4

from sqlalchemy import inspect, text

from ... import domain as d
from ...ops.storage import require_active
from ...review.model_adapter import strict_json
from ...security import ServiceError
from .. import service
from ..attachment_records import items
from ..routing import choose_workflow
from . import jev_codec
from .judge_policy import JudgeRuntime, copy, encoded, receipt, sha, total, validated


_ACTIVE = {'queued', 'preparing', 'routing', 'retrieving', 'generating', 'persisting', 'awaiting_input'}


def model(kind, raw):
    return validated(kind, strict_json(raw))


def _row(identifier, db):
    row = db.execute(text('SELECT * FROM assistant_judge_attempts WHERE id=:id'),
                     {'id':str(identifier)}).mappings().first()
    if row is None:
        raise ServiceError('CROSS_MATTER_DENIED', 403)
    return row


def request_for_run(actor, run_id, db, config, *, purpose='primary_intent'):
    config = copy(d.JevConfig, config)
    run = service._owned_run(actor, run_id, db)
    conversation = service._owned(actor, UUID(run['conversation_id']), db)
    require_active(db)
    scope = model(d.ScopeSnapshot, run['scope_snapshot'])
    message = db.execute(text('SELECT * FROM assistant_messages WHERE id=:id'),
                         {'id':run['message_id']}).mappings().one()
    if (purpose != 'primary_intent' or run['actor_id'] != str(actor.user_id)
            or run['session_id'] != str(actor.session_id)
            or conversation['archived_at'] is not None or scope != service._snapshot(conversation)
            or run['cancel_requested'] or run['state'] not in _ACTIVE
            or message['conversation_id'] != run['conversation_id'] or message['role'] != 'user'
            or message['source_revision'] != scope.input_revision or items(conversation, db)):
        raise ServiceError('BLOCKED_LIVE', 403)
    request = d.JudgeRequest(local_request_id=UUID(run['request_id']), scope=scope,
        purpose=purpose, text=message['content'], explicit_skill=run['requested_skill'])
    if request.explicit_skill is not None:
        return request
    try:
        jev_codec.build_request(request, config)
    except ValueError:
        raise ServiceError('BLOCKED_LIVE', 403) from None
    return request


def read_attempt(actor, identifier, db):
    row = _row(identifier, db)
    service._owned(actor, UUID(row['conversation_id']), db)
    request = model(d.JudgeRequest, row['request_json'])
    stored = db.scalar(text('SELECT receipt_json FROM assistant_judge_receipts WHERE attempt_id=:id'), {'id':row['id']})
    decision = db.scalar(text('SELECT decision_json FROM assistant_judge_decisions WHERE attempt_id=:id'), {'id':row['id']})
    return validated(d.JudgeAttemptView, dict(id=row['id'], run_id=row['run_id'], message_id=row['message_id'],
        purpose=row['purpose'], scope=request.scope, state=row['state'], reserved_usd=row['reserved_usd'],
        receipt=model(d.JudgeReceipt, stored) if stored else None,
        decision=model(d.JudgeDecisionView, decision) if decision else None))


def _budget(policy, db):
    rows = db.execute(text('''SELECT a.*,r.receipt_json FROM assistant_judge_attempts a
        LEFT JOIN assistant_judge_receipts r ON r.attempt_id=a.id WHERE a.policy_id=:id'''),
        {'id':str(policy.policy_id)}).mappings().all()
    costs = []; calls = 0
    for row in rows:
        if row['policy_sha256'] != sha(encoded(policy)):
            raise ServiceError('VERSION_CONFLICT', 409)
        if row['state'] == 'not_sent':
            continue
        calls += 1
        costs.append(Decimal(row['reserved_usd']))
    return total(costs), calls


def reserve(actor, run_id, db, runtime, *, purpose='primary_intent'):
    if type(runtime) is not JudgeRuntime:
        raise ServiceError('BLOCKED_LIVE', 403)
    run = service._owned_run(actor, run_id, db)
    if run['requested_skill'] is not None:
        request_for_run(actor, run_id, db, d.JevConfig(), purpose=purpose)
        return None
    config = runtime.configuration()
    request = request_for_run(actor, run_id, db, config, purpose=purpose)
    if request.explicit_skill is not None:
        return None
    config, policy, version = runtime.snapshot_for(actor, request)
    previous = db.execute(text('SELECT * FROM assistant_judge_attempts WHERE run_id=:run AND purpose=:purpose'),
                          {'run':str(run_id), 'purpose':purpose}).mappings().first()
    digest = jev_codec.input_hash(request, config)
    if previous:
        if (previous['input_hash'] != digest or previous['policy_sha256'] != sha(encoded(policy))
                or previous['config_sha256'] != sha(encoded(config))):
            raise ServiceError('VERSION_CONFLICT', 409)
        return read_attempt(actor, UUID(previous['id']), db)
    used, calls = _budget(policy, db)
    if total((used, policy.reserved_usd)) > policy.max_total_usd or calls >= policy.max_calls:
        raise ServiceError('BUDGET_EXCEEDED', 403)
    run = service._owned_run(actor, run_id, db)
    identifier, at = uuid4(), service._at()
    db.execute(text('''INSERT INTO assistant_judge_attempts
        (id,run_id,conversation_id,message_id,actor_id,session_id,purpose,policy_id,authorization_id,
         config_sha256,policy_sha256,input_hash,source_sha256,request_json,config_json,policy_json,
         reserved_usd,created_at,state,updated_at)
        VALUES(:id,:run,:cid,:message,:actor,:session,:purpose,:policy,:version,:cfgsha,:policysha,:inputhash,
               :source,:request,:config,:policyjson,:reserved,:at,'reserved',:at)'''),
        {'id':str(identifier), 'run':str(run_id), 'cid':run['conversation_id'], 'message':run['message_id'],
         'actor':str(actor.user_id), 'session':str(actor.session_id), 'purpose':purpose,
         'policy':str(policy.policy_id), 'version':str(version), 'cfgsha':sha(encoded(config)),
         'policysha':sha(encoded(policy)), 'inputhash':digest, 'source':sha(request.text),
         'request':encoded(request), 'config':encoded(config), 'policyjson':encoded(policy),
         'reserved':str(policy.reserved_usd), 'at':at})
    return read_attempt(actor, identifier, db)


def _current(actor, row, db, runtime):
    if type(runtime) is not JudgeRuntime:
        raise ServiceError('BLOCKED_LIVE', 403)
    stored = model(d.JudgeRequest, row['request_json'])
    config, policy, version = runtime.snapshot_for(actor, stored)
    current = request_for_run(actor, UUID(row['run_id']), db, config, purpose=row['purpose'])
    if (current != stored or str(version) != row['authorization_id']
            or row['policy_sha256'] != sha(encoded(policy)) or row['config_sha256'] != sha(encoded(config))
            or jev_codec.input_hash(current, config) != row['input_hash']):
        raise ServiceError('VERSION_CONFLICT', 409)
    used, calls = _budget(policy, db)
    if used > policy.max_total_usd or calls > policy.max_calls:
        raise ServiceError('BUDGET_EXCEEDED', 403)
    return current, config


def fallback(row, *, evidence='sent_unknown', reason='provider_error'):
    request = model(d.JudgeRequest, row['request_json'])
    return d.JudgeResult(status='failed', reason_code=reason, evidence=evidence,
        local_request_id=request.local_request_id, scope=request.scope, input_hash=row['input_hash'], elapsed_ms=0)


def _record(row, result, db, *, decision=None):
    at = service._at()
    if decision is not None and model(d.JudgePolicy, row['policy_json']).expires_at <= datetime.fromisoformat(at):
        decision = None
    value = receipt(result, Decimal(row['reserved_usd']))
    db.execute(text('INSERT INTO assistant_judge_receipts VALUES(:id,:receipt,:at)'),
               {'id':row['id'], 'receipt':encoded(value), 'at':at})
    db.execute(text('UPDATE assistant_judge_attempts SET state=:state,updated_at=:at WHERE id=:id'),
               {'state':result.evidence, 'at':at, 'id':row['id']})
    if decision is not None:
        output = d.JudgeDecisionView(attempt_id=row['id'], run_id=row['run_id'], scope=result.scope,
                                    decision=decision, created_at=at)
        db.execute(text('INSERT INTO assistant_judge_decisions VALUES(:id,:decision,:at)'),
                   {'id':row['id'], 'decision':encoded(output), 'at':at})


def _abandon(row, db):
    if row['state'] != 'reserved' or row['claim_sha256'] is not None:
        raise ServiceError('STATE_CONFLICT', 409)
    _record(row, fallback(row, evidence='not_sent', reason='config_changed'), db)


def claim(actor, identifier, db, runtime):
    row = _row(identifier, db)
    service._owned(actor, UUID(row['conversation_id']), db)
    require_active(db)
    if row['actor_id'] != str(actor.user_id) or row['session_id'] != str(actor.session_id):
        raise ServiceError('BLOCKED_LIVE', 403)
    if row['state'] != 'reserved':
        return None
    try:
        request, config = _current(actor, row, db, runtime)
    except (ServiceError, ValueError):
        require_active(db)
        row = _row(identifier, db)
        with db.begin_nested():
            _abandon(row, db)
        return None
    token = secrets.token_hex(32)
    changed = db.execute(text('''UPDATE assistant_judge_attempts SET state='sending',claim_sha256=:claim,updated_at=:at
        WHERE id=:id AND state='reserved' AND claim_sha256 IS NULL'''),
        {'id':str(identifier), 'claim':sha(token), 'at':service._at()}).rowcount
    if changed != 1:
        raise ServiceError('STATE_CONFLICT', 409)
    return token, request, config


def preflight(actor, identifier, token, request, config, db, runtime):
    row = _row(identifier, db)
    if row['state'] != 'sending' or row['claim_sha256'] != sha(token):
        raise ServiceError('STATE_CONFLICT', 409)
    current, expected = _current(actor, row, db, runtime)
    if current != request or expected != config:
        raise ServiceError('VERSION_CONFLICT', 409)


def settle(actor, identifier, token, result, db, runtime):
    require_active(db)
    row = _row(identifier, db)
    actor = copy(d.Actor, actor)
    if row['actor_id'] != str(actor.user_id) or row['session_id'] != str(actor.session_id):
        raise ServiceError('BLOCKED_LIVE', 403)
    if row['state'] != 'sending' or type(token) is not str or row['claim_sha256'] != sha(token):
        raise ServiceError('STATE_CONFLICT', 409)
    # Receipt identity cannot be supplied by another attempt, even if its answer is valid.
    result = copy(d.JudgeResult, result)
    request = model(d.JudgeRequest, row['request_json'])
    config = model(d.JevConfig, row['config_json'])
    if (result.local_request_id != request.local_request_id or result.scope != request.scope
            or result.input_hash != row['input_hash']):
        raise ServiceError('VERSION_CONFLICT', 409)
    decision = None
    try:
        _current(actor, row, db, runtime)
        if (result.status == 'ok' and result.elapsed_ms < config.timeout_ms
                and set(result.answers) == {request.purpose}):
            decision = choose_workflow(request.explicit_skill, result, get_args(d.AssistantSkill))
    except (ServiceError, ValueError):
        pass
    # Authorization checks can commit a denial audit. Reacquire the write lock/fence.
    require_active(db)
    row = _row(identifier, db)
    if row['state'] != 'sending' or row['claim_sha256'] != sha(token):
        raise ServiceError('STATE_CONFLICT', 409)
    with db.begin_nested():
        _record(row, result, db, decision=decision)


def cancel_reserved_for_run(run_id, db):
    if not inspect(db.connection()).has_table('assistant_judge_attempts'):
        return 0
    rows = db.execute(text("SELECT * FROM assistant_judge_attempts WHERE run_id=:id AND state='reserved'"),
                      {'id':str(run_id)}).mappings().all()
    for row in rows:
        _abandon(row, db)
    return len(rows)


def recover_attempts(db):
    """Maintenance only: accounting evidence, never enqueue or modify a main run."""
    rows = db.execute(text("SELECT * FROM assistant_judge_attempts WHERE state IN ('reserved','sending')")).mappings().all()
    for row in rows:
        result = fallback(row, evidence='not_sent' if row['state'] == 'reserved' else 'sent_unknown')
        _record(row, result, db)
    return len(rows)
