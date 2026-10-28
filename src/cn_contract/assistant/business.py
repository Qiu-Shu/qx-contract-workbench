"""Local business preparation on the existing conversation run/event ledger.

This entry never calls a model or treats a local result as model output.
"""
from uuid import UUID, NAMESPACE_URL, uuid4, uuid5
import json

from sqlalchemy import text

from .. import domain as d
from ..config import canonical_json
from ..ops.storage import require_active
from ..record_codec import sha
from ..security import ServiceError
from . import service, profile_store, reception_worksheet
from .research import _append
from . import business_preparation as preparation


def classify(content):
    choices = []
    if any(word in content for word in ('客户咨询', '接待客户', '客户的咨询', '客户诉求', '销售接待')):
        choices.append('sales')
    if any(word in content for word in ('整理案件', '整理这个案件', '整理材料', '整理证据', '时间线', '事实线索', '起草起诉状', '起草答辩状')):
        choices.append('case')
    if (any(word in content for word in ('审查合同', '审查这个合同', '审阅合同', '审查这份合同', '合同审查', '重新审查'))
            or any(word in content for word in ('我是甲方', '我是乙方', '代表甲方', '代表乙方'))
            and any(word in content for word in ('审查', '审阅', '修改'))):
        choices.append('contract')
    if any(word in content for word in ('模拟法庭', '模拟开庭', '模拟对方律师', '法官角度', '对方律师和法官', '庭审准备')):
        choices.append('court')
    return choices[0] if len(choices) == 1 else 'ambiguous' if choices else None


def continuing(content):
    return any(word in content for word in ('继续', '补充', '这次任务', '这个任务', '上述', '刚才'))


