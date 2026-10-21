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
from . import context_codec
from .policy import encoded, sha, prepare, require_policy, reservation, receipt, add_costs, validated


def _model(model, raw):
    return validated(model, strict_json(raw))


def _input(row):
    """Private format dispatch shared by every ledger reader.

    The current schema always carries input_format; a missing or unknown value
    is corruption, never a silent fallback. Only archive validation against a
    positively identified older schema decodes historical rows as V1 elsewhere.
    """
    fmt = row['input_format'] if 'input_format' in row.keys() else None
    if fmt == 'plain-text-v1':
        return _model(d.MainPreparedInput, row['input_json'])
    if fmt == 'library-context-v1':
        return _model(d.MainContextPreparedInput, row['input_json'])
    raise ValueError('ASSISTANT_MODEL_INTEGRITY')


def _wire(prepared, config):
    """Deterministic rebuild for the decoded format."""
    if isinstance(prepared, d.MainContextPreparedInput):
        return context_codec.prepare(prepared.request, config).wire_payload_json
    return prepare(prepared.request, config).wire_payload_json


def _row(identifier, db):
    row = db.execute(text('SELECT * FROM assistant_model_attempts WHERE id=:id'),
                     {'id':str(identifier)}).mappings().first()
    if row is None:
        raise ServiceError('CROSS_MATTER_DENIED', 403)
    return row


def _relations(identifier, db):
    return db.execute(text('''SELECT ordinal,saved_citation_id FROM assistant_model_input_citations
        WHERE attempt_id=:id ORDER BY ordinal'''), {'id':str(identifier)}).mappings().all()


def _context_sources_match(row, prepared, db):
    """The persisted ordered selection must equal the immutable input's manifest."""
    relations = _relations(row['id'], db)
    manifest = prepared.request.manifest
    bindings = prepared.request.basis.source_bindings
    if not 1 <= len(relations) <= 8 or len(relations) != len(manifest.sources):
        raise ValueError('ASSISTANT_MODEL_INTEGRITY')
    for ordinal, (relation, source, binding) in enumerate(zip(relations, manifest.sources, bindings)):
        if (relation['ordinal'] != ordinal or relation['saved_citation_id'] != str(source.saved_citation_id)
                or binding.saved_citation_id != source.saved_citation_id):
            raise ValueError('ASSISTANT_MODEL_INTEGRITY')
        digest = db.scalar(text('SELECT citation_sha256 FROM assistant_library_citations WHERE id=:id'),
                           {'id': relation['saved_citation_id']})
        if digest is None or digest != binding.citation_sha256:
            raise ValueError('ASSISTANT_MODEL_INTEGRITY')


