"""Archive validation for independent Jev history; never grants execution."""
from decimal import Context, Decimal, localcontext
import re
from typing import get_args
from uuid import UUID

from pydantic import TypeAdapter
from sqlalchemy import text

from .. import domain as d
from ..review.model_adapter import strict_json
from ..security import ServiceError
from ..storage_schema import identify_schema
from .providers import jev_codec
from .providers.judge_policy import encoded, receipt, sha, total
from .routing import choose_workflow


def _fail():
    raise ValueError('ASSISTANT_JUDGE_INTEGRITY')


def _uuid(value):
    if type(value) is not str or str(UUID(value)) != value:
        _fail()
    return value


def _hash(value):
    if type(value) is not str or not re.fullmatch('[a-f0-9]{64}', value):
        _fail()


def _model(kind, raw):
    value = kind.model_validate(strict_json(raw))
    if encoded(value) != raw:
        _fail()
    return value


def _at(value):
    return TypeAdapter(d.UTCDatetime).validate_python(value)


def _validate(db, attempts, receipts, decisions, workspace):
    conversations = {r['id']:r for r in db.execute(text('SELECT * FROM assistant_conversations')).mappings()}
    messages = {r['id']:r for r in db.execute(text('SELECT * FROM assistant_messages')).mappings()}
    runs = {r['id']:r for r in db.execute(text('SELECT * FROM assistant_runs')).mappings()}
    sessions = {r['id']:r['user_id'] for r in db.execute(text('SELECT id,user_id FROM sessions')).mappings()}
    users = set(db.scalars(text('SELECT id FROM users')))
    policies = {}
    for row in attempts:
        for key in ('id','run_id','conversation_id','message_id','actor_id','session_id','policy_id','authorization_id'):
            _uuid(row[key])
        for key in ('config_sha256','policy_sha256','input_hash','source_sha256'):
            _hash(row[key])
        request = _model(d.JudgeRequest, row['request_json'])
        config = _model(d.JevConfig, row['config_json'])
        policy = _model(d.JudgePolicy, row['policy_json'])
        scope = request.scope
        run, conversation, message = runs.get(row['run_id']), conversations.get(row['conversation_id']), messages.get(row['message_id'])
        if run is None or conversation is None or message is None:
            _fail()
        if (row['actor_id'] not in users or sessions.get(row['session_id']) != row['actor_id']
                or run['actor_id'] != row['actor_id'] or run['session_id'] != row['session_id']
                or conversation['owner_id'] != row['actor_id'] or conversation['workspace_id'] != workspace
                or run['conversation_id'] != row['conversation_id'] or run['message_id'] != row['message_id']
                or message['conversation_id'] != row['conversation_id'] or message['role'] != 'user'
                or str(request.local_request_id) != _uuid(run['request_id'])
                or str(scope.workspace_id) != workspace or str(scope.conversation_id) != row['conversation_id']
                or _model(d.ScopeSnapshot, run['scope_snapshot']) != scope
                or request.text != message['content'] or message['source_revision'] != scope.input_revision
                or row['source_sha256'] != sha(request.text) or request.explicit_skill is not None
                or run['requested_skill'] is not None or row['purpose'] != request.purpose
                or request.purpose != 'primary_intent' or scope.scope_kind != conversation['scope_kind']
                or (str(scope.scope_ref) if scope.scope_ref else None) != conversation['scope_ref']
                or scope.binding_revision != conversation['binding_revision']
                or scope.input_revision > conversation['input_revision']
                or scope.materials_revision > conversation['materials_revision']):
            _fail()
        _hash(run['request_sha256'])
        if scope.scope_kind != 'conversation':
            table = 'matters' if scope.scope_kind == 'matter' else 'intake_cases'
            target = db.execute(text(f'SELECT * FROM {table} WHERE id=:id'), {'id':str(scope.scope_ref)}).mappings().first()
            if target is None or scope.scope_kind == 'intake' and target['owner_id'] != row['actor_id']:
                _fail()
        if scope.materials_revision:
            raw = db.scalar(text('SELECT items_json FROM assistant_material_snapshots WHERE conversation_id=:cid AND revision=:rev'),
                            {'cid':row['conversation_id'], 'rev':scope.materials_revision})
            if raw != '[]':
                _fail()
        created, updated = _at(row['created_at']), _at(row['updated_at'])
        if (not _at(conversation['created_at']) <= _at(message['created_at']) == _at(run['created_at']) <= created <= updated
                or not config.enabled or str(policy.policy_id) != row['policy_id']
                or str(policy.workspace_id) != workspace or str(policy.actor_id) != row['actor_id']
                or str(policy.session_id) != row['session_id'] or policy.expires_at <= created
                or policy.config_sha256 != row['config_sha256'] or sha(encoded(config)) != row['config_sha256']
                or sha(encoded(policy)) != row['policy_sha256'] or jev_codec.input_hash(request, config) != row['input_hash']
                or not any(p.local_request_id == request.local_request_id and p.purpose == request.purpose
                           and p.input_hash == row['input_hash'] for p in policy.permissions)):
            _fail()
        jev_codec.build_request(request, config)
        reserved = TypeAdapter(d.JudgeUSD).validate_python(row['reserved_usd'])
        if reserved != policy.reserved_usd or str(reserved) != row['reserved_usd']:
            _fail()
        state, claim = row['state'], row['claim_sha256']
        if claim is not None:
            _hash(claim)
        if (state == 'reserved' and claim is not None or
                state in {'sending','sent_unknown','received'} and claim is None):
            _fail()
        stored, decision = receipts.get(row['id']), decisions.get(row['id'])
        if state in {'reserved','sending'}:
            if stored is not None or decision is not None:
                _fail()
        elif state in {'not_sent','sent_unknown','received'}:
            if stored is None or _at(stored['created_at']) != updated:
                _fail()
            value = _model(d.JudgeReceipt, stored['receipt_json'])
            result = value.result
            if (result.evidence != state or result.local_request_id != request.local_request_id
                    or result.scope != scope or result.input_hash != row['input_hash']
                    or value != receipt(result, reserved)):
                _fail()
            if result.provider_request_id is not None and (not result.provider_request_id.strip()
                    or any(ord(char) < 32 or 127 <= ord(char) <= 159 for char in result.provider_request_id)):
                _fail()
            if decision is not None:
                view = _model(d.JudgeDecisionView, decision['decision_json'])
                if (result.status != 'ok' or set(result.answers) != {request.purpose}
                        or result.elapsed_ms >= config.timeout_ms or updated >= policy.expires_at
                        or view.attempt_id != UUID(row['id'])
                        or view.run_id != UUID(row['run_id']) or view.scope != scope
                        or _at(decision['created_at']) != updated or view.created_at != updated
                        or view.decision != choose_workflow(None, result, get_args(d.AssistantSkill))):
                    _fail()
        else:
            _fail()
        prior, costs = policies.setdefault(row['policy_id'], (row['policy_sha256'], []))
        if prior != row['policy_sha256']:
            _fail()
        if state != 'not_sent':
            costs.append(reserved)
        if len(costs) > policy.max_calls or total(costs) > policy.max_total_usd:
            _fail()


