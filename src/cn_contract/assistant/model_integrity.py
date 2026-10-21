"""Read-only validation of archived model history; never grants execution rights."""
from decimal import Context, Decimal, localcontext
import re
from uuid import UUID

from pydantic import TypeAdapter
from sqlalchemy import text

from .. import domain as d
from ..storage_schema import identify_schema
from .providers.main import _strict_json
from .providers.policy import encoded, estimated_cost, prepare, reservation, sha


def _fail():
    raise ValueError('ASSISTANT_MODEL_INTEGRITY')


def _uuid(value):
    if type(value) is not str or str(UUID(value)) != value:
        _fail()
    return value


def _hash(value):
    if type(value) is not str or not re.fullmatch('[a-f0-9]{64}', value):
        _fail()


def _json(raw, limit=2*1024**2):
    if type(raw) is not str or len(raw.encode('utf-8')) > limit:
        _fail()
    return _strict_json(raw)


def _model(model, raw, limit=2*1024**2):
    result = model.model_validate(_json(raw, limit))
    if encoded(result) != raw:
        _fail()
    return result


def _at(value):
    if type(value) is not str:
        _fail()
    return TypeAdapter(d.UTCDatetime).validate_python(value)


def _receipt(row, stored, output, config, run, created, updated, *, intermediate=False):
    state, claim = row['state'], row['claim_sha256']
    if state not in {'reserved','sending','received','sent_unknown','failed_before_send'}:
        _fail()
    if claim is not None:
        _hash(claim)
    if state == 'reserved' and claim is not None or state in {'sending','received','sent_unknown'} and claim is None:
        _fail()
    if state in {'reserved','sending'}:
        if stored is not None or output is not None or intermediate:
            _fail()
        if run['state'] not in ({'queued','cancelled'} if state == 'reserved' else {'generating'}):
            _fail()
        return None
    if stored is None or _at(stored['created_at']) != updated or updated < created:
        _fail()
    value = _model(d.MainReceipt, stored['receipt_json'], 16384)
    if value.state != state:
        _fail()
    if value.provider_request_id is not None and (not value.provider_request_id.strip()
            or any(ord(char) < 32 for char in value.provider_request_id)):
        _fail()
    if state == 'failed_before_send':
        status, cost = 'not_sent', Decimal(0)
    elif value.usage is None:
        status, cost = 'unknown', None
    else:
        if output is not None and (value.usage.prompt_tokens > config.max_input_bytes
                or value.usage.completion_tokens > config.max_output_tokens):
            _fail()
        status = 'estimated'
        cost = estimated_cost(value.usage.prompt_tokens, value.usage.completion_tokens, config)
    if value.cost_status != status or value.estimated_cost_usd != cost:
        _fail()
    if state != 'received' and (output is not None or value.error_code is None):
        _fail()
    if intermediate:
        # A plan round is a received, error-free, output-free continuation.
        if state != 'received' or value.error_code is not None or output is not None:
            _fail()
    elif output is not None:
        if run['state'] != 'completed' or value.error_code is not None:
            _fail()
    elif run['state'] not in {'failed','cancelled','interrupted'}:
        _fail()
    return value


def _events(db, row, run, value, output):
    events = db.execute(text('''SELECT * FROM assistant_run_events
        WHERE run_id=:run ORDER BY seq'''), {'run':row['run_id']}).mappings().all()
    if any(event['seq'] != sequence for sequence, event in enumerate(events, start=1)):
        _fail()
    events = [event for event in events if event['event_type'].lower().startswith('model.')]
    expected = [('model.reserved', {'attempt_id':row['id'], 'state':'queued'})]
    if row['claim_sha256'] is not None:
        expected.append(('model.started', {'attempt_id':row['id'], 'state':'generating'}))
    if value is not None:
        if run['state'] == 'interrupted':
            expected.append(('model.interrupted', {'attempt_id':row['id'], 'state':'interrupted',
                                                   'cost_status':value.cost_status}))
            if value.error_code != 'BLOCKED_LIVE' or row['state'] not in {'failed_before_send','sent_unknown'}:
                _fail()
        else:
            expected.append(('model.finished', {'attempt_id':row['id'], 'state':run['state'],
                'output_id':output['id'] if output else None, 'cost_status':value.cost_status,
                'error_code':value.error_code}))
    if len(events) != len(expected):
        _fail()
    for event, (kind, payload) in zip(events, expected):
        if (event['event_type'] != kind or event['audience'] != 'internal'
                or _json(event['payload_json'], 16384) != payload
                or _at(event['created_at']) < _at(row['created_at'])):
            _fail()