def _record(run, db):
    events = db.execute(text('SELECT * FROM assistant_run_events WHERE run_id=:id ORDER BY seq'),
                        {'id': run['id']}).mappings().all()
    business = [event for event in events if event['event_type'].lower().startswith('business.')]
    if not business:
        return None
    if ([event['event_type'] for event in business] != ['business.accepted', 'business.result']
            or [event['seq'] for event in business] != [2, 3] or len(events) not in (3, 4)):
        raise ValueError('BUSINESS_RECORD_INVALID')
    accepted = d.BusinessAccepted.model_validate_json(business[0]['payload_json'])
    record = d.BusinessResultRecord.model_validate_json(business[1]['payload_json'])
    result, request = record.result, accepted.request
    scope = d.ScopeSnapshot.model_validate_json(run['scope_snapshot'])
    effective_state = result.state
    if len(events) == 4:
        last = events[-1]
        payload = json.loads(last['payload_json'])
        if last['seq'] != 4 or result.state != 'awaiting_input' or last['audience'] != 'internal':
            raise ValueError('BUSINESS_RECORD_INVALID')
        if last['event_type'] == 'run.cancelled':
            UUID(payload['request_id'])
            if payload != {'request_id':payload['request_id'], 'previous_state':'awaiting_input',
                           'state':'cancelled', 'cancel_requested':True} or run['cancel_requested'] != 1:
                raise ValueError('BUSINESS_RECORD_INVALID')
            effective_state = 'cancelled'
        elif last['event_type'] == 'restore.quarantined':
            if payload != {'previous_state':'awaiting_input', 'reason':'restored_read_only', 'state':'blocked'}:
                raise ValueError('BUSINESS_RECORD_INVALID')
            effective_state = 'blocked'
        else:
            raise ValueError('BUSINESS_RECORD_INVALID')
    if (record.result_sha256 != sha(result.model_dump(mode='json'))
            or accepted.scope != scope or result.scope != scope
            or accepted.workflow != result.workflow or accepted.task_id != result.task_id
            or str(result.run_id) != run['id'] or str(result.message_id) != run['message_id']
            or str(result.request_id) != run['request_id'] or result.request_id != request.request_id
            or effective_state != run['state'] or run['selected_provider'] is not None or run['requested_skill'] is not None
            or run['selected_model'] is not None or run['budget_json'] is not None
            or scope != request.expected_scope.model_copy(update={'input_revision':request.expected_scope.input_revision + 1})):
        raise ValueError('BUSINESS_RECORD_INVALID')
    message = db.execute(text('SELECT * FROM assistant_messages WHERE id=:id'),
                         {'id':run['message_id']}).mappings().one()
    original = _message(request)
    digest = service._digest({'actor_id':run['actor_id'], 'workspace_id':str(scope.workspace_id),
        'conversation_id':run['conversation_id'], 'request':original.model_dump(mode='json')})
    if (message['content'] != request.content or message['role'] != 'user'
            or message['source_revision'] != scope.input_revision
            or message['conversation_id'] != run['conversation_id'] or digest != run['request_sha256']):
        raise ValueError('BUSINESS_RECORD_INVALID')
    from .profile_integrity import _scope, _at
    conversation = db.execute(text('SELECT * FROM assistant_conversations WHERE id=:id'),
        {'id':run['conversation_id']}).mappings().one()
    _scope(db, scope, conversation, conversation['workspace_id'], result.created_at)
    session_owner = db.scalar(text('SELECT user_id FROM sessions WHERE id=:id'), {'id':run['session_id']})
    if (session_owner != run['actor_id'] or run['actor_id'] != conversation['owner_id'] or events[0]['event_type'] != 'message.accepted'
            or json.loads(events[0]['payload_json']) != {'message_id':run['message_id'],
                'input_revision':scope.input_revision, 'state':'queued'}
            or any(event['audience'] != 'internal' for event in events)
            or _at(run['created_at']) > result.created_at
            or _at(business[0]['created_at']) > result.created_at
            or _at(business[1]['created_at']) < result.created_at
            or any(_at(a['created_at']) > _at(b['created_at']) for a, b in zip(events, events[1:]))):
        raise ValueError('BUSINESS_RECORD_INVALID')
    answer = db.execute(text('SELECT * FROM assistant_messages WHERE id=:id'),
        {'id':str(uuid5(NAMESPACE_URL, 'qx-business-answer:' + run['id']))}).mappings().first()
    if (answer is None or answer['role'] != 'assistant' or answer['content'] != result.text
            or answer['conversation_id'] != run['conversation_id'] or answer['source_revision'] != scope.input_revision):
        raise ValueError('BUSINESS_RECORD_INVALID')
    from .evidence_records import source
    for ref in result.source_refs:
        source(ref, scope, 0, result.created_at, db)
    if result.evidence:
        preparation.validate_evidence(result, db)
    if (result.task_id and request.task_id and result.task_id != request.task_id
            and not any(word in request.content for word in ('重新审查', '新建任务', '开始新任务'))):
        raise ValueError('BUSINESS_RECORD_INVALID')
    if result.contract_draft_id:
        target = db.scalar(text('SELECT conversation_id FROM task_drafts WHERE id=:id'),
                           {'id':str(result.contract_draft_id)})
        if target != run['conversation_id']:
            raise ValueError('BUSINESS_RECORD_INVALID')
    if result.intake_id:
        receipt = db.execute(text('SELECT intake_id,conversation_id FROM assistant_profile_receipts WHERE request_id=:id'),
            {'id':str(uuid5(NAMESPACE_URL, 'qx-business-profile:' + run['id']))}).mappings().first()
        if receipt is None or receipt['intake_id'] != str(result.intake_id) or receipt['conversation_id'] != run['conversation_id']:
            raise ValueError('BUSINESS_RECORD_INVALID')
    return accepted, result


def _message(request):
    return d.AssistantMessageInput(request_id=request.request_id, expected_scope=request.expected_scope,
        expected_composer_revision=request.expected_composer_revision, content=request.content)


