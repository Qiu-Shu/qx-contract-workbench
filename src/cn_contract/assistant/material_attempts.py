"""Material-purpose adapter for the existing single-claim model ledger."""
import logging
from uuid import UUID, uuid4
from sqlalchemy import text
from .. import domain as d
from ..config import canonical_json
from ..security import ServiceError
from ..ops.storage import require_active
from . import service, material_codec as codec, material_preparation as inputs
from .providers import attempts
from .providers.policy import encoded, sha, require_policy, reservation, add_costs, receipt, budget_exceeded

_logger = logging.getLogger(__name__)


def message(basis):
    return d.AssistantMessageInput(request_id=basis.request_id, expected_scope=basis.expected_scope,
        expected_composer_revision=basis.expected_composer_revision, content=basis.manifest.question)


def enqueue(actor, selection, basis, db, runtime):
    cid = selection.expected_scope.conversation_id
    conversation = service._owned(actor, cid, db)
    require_active(db)
    config, policy = runtime.snapshot_for(actor, selection.expected_scope)
    runtime.check_material_submission(actor, basis)
    previous = attempts._previous(cid, selection.request_id, db)
    if previous:
        row = attempts._row(previous['attempt_id'], db)
        prepared = attempts._input(row)
        if type(prepared) is not d.MainMaterialPreparedInput or prepared.request.basis != basis:
            raise ServiceError('VERSION_CONFLICT', 409)
        return attempts.read_attempt(actor, UUID(row['id']), db)
    manifest, _ = inputs.assemble(actor, selection, db)
    if codec.build_basis(selection, manifest, config) != basis:
        raise ServiceError('VERSION_CONFLICT', 409)
    require_policy(config, policy, actor, selection.expected_scope, basis.manifest_sha256)
    used, calls = attempts._budget(policy, db)
    reserved = reservation(config)
    if calls >= policy.max_calls or budget_exceeded(add_costs((used, reserved)), policy.max_total_usd):
        raise ServiceError('BUDGET_EXCEEDED', 403)
    with db.begin_nested():
        run = service.save_message(actor, cid, message(basis), db)
        prepared = codec.prepare(d.MainMaterialRequest(run_id=run.id, message_id=run.message_id,
            scope=run.scope, basis=basis), config)
        identifier, at = uuid4(), service._at()
        db.execute(text('''INSERT INTO assistant_model_attempts
            (id,run_id,conversation_id,policy_id,config_sha256,policy_sha256,request_sha256,
             input_json,config_json,policy_json,reserved_usd,created_at,state,updated_at,input_format,round_no)
            VALUES(:id,:run,:cid,:policy,:config_sha,:policy_sha,:request_sha,:input,:config,:policy_json,
                   :reserved,:at,'reserved',:at,'material-business-v1',1)'''),
            {'id':str(identifier), 'run':str(run.id), 'cid':str(cid), 'policy':str(policy.policy_id),
             'config_sha':sha(encoded(config)), 'policy_sha':sha(encoded(policy)), 'request_sha':sha(prepared.wire_payload_json),
             'input':encoded(prepared), 'config':encoded(config), 'policy_json':encoded(policy), 'reserved':str(reserved), 'at':at})
        db.execute(text('UPDATE assistant_runs SET selected_provider=:provider,selected_model=:model,budget_json=:budget WHERE id=:id'),
            {'id':str(run.id), 'provider':config.provider, 'model':config.model,
             'budget':canonical_json({'policy_id':str(policy.policy_id), 'reserved_usd':str(reserved), 'unit':'USD'})})
        attempts._event(run.id, 'model.reserved', {'attempt_id':str(identifier), 'state':'queued'}, db)
    return attempts.read_attempt(actor, identifier, db)