def _plan_stop_events(db):
    """Load bounded-rounds continuation events; malformed payloads are corruption."""
    plans, stops = {}, {}
    rows = db.execute(text('''SELECT * FROM assistant_run_events
        WHERE event_type IN ('model.tool_plan','model.bounded_stop')
        ORDER BY run_id,seq''')).mappings().all()
    for row in rows:
        if row['audience'] != 'internal':
            _fail()
        payload = _json(row['payload_json'], 262144)
        if type(payload) is not dict:
            _fail()
        attempt_id = payload.get('attempt_id')
        if type(attempt_id) is not str:
            _fail()
        _uuid(attempt_id)
        if row['event_type'] == 'model.tool_plan':
            plan = d.MainContextToolPlan.model_validate(payload.get('plan'))
            plans.setdefault(attempt_id, []).append((row['seq'], plan))
        else:
            if payload.get('reason') not in ('rounds_exhausted', 'tool_limit', 'tool_rejected',
                                             'budget_exhausted'):
                _fail()
            stops.setdefault(row['run_id'], []).append((row['seq'], payload))
    return plans, stops


def _events_rounds(db, run, rows, receipts, outputs, plan_map, stop_map):
    """Whole-run expected model event sequence for a bounded-rounds archive."""
    events = db.execute(text('''SELECT * FROM assistant_run_events
        WHERE run_id=:run ORDER BY seq'''), {'run':run['id']}).mappings().all()
    if any(event['seq'] != sequence for sequence, event in enumerate(events, start=1)):
        _fail()
    events = [event for event in events if event['event_type'].lower().startswith('model.')]
    expected = []
    for row in rows:
        expected.append(('model.reserved', {'attempt_id':row['id'], 'state':'queued'}, row))
        if row['claim_sha256'] is not None:
            expected.append(('model.started', {'attempt_id':row['id'], 'state':'generating'}, row))
        stored = receipts.get(row['id'])
        if stored is None:
            continue
        value = _model(d.MainReceipt, stored['receipt_json'], 16384)
        plans = plan_map.get(row['id'], ())
        if (run['state'] == 'interrupted' and value.error_code == 'BLOCKED_LIVE'
                and row['state'] in ('failed_before_send', 'sent_unknown')):
            expected.append(('model.interrupted', {'attempt_id':row['id'], 'state':'interrupted',
                'cost_status':value.cost_status}, row))
        elif plans:
            expected.append(('model.finished', {'attempt_id':row['id'], 'state':'generating',
                'output_id':None, 'cost_status':value.cost_status, 'error_code':None}, row))
            expected.append(('model.tool_plan', {'attempt_id':row['id'],
                'plan':plans[0][1].model_dump(mode='json')}, row))
        else:
            output = outputs.get(row['id'])
            expected.append(('model.finished', {'attempt_id':row['id'], 'state':run['state'],
                'output_id':output['id'] if output else None, 'cost_status':value.cost_status,
                'error_code':value.error_code}, row))
    for _, payload in stop_map.get(run['id'], ()):
        expected.append(('model.bounded_stop', payload, None))
    if len(events) != len(expected):
        _fail()
    for event, (kind, payload, row) in zip(events, expected):
        if (event['event_type'] != kind or event['audience'] != 'internal'
                or _json(event['payload_json'], 262144) != payload):
            _fail()
        if row is not None and _at(event['created_at']) < _at(row['created_at']):
            _fail()