def history(actor, cid, db):
    service._owned(actor, cid, db)
    rows = db.execute(text('''SELECT r.* FROM assistant_runs r WHERE r.conversation_id=:cid
        AND EXISTS(SELECT 1 FROM assistant_run_events e WHERE e.run_id=r.id AND e.event_type='business.accepted')
        ORDER BY r.rowid'''), {'cid':str(cid)}).mappings()
    try:
        return tuple(_record(row, db)[1] for row in rows)
    except (ValueError, TypeError):
        raise ServiceError('VERSION_CONFLICT', 409) from None


def find(actor, cid, request_id, db):
    service._owned(actor, cid, db)
    row = db.execute(text('SELECT * FROM assistant_runs WHERE conversation_id=:cid AND request_id=:rid'),
                     {'cid':str(cid), 'rid':str(request_id)}).mappings().first()
    if row is None:
        return None
    try:
        result = _record(row, db)
        if result is None:
            raise ValueError
        return result
    except (ValueError, TypeError):
        raise ServiceError('VERSION_CONFLICT', 409) from None


def _reception(actor, run, request, db):
    import re

    # Only whole-message presentation requests are excluded; mixed facts remain sourced.
    output_only = re.fullmatch(
        r'(?:请|麻烦)?(?:(?:把|将)?(?:刚才的|上面的|这段)?(?:发?给客户的)?(?:回复|答复|回答)(?:再)?'
        r'(?:(?:缩短|精简|压缩)(?:到|为|成)?(?:[一二三四五六七八九十两0-9]+句(?:话)?|一点|一些)?'
        r'|(?:改得|改为|改成|写得|调整为)(?:更)?(?:委婉|礼貌|简短|简洁|正式|口语化|温和|通俗)(?:的语气)?(?:一点|一些)?)'
        r'|用[一二三四五六七八九十两0-9]+句话(?:回复|答复|回答)'
        r'|(?:润色|精简|缩短)(?:一下)?(?:刚才的|上面的|这段)?(?:回复|答复|回答))',
        request.content.strip().rstrip('。！!？?')) is not None
    current = profile_store._profile(run.scope.conversation_id, db)
    view = reception_worksheet.view(actor, run.scope.conversation_id, db)
    quote = d.ProfileMessageRef(kind='message', conversation_id=run.scope.conversation_id,
        message_id=run.message_id, source_revision=run.scope.input_revision,
        start=0, end=len(request.content), quote=request.content, quote_sha256=sha_text(request.content))
    excerpt = request.content if len(request.content) <= 12000 else '【原话节选；全文见来源消息】\n' + request.content[:11970]
    changes = [] if output_only else [d.ProfileProposal(field='consultation',
        value=d.TextFactValue(kind='text', value=excerpt), origin='user_statement', source_refs=(quote,))]
    if current is None and not output_only:
        changes.append(d.ProfileProposal(field='title', value=d.TextFactValue(kind='text', value=request.content[:60]),
            origin='user_statement', source_refs=(quote,)))
    edits, notice = (), ''
    project = view.writable and not output_only
    if not output_only:
        field = next((item for item in current.fields if item.field == 'consultation'), None) if current else None
        managed = field is None and view.expected_intake_id is None
        previous = ''
        if field is not None:
            # A value match alone never makes a human edit automatic. Prove the
            # receipt belongs to a completed sales run in this same conversation.
            auto = {}
            for row in db.execute(text('''SELECT r.* FROM assistant_runs r WHERE r.conversation_id=:cid
                    AND EXISTS(SELECT 1 FROM assistant_run_events e
                    WHERE e.run_id=r.id AND e.event_type='business.result')'''),
                    {'cid':str(run.scope.conversation_id)}).mappings():
                accepted, result = _record(row, db)
                if result.workflow == 'sales':
                    auto[str(uuid5(NAMESPACE_URL, 'qx-business-profile:' + row['id']))] = accepted
            for row in db.execute(text('''SELECT * FROM assistant_profile_receipts
                    WHERE conversation_id=:cid ORDER BY sequence DESC'''),
                    {'cid':str(run.scope.conversation_id)}).mappings():
                saved = d.ProfileCommitInput.model_validate_json(row['request_json'])
                edit = next((item for item in saved.manual_edits if item.field == 'consultation'), None)
                proposal = next((item for item in saved.patch.changes if item.field == 'consultation'), None)
                if edit is None and (field.protected_value is not None or proposal is None):
                    continue
                profile_store._receipt(row, actor, db)
                origin = auto.get(row['request_id'])
                expected = edit.value if edit else proposal.value
                selected = field.protected_value
                if selected is None and len(field.candidates) == 1:
                    selected = field.candidates[0].value
                managed = (origin is not None and origin.scope == saved.patch.scope
                    and proposal is not None and selected == expected
                    and row['intake_id'] == (str(view.expected_intake_id) if view.expected_intake_id else None)
                    and row['intake_revision'] == view.expected_intake_revision
                    and any(ref.kind == 'message' and ref.quote == origin.request.content
                        and ref.conversation_id == run.scope.conversation_id
                        and ref.source_revision == origin.scope.input_revision for ref in proposal.source_refs))
                if managed and selected.kind == 'text':
                    previous = selected.value
                else:
                    managed = False
                break
        if managed:
            label = '明确更正' if request.content.lstrip().startswith(('更正', '纠正', '修正')) else '补充陈述'
            combined = (previous + '\n\n【' + label + '（待核）】\n' if previous
                        else '【原始陈述（待核）】\n') + request.content
            if len(combined) <= 12000:
                edits = (d.ProfileEdit(field='consultation', value=d.TextFactValue(kind='text', value=combined)),)
            else:
                project = False
                notice = '\n\n咨询档案汇总超限，本次原话未并入；既有档案保持，完整补充及其来源保留在本对话和档案历史中。'
        elif field is None or field.protected_value is None:
            # Leave an unproven/conflicted existing projection intact for review.
            project = False
        else:
            notice = '\n\n人工保留的咨询档案保持不变；本次补充作为待核原话保存，可回查来源。'
    patch = d.ProfilePatch(scope=run.scope, base_profile_revision=current.revision if current else 0,
                          changes=tuple(changes))
    source = d.AssistantMessageView(id=run.message_id, role='user', content=request.content,
                                   source_revision=run.scope.input_revision, created_at=run.created_at)
    receipt = profile_store._commit(actor, d.ProfileCommitInput(
        request_id=uuid5(NAMESPACE_URL, 'qx-business-profile:' + str(run.id)), patch=patch,
        expected_intake_id=view.expected_intake_id, expected_intake_revision=view.expected_intake_revision,
        manual_edits=edits, project_intake=project), d.ProfileSourceSnapshot(scope=run.scope, messages=(source,)), db)
    if output_only:
        return '已保留本次回复调整要求；咨询档案与事实候选未改动。', receipt.intake_id
    reply = ('客户诉求与原始陈述（待核）\n' + request.content[:12000] +
        ('\n（长文完整内容保留在上方原始消息中。）' if len(request.content)>12000 else '') + notice + '\n\n待补信息\n'
        '• 希望优先解决的问题及当前进展。\n• 关键日期、双方身份与完整原始材料。\n'
        '• 已有约定、实际履行及相反说法分别核对。\n\n后续跟进\n'
        '先核对以上信息；补充内容可继续发在本对话。明确日期前不自动安排期限。\n\n'
        '本机接待底稿；这是规则整理，未调用模型，未核实事实。')
    return reply, receipt.intake_id