def current(actor, row, db, runtime):
    require_active(db)
    prepared = attempts._input(row)
    request, basis = prepared.request, prepared.request.basis
    from ..weixin_inbox.runtime_records import require_model_source
    require_model_source(actor, basis, db)
    run = service._owned_run(actor, request.run_id, db)
    inputs.require_parent_active(service._owned_run(actor, basis.parent_business_run_id, db))
    conversation = service._owned(actor, request.scope.conversation_id, db)
    config, policy = runtime.snapshot_for(actor, request.scope)
    runtime.check_material_submission(actor, basis)
    require_policy(config, policy, actor, request.scope, basis.manifest_sha256)
    manifest, _ = inputs.assemble(actor, inputs.selection_for(basis), db, historical=True)
    if (manifest != basis.manifest or service._snapshot(conversation) != request.scope
            or conversation['archived_at'] is not None or run['cancel_requested']
            or run['state'] not in ('queued', 'generating') or run['actor_id'] != str(actor.user_id)
            or run['session_id'] != str(actor.session_id) or codec.prepare(request, config) != prepared
            or row['config_sha256'] != sha(encoded(config)) or row['policy_sha256'] != sha(encoded(policy))):
        raise ServiceError('VERSION_CONFLICT', 409)
    return prepared, config


def settle(actor, identifier, token, reply, db, runtime):
    row = attempts._row(identifier, db)
    if row['state'] != 'sending' or row['claim_sha256'] != sha(token):
        raise ServiceError('STATE_CONFLICT', 409)
    prepared = attempts._input(row)
    config = attempts._model(d.MainModelConfig, row['config_json'])
    reply = d.MainMaterialReply.model_validate(reply.model_dump(mode='python'))
    candidate = reply.output
    if candidate is not None:
        try:
            codec.validate_candidate(candidate, prepared.request.basis.manifest.sources)
            if reply.usage and (reply.usage.prompt_tokens > config.max_input_bytes or reply.usage.completion_tokens > config.max_output_tokens):
                raise ValueError
        except ValueError:
            _logger.warning('model_response_rejected stage=material_settle_candidate')
            reply = d.MainMaterialReply(state='received', usage=reply.usage,
                provider_request_id=reply.provider_request_id, error_code='MODEL_OUTPUT_INVALID')
            candidate = None
    try:
        current(actor, row, db, runtime)
    except (ServiceError, ValueError):
        _logger.warning('model_response_rejected stage=material_settle_current')
        candidate = None
    require_active(db)
    checked = attempts._row(identifier, db)
    if checked['state'] != 'sending' or checked['claim_sha256'] != sha(token):
        raise ServiceError('STATE_CONFLICT', 409)
    at, value, output_id = service._at(), receipt(reply, config), None
    with db.begin_nested():
        db.execute(text('INSERT INTO assistant_model_receipts VALUES(:id,:receipt,:at)'), {'id':row['id'], 'receipt':encoded(value), 'at':at})
        db.execute(text('UPDATE assistant_model_attempts SET state=:state,updated_at=:at WHERE id=:id'),
            {'state':reply.state, 'at':at, 'id':row['id']})
        if candidate is not None:
            output = d.MainMaterialOutputView(id=uuid4(), run_id=row['run_id'], scope=prepared.request.scope,
                candidate=candidate, manifest=prepared.request.basis.manifest, created_at=at)
            output_id = str(output.id)
            db.execute(text('INSERT INTO assistant_model_outputs VALUES(:id,:attempt,:cid,:run,:scope,:output,:at)'),
                {'id':output_id, 'attempt':row['id'], 'cid':row['conversation_id'], 'run':row['run_id'],
                 'scope':encoded(output.scope), 'output':encoded(output), 'at':at})
        cancelled = db.scalar(text('SELECT cancel_requested FROM assistant_runs WHERE id=:id'), {'id':row['run_id']})
        state = 'completed' if candidate is not None else 'cancelled' if cancelled else 'failed'
        db.execute(text('UPDATE assistant_runs SET state=:state WHERE id=:id'), {'state':state, 'id':row['run_id']})
        attempts._event(row['run_id'], 'model.finished', {'attempt_id':row['id'], 'state':state,
            'output_id':output_id, 'cost_status':value.cost_status, 'error_code':value.error_code}, db)