def _validate_rounds_replay(db, run_id, ordered, prepareds, plan_map):
    """Bind plan events, tool calls, receipts and next-round inputs exactly.

    Non-final plan rounds bind every planned call to a receipt which the next
    round input replays. A trailing plan round (in-flight pause or bounded
    stop) may show only a prefix of executed calls; a rejected final call can
    leave its tool.before event without a receipt.
    """
    from .library_records import receipt_view
    from .providers.rounds_codec import project_outcome
    mixed = db.execute(text('''SELECT * FROM assistant_run_events
        WHERE run_id=:run AND event_type IN ('tool.before','model.tool_plan')
        ORDER BY seq'''), {'run': run_id}).mappings().all()
    position = 0
    for index, row in enumerate(ordered, start=1):
        plans = plan_map.get(row['id'])
        if not plans:
            continue
        plan_seq, plan = plans[0]
        if position >= len(mixed) or mixed[position]['event_type'] != 'model.tool_plan':
            _fail()
        if mixed[position]['seq'] != plan_seq:
            _fail()
        position += 1
        exchange = None
        if index < len(ordered):
            following = prepareds[ordered[index]['id']]
            if type(following) is not d.MainContextRoundsPreparedInput:
                _fail()
            exchange = following.exchanges[index - 1]
            if exchange.round_no != index or exchange.plan != plan:
                _fail()
        executed = 0
        while position < len(mixed) and mixed[position]['event_type'] == 'tool.before':
            if executed >= len(plan.calls):
                _fail()
            planned = plan.calls[executed]
            event = mixed[position]
            call = d.LibraryHandlerEvent.model_validate(_json(event['payload_json'], 16384))
            if (call.handler_id != planned.tool or call.request.tool != planned.tool
                    or call.request.query != planned.query
                    or call.request.saved_citation_id != planned.saved_citation_id):
                _fail()
            receipt_row = db.execute(text('''SELECT * FROM assistant_handler_receipts
                WHERE run_id=:run AND event_seq=:seq AND handler_id=:handler
                AND handler_version='1' '''), {'run': run_id, 'seq': event['seq'],
                'handler': call.handler_id}).mappings().first()
            if exchange is not None:
                if receipt_row is None:
                    _fail()
                if project_outcome(receipt_view(receipt_row)) != exchange.outcomes[executed]:
                    _fail()
            executed += 1
            position += 1
        if exchange is not None and executed != len(plan.calls):
            _fail()
    if position != len(mixed):
        _fail()


