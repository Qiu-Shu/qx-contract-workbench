"""Purpose-bound profile execution on the existing single-call ledger.

No HTTP entry or new task queue lives here. Callers own short transactions;
network execution stays in the common runner outside those transactions.
"""
from uuid import UUID, uuid4

from sqlalchemy import text

from ... import domain as d
from ...config import canonical_json
from ...ops.storage import require_active
from ...security import ServiceError
from .. import profile_preparation_service as inputs, profile_store, service
from . import attempts, profile_preparation
from .policy import add_costs, encoded, receipt, require_policy, reservation, sha, budget_exceeded


def _check(runtime, name, *args):
    method = getattr(runtime, name, None)
    if not callable(method):
        raise ServiceError('BLOCKED_LIVE', 403)
    method(*args)


def enqueue(actor, cid, request, db, runtime, *, project_intake=False):
    request = d.AssistantMessageInput.model_validate(request.model_dump(mode='python'))
    if type(project_intake) is not bool:
        raise ServiceError('VERSION_CONFLICT', 409)
    conversation = service._owned(actor, cid, db)
    require_active(db)
    config, policy = runtime.snapshot_for(actor, service._snapshot(conversation))
    previous = attempts._previous(cid, request.request_id, db)
    if previous:
        if previous['attempt_id'] is None:
            raise ServiceError('STATE_CONFLICT', 409)
        row = attempts._row(previous['attempt_id'], db)
        prepared = attempts._input(row)
        if not isinstance(prepared, d.MainProfilePreparedInput):
            raise ServiceError('VERSION_CONFLICT', 409)
        basis = prepared.basis
        # Replay compares the registered plan, never a newly advanced baseline.
        if (basis.project_intake != project_intake or request.content != prepared.request.content
                or policy is None or row['config_sha256'] != sha(encoded(config))
                or row['policy_sha256'] != sha(encoded(policy))):
            raise ServiceError('VERSION_CONFLICT', 409)
        service.save_message(actor, cid, request, db)
        _check(runtime, 'check_profile_submission', actor, request, basis)
        if attempts._wire(prepared, config) != prepared.wire_payload_json:
            raise ServiceError('VERSION_CONFLICT', 409)
        return attempts.read_attempt(actor, UUID(row['id']), db)
    basis = inputs.build_profile_basis(actor, cid, request, db, config=config,
                                       project_intake=project_intake)
    _check(runtime, 'check_profile_submission', actor, request, basis)
    require_policy(config, policy, actor, basis.expected_scope, profile_preparation.basis_digest(basis))
    used, calls = attempts._budget(policy, db)
    reserved = reservation(config)
    if budget_exceeded(add_costs((used, reserved)), policy.max_total_usd):
        raise ServiceError('BUDGET_EXCEEDED', 403)
    if calls >= policy.max_calls:
        raise ServiceError('CALL_LIMIT_EXCEEDED', 403)
    with db.begin_nested():
        run = service.save_message(actor, cid, request, db)
        prepared = inputs.prepare_profile(actor, run.id, basis, db, config=config)
        identifier, at = uuid4(), service._at()
        db.execute(text('''INSERT INTO assistant_model_attempts
            (id,run_id,conversation_id,policy_id,config_sha256,policy_sha256,request_sha256,
             input_json,config_json,policy_json,reserved_usd,created_at,state,updated_at,input_format,round_no)
            VALUES(:id,:run,:cid,:policy,:config_sha,:policy_sha,:request_sha,:input,:config,:policy_json,
                   :reserved,:at,'reserved',:at,'profile-text-v1',1)'''),
            {'id':str(identifier), 'run':str(run.id), 'cid':str(cid), 'policy':str(policy.policy_id),
             'config_sha':sha(encoded(config)), 'policy_sha':sha(encoded(policy)),
             'request_sha':sha(prepared.wire_payload_json), 'input':encoded(prepared),
             'config':encoded(config), 'policy_json':encoded(policy), 'reserved':str(reserved), 'at':at})
        db.execute(text('''UPDATE assistant_runs SET selected_provider=:provider,selected_model=:model,
            budget_json=:budget WHERE id=:id'''), {'id':str(run.id), 'provider':config.provider,
            'model':config.model, 'budget':canonical_json({'policy_id':str(policy.policy_id),
                'reserved_usd':str(reserved), 'unit':'USD'})})
        attempts._event(run.id, 'model.reserved', {'attempt_id':str(identifier), 'state':'queued'}, db)
    return attempts.read_attempt(actor, identifier, db)


def current(actor, row, db, runtime):
    require_active(db)
    prepared = attempts._input(row)
    if not isinstance(prepared, d.MainProfilePreparedInput):
        raise ServiceError('VERSION_CONFLICT', 409)
    config, policy = runtime.snapshot_for(actor, prepared.request.scope)
    _check(runtime, 'check_profile_execution', actor, prepared.basis.request_id, prepared)
    require_policy(config, policy, actor, prepared.request.scope,
                   profile_preparation.basis_digest(prepared.basis))
    rebuilt = inputs.prepare_profile(actor, UUID(row['run_id']), prepared.basis, db, config=config)
    if (rebuilt != prepared or str(prepared.request.scope.conversation_id) != row['conversation_id']
            or row['config_sha256'] != sha(encoded(config)) or row['policy_sha256'] != sha(encoded(policy))
            or row['request_sha256'] != sha(prepared.wire_payload_json)):
        raise ServiceError('VERSION_CONFLICT', 409)
    return prepared, config


def _claimed(identifier, token, db):
    require_active(db)
    row = attempts._row(identifier, db)
    if row['state'] != 'sending' or row['claim_sha256'] != sha(token):
        raise ServiceError('STATE_CONFLICT', 409)
    return row


