"""Minimal personal-channel receipts; business/model ledgers own all content."""
from uuid import UUID, uuid5, NAMESPACE_URL
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from .. import domain as d
from ..assistant import business, service
from ..record_codec import sha
from ..security import ServiceError
from . import ingress

NOTICES = {
    'collect_only':'材料和指令已收集。桌面尚未开启自动模型范围，请在桌面确认后处理。',
    'dirty_composer':'桌面有未发送草稿，微信任务等待处理；请先发送或自行清理草稿。',
    'instruction_required':'材料已收到。请说明要做合同审查、案件整理、庭审准备还是客户接待。',
    'main_contract_required':'指令已收到，请继续发送合同或案件材料。',
    'main_contract_selection_required':'已收到多份材料。请在桌面任务记录中选择主合同后继续。',
    'ambiguous':'这条内容属于哪个任务、需要哪种业务处理？请在桌面明确归属后继续。',
    'media_pending':'材料正在归集，请稍候。',
    'media_not_readable':'材料未完整读取，请到桌面检查原文和解析状态。',
}


def bounded_reply(body):
    return body if len(body) <= 3000 else body[:2900] + '\n\n内容较长，完整结果和引用请到桌面本对话查看。'


def model_reply(attempt):
    if attempt.output is not None:
        return bounded_reply(attempt.output.candidate.text + '\n\n工作草稿，事实与依据待核。完整材料与引用见桌面本对话。')
    return '本次处理未得到可用成果，请在桌面查看原请求状态。结果未知时不会自动重试。'


def stable(kind, *parts):
    return uuid5(NAMESPACE_URL, 'qx-personal:' + kind + ':' + ':'.join(map(str, parts)))


def links(db, mapping_id):
    return tuple(d.PersonalWeixinRunLink(**row) for row in db.execute(text(
        'SELECT * FROM weixin_personal_runs WHERE mapping_id=:id ORDER BY rowid'),
        {'id':str(mapping_id)}).mappings())


def add_link(db, mapping_id, draft, event_id, result):
    value = d.PersonalWeixinRunLink(id=stable('link', draft.id, draft.revision),
        mapping_id=mapping_id, draft_id=draft.id, draft_revision=draft.revision,
        source_event_id=event_id, business_run_id=result.run_id,
        model_request_id=stable('model', draft.id, draft.revision), created_at=service._at())
    ingress._insert('weixin_personal_runs', value.model_dump(mode='json'), db)
    return value


def require_model_source(actor, basis, db):
    if not db.scalar(text("SELECT 1 FROM sqlite_master WHERE name='weixin_personal_runs'")):
        return
    link = db.execute(text('SELECT * FROM weixin_personal_runs WHERE model_request_id=:id'),
        {'id':str(basis.request_id)}).mappings().first()
    if link:
        from . import accounts
        mapping = accounts._mapping(accounts._mapping_row(link['mapping_id'],db))
        accounts._account(actor,mapping.account_id,db,mode='weixin_personal')
        if mapping.revoked_at or any(getattr(mapping.scope,key) != getattr(basis.expected_scope,key) for key in
                ('workspace_id','conversation_id','scope_kind','scope_ref','binding_revision')):
            raise ServiceError('BLOCKED_LIVE',403)


def claim(db, mapping_id, event_id, key, body):
    identifier = stable('reply', mapping_id, key)
    old = db.execute(text('SELECT * FROM weixin_personal_outbox WHERE client_id=:id'),
        {'id':str(identifier)}).mappings().first()
    if old:
        return None  # Includes an interrupted send: never automatically retransmit.
    value = d.PersonalWeixinSendClaim(client_id=identifier, mapping_id=mapping_id,
        source_event_id=event_id, result_key=key, payload_sha256=sha(body),
        status='unknown', created_at=service._at())
    ingress._insert('weixin_personal_outbox', value.model_dump(mode='json'), db)
    return value