def read_attempt(actor, identifier, db):
    row = _row(identifier, db)
    service._owned(actor, UUID(row['conversation_id']), db)
    prepared = _input(row)
    usage = db.scalar(text('SELECT receipt_json FROM assistant_model_receipts WHERE attempt_id=:id'), {'id':row['id']})
    output = db.scalar(text('SELECT output_json FROM assistant_model_outputs WHERE attempt_id=:id'), {'id':row['id']})
    values = dict(id=row['id'], run_id=row['run_id'], scope=prepared.request.scope,
        state=row['state'], reserved_usd=row['reserved_usd'],
        receipt=_model(d.MainReceipt, usage) if usage else None)
    if isinstance(prepared, d.MainContextPreparedInput):
        return validated(d.MainContextAttemptView, dict(values,
            output=_model(d.MainContextOutputView, output) if output else None))
    return validated(d.MainAttemptView, dict(values,
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


def _previous(conversation_id, request_id, db):
    # The submission round is always round 1; later rounds never redefine replay.
    return db.execute(text('''SELECT r.id,a.id AS attempt_id FROM assistant_runs r
        LEFT JOIN assistant_model_attempts a ON a.run_id=r.id AND a.round_no=1
        WHERE r.conversation_id=:cid AND r.request_id=:request'''),
        {'cid':str(conversation_id), 'request':str(request_id)}).mappings().first()


def _replay(actor, conversation_id, message, previous, config, policy, db, *, context,
            citation_ids=None):
    """An old queued message never acquires execution eligibility on retry."""
    if previous['attempt_id'] is None:
        raise ServiceError('STATE_CONFLICT', 409)
    service.save_message(actor, conversation_id, message, db)
    row = _row(previous['attempt_id'], db)
    prepared = _input(row)
    if context != isinstance(prepared, d.MainContextPreparedInput):
        raise ServiceError('VERSION_CONFLICT', 409)
    if (policy is None or row['config_sha256'] != sha(encoded(config))
            or row['policy_sha256'] != sha(encoded(policy))
            or _wire(prepared, config) != prepared.wire_payload_json):
        raise ServiceError('VERSION_CONFLICT', 409)
    if context:
        # The resubmitted ordered selection must equal the registered one;
        # the message digest alone never covers citation_ids.
        persisted = [UUID(item['saved_citation_id']) for item in _relations(row['id'], db)]
        if persisted != list(citation_ids):
            raise ServiceError('VERSION_CONFLICT', 409)
        _context_sources_match(row, prepared, db)
    return read_attempt(actor, UUID(row['id']), db)


def _submission_message(request):
    return d.AssistantMessageInput(request_id=request.request_id, expected_scope=request.expected_scope,
        expected_composer_revision=request.expected_composer_revision, content=request.content)


def enqueue_generation(actor, conversation_id, request, db, runtime):
    request = d.AssistantMessageInput.model_validate(request.model_dump(mode='python'))
    conversation = service._owned(actor, conversation_id, db)
    require_active(db)
    config, policy = runtime.snapshot_for(actor, service._snapshot(conversation))
    runtime.check_submission(actor, request)
    previous = _previous(conversation_id, request.request_id, db)
    if previous:
        return _replay(actor, conversation_id, request, previous, config, policy, db, context=False)
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
             input_json,config_json,policy_json,reserved_usd,created_at,state,updated_at,input_format,round_no)
            VALUES(:id,:run,:cid,:policy,:config_sha,:policy_sha,:request_sha,:input,:config,:policy_json,
                   :reserved,:at,'reserved',:at,'plain-text-v1',1)'''), {'id':str(identifier), 'run':str(run.id),
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


def enqueue_context(actor, conversation_id, request, db, runtime):
    """Register one source-bound answer; the format is fixed by this trusted entry."""
    from ..context_preview import assemble_context
    request = d.MainContextSubmission.model_validate(request.model_dump(mode='python'))
    conversation = service._owned(actor, conversation_id, db)
    require_active(db)
    config, policy = runtime.snapshot_for(actor, service._snapshot(conversation))
    previous = _previous(conversation_id, request.request_id, db)
    if previous:
        return _replay(actor, conversation_id, _submission_message(request), previous,
                       config, policy, db, context=True, citation_ids=request.citation_ids)
    scope, manifest, records = assemble_context(actor, conversation, request.citation_ids, db,
                                                question=request.content)
    # Authorization precedes basis construction: a disabled or missing grant can
    # never describe wire bytes, and the manifest digest alone keys the policy.
    require_policy(config, policy, actor, scope, context_codec.manifest_digest(manifest))
    basis = context_codec.build_basis(request.request_id, manifest, scope,
                                      request.expected_composer_revision, config, records)
    runtime.check_context_submission(actor, request, basis)
    if items(conversation, db):
        raise ServiceError('BLOCKED_LIVE', 403)
    used, calls = _budget(policy, db)
    reserved = reservation(config)
    if add_costs((used,reserved)) > policy.max_total_usd:
        raise ServiceError('BUDGET_EXCEEDED', 403)
    if calls >= policy.max_calls:
        raise ServiceError('CALL_LIMIT_EXCEEDED', 403)
    with db.begin_nested():
        run = service.save_message(actor, conversation_id, _submission_message(request), db)
        prepared = context_codec.prepare(d.MainContextRequest(run_id=run.id, message_id=run.message_id,
            scope=run.scope, composer_revision=request.expected_composer_revision + 1,
            manifest=manifest, basis=basis), config)
        identifier, at = uuid4(), service._at()
        db.execute(text('''INSERT INTO assistant_model_attempts
            (id,run_id,conversation_id,policy_id,config_sha256,policy_sha256,request_sha256,
             input_json,config_json,policy_json,reserved_usd,created_at,state,updated_at,input_format,round_no)
            VALUES(:id,:run,:cid,:policy,:config_sha,:policy_sha,:request_sha,:input,:config,:policy_json,
                   :reserved,:at,'reserved',:at,'library-context-v1',1)'''), {'id':str(identifier),
            'run':str(run.id), 'cid':str(conversation_id), 'policy':str(policy.policy_id),
            'config_sha':sha(encoded(config)), 'policy_sha':sha(encoded(policy)),
            'request_sha':sha(prepared.wire_payload_json), 'input':encoded(prepared),
            'config':encoded(config), 'policy_json':encoded(policy), 'reserved':str(reserved), 'at':at})
        for ordinal, record in enumerate(records):
            db.execute(text('''INSERT INTO assistant_model_input_citations
                (attempt_id,ordinal,saved_citation_id) VALUES(:id,:ordinal,:citation)'''),
                {'id':str(identifier), 'ordinal':ordinal, 'citation':str(record.id)})
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
    prepared = _input(row)
    config, policy = runtime.snapshot_for(actor, prepared.request.scope)
    runtime.check_execution(actor, UUID(run['request_id']), prepared.request)
    if isinstance(prepared, d.MainContextPreparedInput):
        require_policy(config, policy, actor, prepared.request.scope, prepared.request.basis.manifest_sha256)
    else:
        require_policy(config, policy, actor, prepared.request.scope, prepared.request.source_sha256)
    if (str(actor.session_id) != run['session_id'] or run['actor_id'] != str(actor.user_id)
            or conversation['archived_at'] is not None or service._snapshot(conversation) != prepared.request.scope
            or row['config_sha256'] != sha(encoded(config)) or row['policy_sha256'] != sha(encoded(policy))
            or run['cancel_requested'] or run['state'] not in {'queued','generating'}
            or _wire(prepared, config) != prepared.wire_payload_json):
        raise ServiceError('VERSION_CONFLICT', 409)
    if items(conversation, db):
        raise ServiceError('BLOCKED_LIVE', 403)
    if isinstance(prepared, d.MainContextPreparedInput):
        _context_sources_match(row, prepared, db)
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
    prepared = _input(row)
    context = isinstance(prepared, d.MainContextPreparedInput)
    reply = (d.MainContextReply if context else d.MainReply).model_validate(reply.model_dump(mode='python'))
    config = _model(d.MainModelConfig, row['config_json'])
    candidate = reply.output
    outside_envelope = reply.usage is not None and (reply.usage.prompt_tokens > config.max_input_bytes
        or reply.usage.completion_tokens > config.max_output_tokens)
    if context:
        selected = {item.saved_citation_id: item.quote_sha256
                    for item in prepared.request.manifest.sources}
        invalid = any(selected.get(item.saved_citation_id) != item.quote_sha256
                      for item in candidate.citations) if candidate else False
    else:
        invalid = candidate and any(
            c.message_id != prepared.request.message_id or c.quote_sha256 != prepared.request.source_sha256
            for c in candidate.citations)
    if candidate and (outside_envelope or invalid):
        reply = (d.MainContextReply if context else d.MainReply)(
            state='received', provider_request_id=reply.provider_request_id,
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
            view_type = d.MainContextOutputView if context else d.MainOutputView
            output = view_type(id=uuid4(), run_id=row['run_id'], scope=prepared.request.scope,
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