def _sources(prepared, db):
    request = prepared.request
    row = db.execute(text('''SELECT id,role,content,created_at,source_revision FROM assistant_messages
        WHERE id=:id AND conversation_id=:cid'''),
        {'id':str(request.message_id), 'cid':str(request.scope.conversation_id)}).mappings().one()
    # current() just rebuilt the entire prepared input from this same locked DB.
    return d.ProfileSourceSnapshot(scope=request.scope, messages=(d.AssistantMessageView(**row),))


def _persist(row, prepared, reply, candidate, saved, reason, at, db):
    value = receipt(reply, attempts._model(d.MainModelConfig, row['config_json']))
    db.execute(text('INSERT INTO assistant_model_receipts VALUES(:id,:receipt,:at)'),
               {'id':row['id'], 'receipt':encoded(value), 'at':at})
    db.execute(text('UPDATE assistant_model_attempts SET state=:state,updated_at=:at WHERE id=:id'),
               {'state':reply.state, 'at':at, 'id':row['id']})
    output_id = None
    if candidate is not None:
        output = d.MainProfileOutputView(id=uuid4(), run_id=row['run_id'], scope=prepared.request.scope,
                                         candidate=candidate, created_at=at)
        output_id = str(output.id)
        db.execute(text('INSERT INTO assistant_model_outputs VALUES(:id,:attempt,:cid,:run,:scope,:output,:at)'),
                   {'id':output_id, 'attempt':row['id'], 'cid':row['conversation_id'], 'run':row['run_id'],
                    'scope':encoded(output.scope), 'output':encoded(output), 'at':at})
        fixed = {'attempt_id':row['id'], 'output_id':output_id,
                 'handler_id':'profile.save', 'handler_version':'1'}
        digest = profile_preparation.basis_digest(prepared.basis)
        seq = attempts._event(row['run_id'], 'response.ready', fixed | {'basis_sha256':digest}, db)
        outcome = ('applied' if saved.event_type == 'profile.saved' else 'unchanged') if saved else 'blocked'
        sequence = saved.sequence if saved else None
        db.execute(text('''INSERT INTO assistant_profile_handlers
            (run_id,event_seq,handler_id,handler_version,attempt_id,output_id,conversation_id,
             profile_receipt_sequence,outcome,reason_code,basis_sha256,created_at)
            VALUES(:run,:seq,'profile.save','1',:attempt,:output,:cid,:receipt,:outcome,:reason,:basis,:at)'''),
            {'run':row['run_id'], 'seq':seq, 'attempt':row['id'], 'output':output_id,
             'cid':row['conversation_id'], 'receipt':sequence, 'outcome':outcome, 'reason':reason,
             'basis':digest, 'at':service._at()})
        attempts._event(row['run_id'], saved.event_type if saved else 'profile.blocked', fixed | {
            'event_seq':seq, 'outcome':outcome, 'reason_code':reason, 'profile_receipt_sequence':sequence}, db)
    cancelled = db.scalar(text('SELECT cancel_requested FROM assistant_runs WHERE id=:id'), {'id':row['run_id']})
    state = 'completed' if candidate is not None else ('cancelled' if cancelled else 'failed')
    db.execute(text('UPDATE assistant_runs SET state=:state WHERE id=:id'), {'state':state, 'id':row['run_id']})
    attempts._event(row['run_id'], 'model.finished', {'attempt_id':row['id'], 'state':state,
        'output_id':output_id, 'cost_status':value.cost_status, 'error_code':reply.error_code}, db)


def settle(actor, identifier, token, reply, db, runtime):
    row = _claimed(identifier, token, db)
    prepared = attempts._input(row)
    reply = d.MainProfileReply.model_validate(reply.model_dump(mode='python'))
    config = attempts._model(d.MainModelConfig, row['config_json'])
    candidate = reply.output
    if candidate is not None:
        try:
            candidate = profile_preparation.validate_candidate(candidate, prepared.request)
            if reply.usage is not None and (reply.usage.prompt_tokens > config.max_input_bytes
                    or reply.usage.completion_tokens > config.max_output_tokens):
                raise ValueError('PROFILE_OUTPUT_INVALID')
        except ValueError:
            reply = d.MainProfileReply(state='received', provider_request_id=reply.provider_request_id,
                                      usage=reply.usage, error_code='MODEL_OUTPUT_INVALID')
            candidate = None
    try:
        current(actor, row, db, runtime)
    except (ServiceError, ValueError):
        candidate = None
    # Authorization denial may roll back and commit an audit. No ledger writes
    # precede it; reacquire the active-store fence and one-time claim afterwards.
    row = _claimed(identifier, token, db)
    reason = None
    if candidate is not None:
        saved_ok = False
        transaction = db.begin_nested()
        try:
            at = service._at()
            saved = profile_store._commit(actor, profile_preparation.commit_request(prepared, candidate),
                                           _sources(prepared, db), db)
            saved_ok = True
            _persist(row, prepared, reply, candidate, saved, None, at, db)
            transaction.commit()
            return
        except Exception as error:
            # Manage the savepoint explicitly: SQLAlchemy's context manager
            # forbids deny() from opening its audit transaction after rollback.
            # If denial already ended it, never roll back the committed audit.
            if transaction.is_active:
                transaction.rollback()
            # Later ledger failures must roll back the successful profile too.
            if saved_ok:
                raise
            reason = 'version_conflict' if isinstance(error, ServiceError) and error.code == 'VERSION_CONFLICT' else 'save_failed'
            row = _claimed(identifier, token, db)
            try:
                current(actor, row, db, runtime)
            except (ServiceError, ValueError):
                candidate = None
            row = _claimed(identifier, token, db)
    with db.begin_nested():
        _persist(row, prepared, reply, candidate, None, reason, service._at(), db)