def validate_records(db, *, allowed=True):
    if not db.scalar(text("SELECT 1 FROM sqlite_master WHERE name='weixin_personal_runs'")):
        return
    rows = tuple(db.execute(text('SELECT * FROM weixin_personal_runs')).mappings())
    sends = tuple(db.execute(text('SELECT * FROM weixin_personal_outbox')).mappings())
    if (rows or sends) and not allowed:
        raise ValueError('PERSONAL_RUNTIME_REQUIRE_QXBAK')
    try:
        for row in (*rows, *sends):
            mapping = db.execute(text('''SELECT m.*,a.mode,b.conversation_id FROM weixin_peer_bindings m
                JOIN weixin_accounts a ON a.id=m.account_id JOIN task_channel_bindings b ON b.id=m.task_binding_id
                WHERE m.id=:id'''), {'id':row['mapping_id']}).mappings().one()
            source = db.execute(text('SELECT * FROM task_inbox_events WHERE id=:id'),
                {'id':row['source_event_id']}).mappings().one()
            if (mapping['mode'] != 'weixin_personal' or source['binding_id'] != mapping['task_binding_id']
                    or source['created_at'] > row['created_at']):
                raise ValueError
            if 'business_run_id' in row:
                item = d.PersonalWeixinRunLink(**row)
                run = db.execute(text('SELECT * FROM assistant_runs WHERE id=:id'),
                    {'id':row['business_run_id']}).mappings().one()
                draft = db.execute(text('SELECT * FROM task_drafts WHERE id=:id'),
                    {'id':row['draft_id']}).mappings().one()
                accepted, result = business._record(run, db)
                if (item.id != stable('link', item.draft_id, item.draft_revision)
                        or item.model_request_id != stable('model', item.draft_id, item.draft_revision)
                        or accepted.request.request_id != stable('business', item.draft_id, item.draft_revision)
                        or run['conversation_id'] != mapping['conversation_id']
                        or draft['conversation_id'] != mapping['conversation_id']
                        or draft['revision'] < item.draft_revision
                        or result.workflow == 'contract' and result.contract_draft_id != item.draft_id
                        or not db.scalar(text('SELECT 1 FROM task_draft_events WHERE draft_id=:draft AND event_id=:event'),
                            {'draft':row['draft_id'],'event':row['source_event_id']})
                        or result.created_at > item.created_at):
                    raise ValueError
                attempt = db.execute(text('SELECT * FROM assistant_runs WHERE request_id=:id'),
                    {'id':str(item.model_request_id)}).mappings().first()
                if attempt:
                    from ..assistant.providers.attempts import _input
                    saved = db.execute(text('SELECT * FROM assistant_model_attempts WHERE run_id=:id'),
                        {'id':attempt['id']}).mappings().one()
                    prepared = _input(saved)
                    if (type(prepared) is not d.MainMaterialPreparedInput
                            or prepared.request.basis.parent_business_run_id != item.business_run_id):
                        raise ValueError
            else:
                item = d.PersonalWeixinSendClaim(**row)
                if item.client_id != stable('reply', item.mapping_id, item.result_key):
                    raise ValueError
                parts = item.result_key.split(':')
                if parts[0] == 'model' and len(parts) == 2:
                    from ..assistant.providers.attempts import _row, _input
                    attempt = _row(UUID(parts[1]), db)
                    prepared = _input(attempt)
                    linked = db.execute(text('''SELECT 1 FROM weixin_personal_runs WHERE mapping_id=:mapping
                        AND source_event_id=:event AND model_request_id=:request'''),
                        {'mapping':row['mapping_id'],'event':row['source_event_id'],
                         'request':str(prepared.request.basis.request_id)}).first()
                    if not linked or attempt['state'] in {'reserved','sending'}:
                        raise ValueError
                    output = db.scalar(text('SELECT output_json FROM assistant_model_outputs WHERE attempt_id=:id'),
                        {'id':attempt['id']})
                    body = (bounded_reply(d.MainMaterialOutputView.model_validate_json(output).candidate.text +
                        '\n\n工作草稿，事实与依据待核。完整材料与引用见桌面本对话。') if output
                        else '本次处理未得到可用成果，请在桌面查看原请求状态。结果未知时不会自动重试。')
                elif parts[0] == 'notice' and len(parts) == 4:
                    draft_id, revision = str(UUID(parts[1])), int(parts[2])
                    if revision < 1 or not db.scalar(text('''SELECT 1 FROM task_drafts d JOIN task_draft_events e
                        ON d.id=e.draft_id WHERE d.id=:id AND d.revision>=:revision AND e.event_id=:event'''),
                        {'id':draft_id,'revision':revision,'event':row['source_event_id']}):
                        raise ValueError
                    reason = 'collect_only' if parts[3] == 'collect' else parts[3]
                    body = NOTICES.get(reason, NOTICES['media_not_readable'])
                elif parts[0] == 'ambiguous' and len(parts) == 2:
                    UUID(parts[1])
                    body = NOTICES['ambiguous']
                else:
                    raise ValueError
                if item.payload_sha256 != sha(body):
                    raise ValueError
    except (ValueError, TypeError, KeyError, AttributeError, ServiceError, SQLAlchemyError):
        raise ValueError('PERSONAL_RUNTIME_INTEGRITY') from None