def _validate(db, attempts, receipts, outputs, workspace, *, context_schema, rounds=False):
    from . import context_integrity
    run_attempts = {}
    prepareds = {}
    plan_map, stop_map = _plan_stop_events(db) if rounds else ({}, {})
    conversations = {r['id']:r for r in db.execute(text('SELECT * FROM assistant_conversations')).mappings()}
    messages = {r['id']:r for r in db.execute(text('SELECT * FROM assistant_messages')).mappings()}
    runs = {r['id']:r for r in db.execute(text('SELECT * FROM assistant_runs')).mappings()}
    sessions = {r['id']:r for r in db.execute(text('SELECT id,user_id FROM sessions')).mappings()}
    users = set(db.scalars(text('SELECT id FROM users')))
    policies = {}
    relations = 0
    for row in attempts:
        identifier, cid, run_id = (_uuid(row[key]) for key in ('id','conversation_id','run_id'))
        if rounds:
            # rounds rows carry the immutable round occupancy column; v1
            # archives define no intermediate-round semantics and fail closed
            # after the loop, while v2 archives bind plans, tools and inputs.
            round_no = row['round_no']
            if type(round_no) is not int or not 1 <= round_no <= 4:
                _fail()
            run_attempts.setdefault(run_id, []).append(row)
        for key in ('config_sha256','policy_sha256','request_sha256'):
            _hash(row[key])
        config = _model(d.MainModelConfig, row['config_json'], 32768)
        policy = _model(d.MainModelPolicy, row['policy_json'], 131072)
        # Only a positively identified context schema may carry the format column;
        # older schemas are historical V1 by definition, never by fallback.
        fmt = row['input_format'] if context_schema else 'plain-text-v1'
        allowed = ('plain-text-v1', 'library-context-v1')
        if rounds == 'v2':
            allowed = allowed + ('library-context-v2',)
        if fmt not in allowed:
            _fail()
        context = fmt in ('library-context-v1', 'library-context-v2')
        if fmt == 'library-context-v2':
            prepared = _model(d.MainContextRoundsPreparedInput, row['input_json'])
            if prepared.round_no != row['round_no']:
                _fail()
        elif fmt == 'library-context-v1':
            prepared = _model(d.MainContextPreparedInput, row['input_json'])
        else:
            prepared = _model(d.MainPreparedInput, row['input_json'])
        if context and prepared.request.basis.input_format != fmt:
            _fail()
        prepareds[identifier] = prepared
        request, scope = prepared.request, prepared.request.scope
        source_sha = request.basis.manifest_sha256 if context else request.source_sha256
        question = request.manifest.question if context else request.content
        conversation, run = conversations.get(cid), runs.get(run_id)
        message = messages.get(str(request.message_id))
        if conversation is None or run is None or message is None:
            _fail()
        actor, session = _uuid(run['actor_id']), sessions.get(_uuid(run['session_id']))
        _uuid(conversation['id']); _uuid(conversation['owner_id']); _uuid(message['id'])
        _uuid(run['request_id']); _hash(run['request_sha256'])
        if (actor not in users or session is None or session['user_id'] != actor
                or actor != conversation['owner_id'] or run['conversation_id'] != cid
                or conversation['workspace_id'] != workspace or str(scope.workspace_id) != workspace
                or str(scope.conversation_id) != cid or str(request.run_id) != run_id
                or run['message_id'] != str(request.message_id) or message['conversation_id'] != cid
                or message['role'] != 'user' or message['content'] != question
                or message['source_revision'] != scope.input_revision
                or _model(d.ScopeSnapshot, run['scope_snapshot']) != scope
                or scope.scope_kind != conversation['scope_kind']
                or (str(scope.scope_ref) if scope.scope_ref else None) != conversation['scope_ref']
                or scope.binding_revision != conversation['binding_revision']
                or scope.input_revision > conversation['input_revision']
                or scope.materials_revision > conversation['materials_revision']):
            _fail()
        if scope.scope_kind != 'conversation':
            table = 'matters' if scope.scope_kind == 'matter' else 'intake_cases'
            target = db.execute(text(f'SELECT * FROM {table} WHERE id=:id'), {'id':str(scope.scope_ref)}).mappings().first()
            if target is None or scope.scope_kind == 'intake' and target['owner_id'] != actor:
                _fail()
        # Current attachments may have changed after this historical input.
        if scope.materials_revision:
            snapshot = db.scalar(text('''SELECT items_json FROM assistant_material_snapshots
                WHERE conversation_id=:cid AND revision=:revision'''), {'cid':cid,'revision':scope.materials_revision})
            if snapshot != '[]':
                _fail()
        created, updated = _at(row['created_at']), _at(row['updated_at'])
        if (not _at(conversation['created_at']) <= _at(message['created_at']) == _at(run['created_at']) <= created <= updated
                or not config.enabled or str(policy.policy_id) != _uuid(row['policy_id'])
                or str(policy.workspace_id) != workspace or str(policy.actor_id) != actor
                or policy.config_sha256 != row['config_sha256'] or policy.expires_at <= created
                or source_sha not in policy.allowed_content_sha256s
                or sha(encoded(config)) != row['config_sha256'] or sha(encoded(policy)) != row['policy_sha256']
                or run['selected_provider'] != config.provider or run['selected_model'] != config.model):
            _fail()
        if context:
            context_integrity.validate_context_input(row, prepared, config)
            context_integrity.validate_context_selection(db, row, prepared)
            relations += len(request.manifest.sources)
        else:
            if (sha(prepared.wire_payload_json) != row['request_sha256']
                    or prepare(request, config).wire_payload_json != prepared.wire_payload_json):
                _fail()
            if context_schema and db.scalar(text(
                    'SELECT COUNT(*) FROM assistant_model_input_citations WHERE attempt_id=:id'),
                    {'id': row['id']}):
                _fail()
        reserved = TypeAdapter(d.MainUSD).validate_python(row['reserved_usd'])
        if reserved != reservation(config) or reserved > policy.max_total_usd or _json(run['budget_json'], 16384) != {
                'policy_id':row['policy_id'], 'reserved_usd':str(reserved), 'unit':'USD'}:
            _fail()
        output = outputs.get(identifier)
        intermediate = identifier in plan_map
        value = _receipt(row, receipts.get(identifier), output, config, run, created, updated,
                         intermediate=intermediate)
        if rounds != 'v2':
            _events(db, row, run, value, output)
        if output is not None:
            view = _model(d.MainContextOutputView if context else d.MainOutputView,
                          output['output_json'], 262144)
            if (_uuid(output['id']) != str(view.id) or output['conversation_id'] != cid
                    or output['run_id'] != run_id or view.run_id != request.run_id
                    or _model(d.ScopeSnapshot, output['scope_json']) != scope or view.scope != scope
                    or _at(output['created_at']) != view.created_at or view.created_at != updated):
                _fail()
            if context:
                context_integrity.validate_context_output(view, prepared)
            elif any(c.message_id != request.message_id or c.quote_sha256 != request.source_sha256
                     for c in view.candidate.citations):
                _fail()
        old_policy, calls = policies.get(row['policy_id'], (row['policy_sha256'], 0))
        if old_policy != row['policy_sha256']:
            _fail()
        if row['state'] != 'failed_before_send':
            calls += 1
        # Vendor usage can exceed the reserved ceiling. Preserve that receipt;
        # only subsequent execution is blocked by the runtime budget ledger.
        if calls > policy.max_calls:
            _fail()
        policies[row['policy_id']] = old_policy, calls
    if context_schema:
        # No orphaned or extra relation rows beyond the validated manifests.
        total = db.scalar(text('SELECT COUNT(*) FROM assistant_model_input_citations'))
        if total != relations:
            _fail()
        owners = set(db.scalars(text('SELECT DISTINCT attempt_id FROM assistant_model_input_citations')))
        if not owners <= {r['id'] for r in attempts}:
            _fail()
    if rounds == 'v1':
        # The v1 ledger never defined intermediate-round semantics: single only.
        if plan_map or stop_map:
            _fail()
        for run_id, rows in run_attempts.items():
            if len(rows) != 1 or rows[0]['round_no'] != 1:
                _fail()
    if rounds == 'v2':
        for run_id, rows in run_attempts.items():
            ordered = sorted(rows, key=lambda item: item['round_no'])
            if [item['round_no'] for item in ordered] != list(range(1, len(ordered) + 1)):
                _fail()
            if len(ordered) > 1 and any(item['input_format'] != 'library-context-v2'
                                        for item in ordered):
                _fail()
            run = runs[run_id]
            for row in ordered[:-1]:
                # Every non-final round must carry exactly one persisted plan.
                if len(plan_map.get(row['id'], ())) != 1:
                    _fail()
            last = ordered[-1]
            last_plans = plan_map.get(last['id'], ())
            if len(last_plans) > 1:
                _fail()
            stops = stop_map.get(run_id, ())
            if len(stops) > 1:
                _fail()
            if last_plans:
                if stops:
                    stop_seq, payload = stops[0]
                    if (run['state'] != 'failed' or payload['attempt_id'] != last['id']
                            or stop_seq < last_plans[0][0]):
                        _fail()
                    if payload['reason'] == 'rounds_exhausted':
                        last_policy = _model(d.MainModelPolicy, last['policy_json'], 131072)
                        if last['round_no'] != last_policy.max_calls:
                            _fail()
                elif run['state'] not in ('generating', 'interrupted') or last['round_no'] == 4:
                    _fail()
            elif stops:
                _fail()
            _events_rounds(db, run, ordered, receipts, outputs, plan_map, stop_map)
            _validate_rounds_replay(db, run_id, ordered, prepareds, plan_map)