def validate_judge_records(db, *, allowed=True):
    """Only known older schemas skip; live grants are irrelevant to historical proof."""
    schema = [tuple(row) for row in db.execute(text('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name'))]
    native = any(row[0] == 'table' and row[1] == 'local_workspace_identity' for row in schema)
    version = identify_schema(schema, native=native)
    if version in ('pre-intake','intake-v1','assistant-v1','assistant-attachments-v1','assistant-model-v1'):
        return
    if version not in ('assistant-judge-v1', 'assistant-library-v1', 'assistant-context-v1',
                       'assistant-rounds-v1', 'assistant-rounds-v2', 'assistant-profiles-v1',
                       'assistant-profile-model-v1', 'task-drafts-v1', 'weixin-inbox-v1', 'weixin-dispatch-v1', 'weixin-reauthorization-v1', 'weixin-generations-v1', 'weixin-target-provenance-v1', 'weixin-generation-dispatch-v1'):
        raise ValueError('DATABASE_SCHEMA_MISMATCH')
    attempts = db.execute(text('SELECT * FROM assistant_judge_attempts ORDER BY created_at,id')).mappings().all()
    receipts = {r['attempt_id']:r for r in db.execute(text('SELECT * FROM assistant_judge_receipts')).mappings()}
    decisions = {r['attempt_id']:r for r in db.execute(text('SELECT * FROM assistant_judge_decisions')).mappings()}
    if not attempts and not receipts and not decisions:
        return
    if not allowed:
        raise ValueError('ASSISTANT_JUDGES_REQUIRE_QXBAK')
    identities = db.scalars(text('SELECT id FROM local_workspace_identity')).all() if native else []
    if len(identities) != 1 or not (set(receipts) | set(decisions)) <= {r['id'] for r in attempts}:
        _fail()
    try:
        with localcontext(Context(prec=60)):
            _validate(db, attempts, receipts, decisions, _uuid(identities[0]))
    except (ServiceError, ValueError, KeyError, TypeError, ArithmeticError, RecursionError):
        raise ValueError('ASSISTANT_JUDGE_INTEGRITY') from None