def sha_text(value):
    from hashlib import sha256
    return sha256(value.encode('utf-8')).hexdigest()


def submit(actor, cid, value, db, *, personal_draft_id=None):
    request = d.BusinessInput.model_validate(value.model_dump(mode='python'))
    service._owned(actor, cid, db)
    require_active(db)
    previous = find(actor, cid, request.request_id, db)
    if previous:
        if previous[0].request != request:
            raise ServiceError('VERSION_CONFLICT', 409)
        return previous[1]
    old = history(actor, cid, db)
    new_task = request.new_task or any(word in request.content for word in ('重新审查', '新建任务', '开始新任务'))
    intent = request.workflow or classify(request.content)
    workflow = None if intent == 'ambiguous' else intent
    can_continue = intent != 'ambiguous' and (workflow is not None or continuing(request.content) or request.task_id)
    candidates = {item.task_id:item for item in old if item.task_id and (workflow is None or item.workflow == workflow)}
    if request.task_id is not None and not new_task:
        selected = candidates.get(request.task_id)
        if selected is None:
            if any(item.task_id == request.task_id for item in old):
                raise ServiceError('STATE_CONFLICT', 409)
            raise ServiceError('CROSS_MATTER_DENIED', 403)
        workflow = selected.workflow
    else:
        selected = next(iter(candidates.values())) if can_continue and len(candidates) == 1 and not new_task else None
        workflow = workflow or (selected.workflow if selected else None)
    ambiguous = can_continue and len(candidates) > 1 and request.task_id is None and not new_task
    task_id = None if ambiguous or workflow is None else selected.task_id if selected else uuid4()
    with db.begin_nested():
        run = service.save_message(actor, cid, _message(request), db)
        accepted = d.BusinessAccepted(request=request, scope=run.scope, workflow=workflow, task_id=task_id)
        _append(run.id, 'business.accepted', accepted.model_dump(mode='json'), db)
        intake_id, contract_id, refs, state, evidence = None, None, (), 'completed', None
        if ambiguous:
            output, state = '这条补充属于哪个已有任务？请明确任务后继续，当前内容已保留。', 'awaiting_input'
        elif workflow == 'sales':
            output, intake_id = _reception(actor, run, request, db)
        elif workflow in {'case', 'court', 'contract'}:
            refs, files, directory = preparation.sources(actor, cid, db)
            if workflow == 'contract':
                output, contract_id = preparation.contract(actor, run, request, selected, files, db,
                    personal_draft_id=personal_draft_id)
                state = 'awaiting_input'
            elif workflow == 'case':
                output, evidence = preparation.case_text(actor, cid, refs, directory, db)
            else:
                output, evidence = preparation.court_text(actor, cid, refs, directory, db)
        else:
            output, state = '请说明这次要处理客户接待、案件整理、合同审查还是模拟法庭。', 'awaiting_input'
        result = d.BusinessResult(run_id=run.id, message_id=run.message_id, request_id=request.request_id,
            task_id=task_id, workflow=workflow, scope=run.scope, state=state, text=output,
            intake_id=intake_id, contract_draft_id=contract_id, source_refs=refs, evidence=evidence, created_at=service._at())
        db.execute(text('UPDATE assistant_runs SET state=:state WHERE id=:id'), {'state':state, 'id':str(run.id)})
        _append(run.id, 'business.result', d.BusinessResultRecord(result=result,
            result_sha256=sha(result.model_dump(mode='json'))).model_dump(mode='json'), db)
        db.execute(text('''INSERT INTO assistant_messages(id,conversation_id,role,content,created_at,source_revision)
            VALUES(:id,:cid,'assistant',:content,:at,:revision)'''),
            {'id':str(uuid5(NAMESPACE_URL, 'qx-business-answer:' + str(run.id))), 'cid':str(cid),
             'content':output, 'at':result.created_at.isoformat(), 'revision':run.scope.input_revision})
        return result


def validate_business_records(db, *, allowed):
    exists = db.scalar(text("SELECT 1 FROM sqlite_master WHERE type='table' AND name='assistant_run_events'"))
    if not exists:
        return
    identifiers = tuple(db.scalars(text("SELECT DISTINCT run_id FROM assistant_run_events WHERE lower(event_type) LIKE 'business.%'")))
    if identifiers and not allowed:
        raise ValueError('BUSINESS_RECORD_INVALID')
    for identifier in identifiers:
        row = db.execute(text('SELECT * FROM assistant_runs WHERE id=:id'), {'id':identifier}).mappings().one()
        _record(row, db)