def validate_model_records(db, *, allowed=True):
    """Validate every model record; skip only positively identified older schemas."""
    schema = [tuple(row) for row in db.execute(text(
        'SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name'))]
    native = any(row[0] == 'table' and row[1] == 'local_workspace_identity' for row in schema)
    version = identify_schema(schema, native=native)
    if version in ('pre-intake','intake-v1','assistant-v1','assistant-attachments-v1'):
        return
    if version not in ('assistant-model-v1', 'assistant-judge-v1', 'assistant-library-v1',
                       'assistant-context-v1', 'assistant-rounds-v1', 'assistant-rounds-v2'):
        raise ValueError('DATABASE_SCHEMA_MISMATCH')
    attempts = db.execute(text('SELECT * FROM assistant_model_attempts ORDER BY created_at,id')).mappings().all()
    receipts = {r['attempt_id']:r for r in db.execute(text('SELECT * FROM assistant_model_receipts')).mappings()}
    outputs = {r['attempt_id']:r for r in db.execute(text('SELECT * FROM assistant_model_outputs')).mappings()}
    model_runs = set(db.scalars(text('''SELECT id FROM assistant_runs r WHERE selected_provider IS NOT NULL
        OR selected_model IS NOT NULL OR budget_json IS NOT NULL OR EXISTS (
            SELECT 1 FROM assistant_run_events e WHERE e.run_id=r.id AND e.event_type LIKE 'model.%')''')))
    if model_runs != {r['run_id'] for r in attempts}:
        _fail()
    if not attempts and not receipts and not outputs:
        return
    if not allowed:
        raise ValueError('ASSISTANT_MODELS_REQUIRE_QXBAK')
    identities = db.scalars(text('SELECT id FROM local_workspace_identity')).all() if native else []
    if len(identities) != 1:
        _fail()
    if not (set(receipts) | set(outputs)) <= {r['id'] for r in attempts}:
        _fail()
    try:
        # Pydantic decimal digit validation also normalizes using this context.
        with localcontext(Context(prec=60)):
            _validate(db, attempts, receipts, outputs, _uuid(identities[0]),
                      context_schema=version in ('assistant-context-v1', 'assistant-rounds-v1',
                                                 'assistant-rounds-v2'),
                      rounds=('v2' if version == 'assistant-rounds-v2'
                              else 'v1' if version == 'assistant-rounds-v1' else False))
    except (ValueError, TypeError, KeyError, ArithmeticError, RecursionError):
        # Archive errors must not interpolate source text or model bodies.
        raise ValueError('ASSISTANT_MODEL_INTEGRITY') from None
