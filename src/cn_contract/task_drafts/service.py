"""Collect source batches without model calls; freeze immutable review inputs."""
import json
import re
from uuid import UUID, uuid4

from sqlalchemy import text

from .. import domain as d
from ..assistant import attachment_files, attachment_records
from ..assistant.service import _at, _digest, _owned, _snapshot
from ..config import canonical_json
from ..ops.storage import require_active
from ..persistence import configured_database, read_version
from ..security import ServiceError, authorize

CONTROLS = {'暂停':'paused','先别审':'paused','取消':'cancelled','继续':'collecting'}


def _control(request):
    if request.media:
        return None
    value = re.sub(r'[\s，,。.!！?？；;、]', '', request.text)
    if re.fullmatch(r'(?:我?还有(?:附件|材料)(?:要发|没发完)?|(?:附件|材料)(?:还没|没有)发完)'
                    r'(?:请?(?:稍等(?:一下)?|等一下|等等))?', value):
        return 'paused'
    if value in {'请继续','继续审查','请继续审查','继续处理','请继续处理'}:
        return 'collecting'
    return CONTROLS.get(value)


def _validate(model, value):
    return model.model_validate(value.model_dump(mode='python'))


def _write(actor, cid, db):
    row = _owned(actor,cid,db)
    require_active(db)
    if row['archived_at'] is not None:
        raise ServiceError('STATE_CONFLICT',409)
    return row


def _row(table, identifier, db):
    row = db.execute(text('SELECT * FROM ' + table + ' WHERE id=:id'),
        {'id':str(identifier)}).mappings().first()
    if row is None:
        raise ServiceError('CROSS_MATTER_DENIED',403)
    return row


def create_binding(actor, cid, db):
    return _create_binding(actor, cid, db, channel='synthetic')


def _create_binding(actor, cid, db, *, channel):
    _write(actor,cid,db)
    row = db.execute(text('SELECT * FROM task_channel_bindings WHERE conversation_id=:cid AND channel=:channel'),
        {'cid':str(cid),'channel':channel}).mappings().first()
    if row is None:
        identifier = uuid4()
        db.execute(text('''INSERT INTO task_channel_bindings
            (id,conversation_id,channel,cursor,created_at) VALUES (:id,:cid,:channel,0,:at)'''),
            {'id':str(identifier),'cid':str(cid),'channel':channel,'at':_at()})
        row = _row('task_channel_bindings',identifier,db)
    return d.TaskChannelBindingView(**row)


def read_binding(actor, identifier, db):
    row = _row('task_channel_bindings',identifier,db)
    _owned(actor,row['conversation_id'],db)
    return d.TaskChannelBindingView(**row)


def _draft(actor, identifier, db):
    row = _row('task_drafts',identifier,db)
    _owned(actor,row['conversation_id'],db)
    return row


def _payload(row):
    value = d.TaskInboxEventInput.model_validate_json(row['payload_json'])
    if _digest(value.model_dump(mode='json')) != row['payload_sha256'] or value.event_id != row['event_id']:
        raise ServiceError('VERSION_CONFLICT',409)
    return value


def _event(row, db, *, task_id=None):
    value = _payload(row)
    if task_id is None:
        task_id = db.scalar(text('''SELECT draft_id FROM task_draft_events
            WHERE event_id=:id ORDER BY rowid LIMIT 1'''),{'id':row['id']})
    data = value.model_dump(mode='python')
    data['task_id'] = task_id
    channel = db.scalar(text('SELECT channel FROM task_channel_bindings WHERE id=:id'),{'id':row['binding_id']})
    return d.TaskInboxEventView(**data,id=row['id'],binding_id=row['binding_id'],channel=channel,
        association='assigned' if task_id else 'unassigned',created_at=row['created_at'])


def _events(identifier, db):
    return db.execute(text('''SELECT e.* FROM task_inbox_events e JOIN task_draft_events de
        ON de.event_id=e.id WHERE de.draft_id=:id ORDER BY de.ordinal'''),
        {'id':str(identifier)}).mappings().all()


def _resolutions(identifier, db):
    rows = db.execute(text('''SELECT * FROM task_media_resolutions
        WHERE draft_id=:id ORDER BY revision,rowid'''),{'id':str(identifier)}).mappings().all()
    return tuple(d.TaskMediaResolutionView(id=row['id'],event_id=row['event_id'],media_id=row['media_id'],
        action=row['action'],reason=row['reason'],revision=row['revision'],created_at=row['created_at'],
        replacement=None if row['replacement_json'] is None else
            d.TaskMediaInput.model_validate_json(row['replacement_json'])) for row in rows)


def _media(actor, cid, media, db, *, check_files=False):
    metadata = {}
    if media.attachment_id is not None:
        source = attachment_records.owned_attachment(actor,cid,media.attachment_id,db)
        if ((media.sha256 is not None and source['sha256'] != media.sha256)
                or source['original_name'] != media.name or source['mime'] != media.mime):
            raise ServiceError('VERSION_CONFLICT',409)
        if media.parse_revision is not None:
            parsed = attachment_records.parse_view(
                attachment_records.parse_row(cid,media.attachment_id,media.parse_revision,db))
            metadata = {'reading_status':parsed.reading_status,'result_sha256':parsed.result_sha256}
        if check_files:
            attachment_files.read_checked(source,configured_database(db))
    return d.TaskManifestMedia(**media.model_dump(mode='python'),**metadata)


def _manifest(actor, row, db, *, check_files=False):
    conversation = _owned(actor,row['conversation_id'],db)
    resolved = {(str(item.event_id),item.media_id):item for item in _resolutions(row['id'],db)}
    events, blockers, ready = [],[],{}
    for event in _events(row['id'],db):
        payload = _payload(event)
        media_values = []
        for original in payload.media:
            resolution = resolved.get((event['id'],original.media_id))
            if resolution is not None and resolution.action == 'exclude':
                selected = d.TaskManifestMedia(**original.model_dump(mode='python'),
                    excluded=True,exclusion_reason=resolution.reason)
            else:
                selected = _media(actor,row['conversation_id'],
                    resolution.replacement if resolution else original,db,check_files=check_files)
                if selected.status != 'ready':
                    blockers.append('media_' + selected.status)
                elif selected.reading_status != 'readable':
                    blockers.append('media_not_readable')
                elif selected.mime not in {'application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'application/pdf'}:
                    blockers.append('media_unsupported')
                else:
                    previous = ready.get(selected.attachment_id)
                    if previous and (previous.sha256,previous.parse_revision) != (selected.sha256,selected.parse_revision):
                        blockers.append('media_revision_conflict')
                    ready[selected.attachment_id] = selected
            media_values.append(selected)
        events.append(d.TaskManifestEvent(id=event['id'],event_id=payload.event_id,
            payload_sha256=event['payload_sha256'],text=payload.text,media=tuple(media_values)))
    main = UUID(row['main_attachment_id']) if row['main_attachment_id'] else None
    if main is None and len(ready) == 1:
        main = next(iter(ready))
    if main is None:
        blockers.append('main_contract_required' if not ready else 'main_contract_selection_required')
    elif main not in ready:
        blockers.append('main_contract_unavailable')
    if not row['instruction'].strip():
        blockers.append('instruction_required')
    manifest = d.TaskDraftManifest(draft_id=row['id'],conversation_id=row['conversation_id'],
        scope=_snapshot(conversation),revision=row['revision'],instruction=row['instruction'],
        main_attachment_id=main,events=tuple(events),synthetic=not db.scalar(text('''SELECT 1 FROM task_draft_events de
            JOIN task_inbox_events e ON e.id=de.event_id JOIN task_channel_bindings b ON b.id=e.binding_id
            WHERE de.draft_id=:id AND b.channel='weixin_personal' LIMIT 1'''),{'id':row['id']}))
    return manifest,tuple(dict.fromkeys(blockers))


def _execution(row):
    data = dict(row)
    data['manifest'] = d.TaskDraftManifest.model_validate_json(data.pop('manifest_json'))
    data['document_versions'] = json.loads(data.pop('document_versions_json'))
    data['source_versions'] = json.loads(data.pop('source_versions_json'))
    result = d.TaskExecutionView(**data)
    if (_digest(result.manifest.model_dump(mode='json')) != result.manifest_sha256
            or result.draft_id != result.manifest.draft_id or result.revision != result.manifest.revision):
        raise ServiceError('VERSION_CONFLICT',409)
    return result


def read_execution(actor, identifier, db):
    row = _row('task_executions',identifier,db)
    draft = _draft(actor,row['draft_id'],db)
    result = _execution(row)
    current = _snapshot(_owned(actor,draft['conversation_id'],db))
    frozen = result.manifest.scope
    if ((current.workspace_id,current.conversation_id,current.binding_revision,current.scope_kind,current.scope_ref)
            != (frozen.workspace_id,frozen.conversation_id,frozen.binding_revision,frozen.scope_kind,frozen.scope_ref)):
        raise ServiceError('VERSION_CONFLICT',409)
    if result.matter_id is not None:
        authorize(actor,result.matter_id,'read',db)
    return result


def read_draft(actor, identifier, db):
    row = _draft(actor,identifier,db)
    execution_id = db.scalar(text('SELECT id FROM task_executions WHERE draft_id=:id'),{'id':str(identifier)})
    execution = read_execution(actor,execution_id,db) if execution_id else None
    if execution:
        manifest,blockers = execution.manifest,()
    else:
        manifest,blockers = _manifest(actor,row,db)
    return d.TaskDraftView(**row,events=tuple(_event(event,db,task_id=identifier) for event in _events(identifier,db)),
        media_resolutions=_resolutions(identifier,db),manifest_sha256=_digest(manifest.model_dump(mode='json')),
        blockers=blockers,execution=execution,synthetic=manifest.synthetic).model_copy(update={'main_attachment_id':manifest.main_attachment_id})


def list_drafts(actor, cid, db):
    _owned(actor,cid,db)
    identifiers = db.scalars(text('SELECT id FROM task_drafts WHERE conversation_id=:cid ORDER BY rowid'),
        {'cid':str(cid)}).all()
    binding = db.execute(text("SELECT * FROM task_channel_bindings WHERE conversation_id=:cid ORDER BY CASE channel WHEN 'synthetic' THEN 0 ELSE 1 END,id"),
        {'cid':str(cid)}).mappings().first()
    unassigned = ()
    if binding:
        rows = db.execute(text('''SELECT e.* FROM task_inbox_events e
            JOIN task_channel_bindings b ON b.id=e.binding_id WHERE b.conversation_id=:cid
            AND NOT EXISTS(SELECT 1 FROM task_draft_events de WHERE de.event_id=e.id) ORDER BY e.rowid'''),
            {'cid':str(cid)}).mappings().all()
        unassigned = tuple(_event(row,db) for row in rows)
    items = []
    for identifier in identifiers:
        try:
            items.append(read_draft(actor,identifier,db))
        except ServiceError as error:
            if error.status_code not in {403,409}:
                raise
    return d.TaskDraftListView(binding=d.TaskChannelBindingView(**binding) if binding else None,
        items=tuple(items),unassigned_events=unassigned)


def _new_draft(cid, db, *, parent=None):
    identifier,at = str(uuid4()),_at()
    db.execute(text('''INSERT INTO task_drafts (id,conversation_id,parent_draft_id,revision,state,
        instruction,main_attachment_id,created_at,updated_at)
        VALUES (:id,:cid,:parent,1,'collecting',:instruction,:main,:at,:at)'''),
        {'id':identifier,'cid':str(cid),'parent':parent['id'] if parent else None,
         'instruction':parent['instruction'] if parent else '',
         'main':parent['main_attachment_id'] if parent else None,'at':at})
    if parent:
        db.execute(text('''INSERT INTO task_draft_events(draft_id,event_id,ordinal)
            SELECT :new,event_id,ordinal FROM task_draft_events WHERE draft_id=:old'''),
            {'new':identifier,'old':parent['id']})
        latest = {(item.event_id,item.media_id):item for item in _resolutions(parent['id'],db)}
        for resolution in latest.values():
            _save_resolution(identifier,resolution,1,db)
    return identifier


def _attach(identifier, event, db):
    if not _fits(identifier,event,db):
        raise ServiceError('FILE_LIMIT',413)
    draft = _row('task_drafts',identifier,db)
    ordinal = db.scalar(text('SELECT COALESCE(MAX(ordinal),0)+1 FROM task_draft_events WHERE draft_id=:id'),
        {'id':str(identifier)})
    db.execute(text('INSERT INTO task_draft_events(draft_id,event_id,ordinal) VALUES (:draft,:event,:ordinal)'),
        {'draft':str(identifier),'event':event['id'],'ordinal':ordinal})
    request = _payload(event)
    control = _control(request)
    content = '' if control else request.text
    instruction = '\n'.join(value for value in (draft['instruction'],content) if value.strip())
    if len(instruction) > 20000:
        raise ServiceError('FILE_LIMIT',413)
    db.execute(text('''UPDATE task_drafts SET revision=revision+1,instruction=:instruction,
        state=:state,updated_at=:at WHERE id=:id AND state!='frozen' '''),
        {'id':str(identifier),'instruction':instruction,'state':control or draft['state'],'at':_at()})


def _fits(identifier, event, db):
    events = _events(identifier,db)
    if len(events) >= 100:
        return False
    all_events = (*events,event)
    if sum(len(item['payload_json'].encode('utf-8')) for item in all_events) > 3*1024*1024:
        return False
    attachments = {media.attachment_id for item in all_events for media in _payload(item).media
        if media.attachment_id is not None}
    attachments.update(item.replacement.attachment_id for item in _resolutions(identifier,db) if item.replacement)
    if len(attachments) > 20:
        return False
    draft = _row('task_drafts',identifier,db)
    request = _payload(event)
    content = '' if _control(request) else request.text
    return len('\n'.join(value for value in (draft['instruction'],content) if value.strip())) <= 20000


def _follow_target(actor, cid, identifier, control, db):
    row = _draft(actor,identifier,db)
    if row['conversation_id'] != str(cid):
        raise ServiceError('CROSS_MATTER_DENIED',403)
    if row['state'] == 'frozen':
        execution_id = db.scalar(text('SELECT id FROM task_executions WHERE draft_id=:id'),{'id':row['id']})
        read_execution(actor,execution_id,db)
        if control:
            return None
        children = db.scalars(text("SELECT id FROM task_drafts WHERE parent_draft_id=:id AND state='collecting'"),
            {'id':row['id']}).all()
        if len(children) > 1:
            return None
        return children[0] if children else _new_draft(cid,db,parent=row)
    return row['id'] if row['state'] == 'collecting' or control else None


def _target(actor, cid, event, db):
    request = _payload(event)
    control = _control(request)
    if (db.scalar(text('SELECT channel FROM task_channel_bindings WHERE id=:id'),
            {'id':event['binding_id']}) == 'weixin_personal'
            and request.task_id is None and request.reply_to_event_id is None
            and db.scalar(text("SELECT 1 FROM sqlite_master WHERE name='weixin_personal_runs'"))):
        # Source text is interpreted here; the immutable wire payload/hash stays intact.
        candidates = db.execute(text('''SELECT DISTINCT draft.* FROM task_drafts draft
            JOIN task_draft_events de ON de.draft_id=draft.id JOIN task_inbox_events e ON e.id=de.event_id
            WHERE draft.conversation_id=:cid AND draft.state IN ('collecting','paused') '''),
            {'cid':str(cid)}).mappings().all()
        unused = [row for row in candidates if not db.scalar(text(
            'SELECT 1 FROM weixin_personal_runs WHERE draft_id=:id'), {'id':row['id']})]
        if control:
            return unused[0]['id'] if len(unused) == 1 else None
        explicit = any(word in request.text for word in ('重新审查', '新建任务', '开始新任务'))
        if len(unused) == 1 and not explicit:
            return unused[0]['id']
        # A single leaf identifies the previous task without guessing by timestamp.
        leaves = [row for row in candidates if not db.scalar(text(
            'SELECT 1 FROM task_drafts WHERE parent_draft_id=:id'), {'id':row['id']})]
        parent = dict(leaves[0]) if len(leaves) == 1 else None
        if parent is not None and parent['main_attachment_id'] is None:
            main = read_draft(actor,parent['id'],db).main_attachment_id
            parent['main_attachment_id'] = str(main) if main else None
        if explicit:
            return _new_draft(cid, db, parent=parent)
        if not unused and len(leaves) == 1 and not control:
            return _new_draft(cid, db, parent=parent)
        if not candidates and not control:
            return _new_draft(cid, db)
        return None
    if request.task_id is not None:
        return _follow_target(actor,cid,request.task_id,control,db)
    if request.reply_to_event_id is not None:
        candidates = db.execute(text('''SELECT draft.id,draft.state FROM task_drafts draft
            JOIN task_draft_events link ON link.draft_id=draft.id
            JOIN task_inbox_events source ON source.id=link.event_id
            WHERE source.binding_id=:binding AND source.event_id=:event
            AND draft.conversation_id=:cid AND draft.state IN ('collecting','frozen')'''),
            {'binding':event['binding_id'],'event':request.reply_to_event_id,'cid':str(cid)}).all()
        active = [identifier for identifier,state in candidates if state == 'collecting']
        selected = active or [identifier for identifier,state in candidates if state == 'frozen']
        if len(selected) != 1:
            return None
        return _follow_target(actor,cid,selected[0],control,db)
    if request.start_new:
        return _new_draft(cid,db)
    condition = "state!='frozen'" if control else "state='collecting'"
    candidates = db.scalars(text('SELECT id FROM task_drafts WHERE conversation_id=:cid AND '+condition),
        {'cid':str(cid)}).all()
    if len(candidates) == 1:
        return candidates[0]
    if not control and not candidates and not db.scalar(text('SELECT COUNT(*) FROM task_drafts WHERE conversation_id=:cid'),{'cid':str(cid)}):
        return _new_draft(cid,db)
    return None


def receive_batch(actor, binding_id, value, db):
    return _receive_batch(actor,binding_id,value,db,channel='synthetic')


def _receive_batch(actor, binding_id, value, db, *, channel):
    value = _validate(d.TaskInboxBatchInput,value)
    binding = read_binding(actor,binding_id,db)
    if binding.channel != channel:
        raise ServiceError('STATE_CONFLICT',409)
    _write(actor,binding.conversation_id,db)
    rows,new = [],[]
    with db.begin_nested():
        for event in value.events:
            digest = _digest(event.model_dump(mode='json'))
            row = db.execute(text('SELECT * FROM task_inbox_events WHERE binding_id=:binding AND event_id=:event'),
                {'binding':str(binding_id),'event':event.event_id}).mappings().first()
            if row is not None:
                if row['payload_sha256'] != digest:
                    raise ServiceError('VERSION_CONFLICT',409)
            else:
                if event.task_id is not None:
                    target = _draft(actor,event.task_id,db)
                    if target['conversation_id'] != str(binding.conversation_id):
                        raise ServiceError('CROSS_MATTER_DENIED',403)
                for media in event.media:
                    _media(actor,binding.conversation_id,media,db)
                identifier = str(uuid4())
                db.execute(text('''INSERT INTO task_inbox_events
                    (id,binding_id,event_id,payload_sha256,payload_json,created_at)
                    VALUES (:id,:binding,:event,:sha,:payload,:at)'''),
                    {'id':identifier,'binding':str(binding_id),'event':event.event_id,'sha':digest,
                     'payload':canonical_json(event.model_dump(mode='json')),'at':_at()})
                row = _row('task_inbox_events',identifier,db)
                new.append(row)
            rows.append(row)
        if binding.cursor != value.expected_cursor:
            if new or value.next_cursor > binding.cursor:
                raise ServiceError('VERSION_CONFLICT',409)
        else:
            # Every descriptor is durable in this transaction before association or cursor advancement.
            for row in new:
                target = _target(actor,binding.conversation_id,row,db)
                # A full requested target leaves the durable event available for later assignment.
                if target is not None and _fits(target,row,db):
                    _attach(target,row,db)
            db.execute(text('UPDATE task_channel_bindings SET cursor=:next WHERE id=:id AND cursor=:expected'),
                {'id':str(binding_id),'next':value.next_cursor,'expected':value.expected_cursor})
        events = tuple(_event(row,db) for row in rows)
        drafts = tuple(read_draft(actor,identifier,db) for identifier in dict.fromkeys(
            event.task_id for event in events if event.task_id))
        return d.TaskInboxBatchReceipt(binding=read_binding(actor,binding_id,db),events=events,drafts=drafts)


def _save_resolution(draft_id, resolution, revision, db):
    db.execute(text('''INSERT INTO task_media_resolutions
        (id,draft_id,event_id,revision,media_id,action,reason,replacement_json,created_at)
        VALUES (:id,:draft,:event,:revision,:media,:action,:reason,:replacement,:at)'''),
        {'id':str(uuid4()),'draft':str(draft_id),'event':str(resolution.event_id),'revision':revision,
         'media':resolution.media_id,'action':resolution.action,'reason':resolution.reason,
         'replacement':canonical_json(resolution.replacement.model_dump(mode='json')) if resolution.replacement else None,
         'at':_at()})


def update_draft(actor, identifier, value, db):
    value = _validate(d.TaskDraftUpdateInput,value)
    row = _draft(actor,identifier,db)
    _write(actor,row['conversation_id'],db)
    if row['revision'] != value.expected_revision or row['state'] == 'frozen':
        raise ServiceError('VERSION_CONFLICT',409)
    with db.begin_nested():
        if value.action in {'update','assign'} and row['state'] != 'collecting':
            if row['state'] != 'paused' or read_draft(actor,identifier,db).synthetic:
                raise ServiceError('STATE_CONFLICT',409)
        state = {'pause':'paused','cancel':'cancelled','resume':'collecting'}.get(value.action,row['state'])
        if value.action == 'assign':
            for event_id in value.event_ids:
                event = _row('task_inbox_events',event_id,db)
                binding = read_binding(actor,event['binding_id'],db)
                if binding.conversation_id != UUID(row['conversation_id']):
                    raise ServiceError('CROSS_MATTER_DENIED',403)
                if db.scalar(text('SELECT COUNT(*) FROM task_draft_events WHERE event_id=:id'),{'id':str(event_id)}):
                    raise ServiceError('VERSION_CONFLICT',409)
                _attach(identifier,event,db)
        else:
            revision = row['revision']+1
            for resolution in value.media_resolutions:
                event = next((item for item in _events(identifier,db) if item['id'] == str(resolution.event_id)),None)
                if event is None or not any(item.media_id == resolution.media_id for item in _payload(event).media):
                    raise ServiceError('VERSION_CONFLICT',409)
                if resolution.replacement:
                    _media(actor,row['conversation_id'],resolution.replacement,db)
                _save_resolution(identifier,resolution,revision,db)
            db.execute(text('''UPDATE task_drafts SET revision=:revision,state=:state,
                instruction=:instruction,main_attachment_id=:main,updated_at=:at
                WHERE id=:id AND revision=:expected'''),
                {'id':str(identifier),'revision':revision,'state':state,'expected':value.expected_revision,
                 'instruction':value.instruction if value.instruction is not None else row['instruction'],
                 'main':str(value.main_attachment_id) if value.main_attachment_id else row['main_attachment_id'],'at':_at()})
        result = read_draft(actor,identifier,db)
        if value.main_attachment_id is not None and 'main_contract_unavailable' in result.blockers:
            raise ServiceError('VERSION_CONFLICT',409)
        return result


def freeze_draft(actor, identifier, value, db):
    value = _validate(d.TaskFreezeInput,value)
    row = _draft(actor,identifier,db)
    _write(actor,row['conversation_id'],db)
    previous = db.execute(text('SELECT * FROM task_executions WHERE draft_id=:id'),{'id':str(identifier)}).mappings().first()
    if previous:
        if previous['revision'] != value.expected_revision or previous['manifest_sha256'] != value.manifest_sha256:
            raise ServiceError('VERSION_CONFLICT',409)
        return read_execution(actor,previous['id'],db)
    manifest,blockers = _manifest(actor,row,db,check_files=True)
    digest = _digest(manifest.model_dump(mode='json'))
    if row['revision'] != value.expected_revision or digest != value.manifest_sha256:
        raise ServiceError('VERSION_CONFLICT',409)
    if row['state'] != 'collecting' or blockers:
        raise ServiceError('STATE_CONFLICT',409)
    with db.begin_nested():
        updated = db.execute(text("UPDATE task_drafts SET state='frozen',updated_at=:at WHERE id=:id AND revision=:revision AND state='collecting'"),
            {'id':str(identifier),'revision':value.expected_revision,'at':_at()})
        if updated.rowcount != 1:
            raise ServiceError('VERSION_CONFLICT',409)
        execution_id,at = uuid4(),_at()
        db.execute(text('''INSERT INTO task_executions
            (id,draft_id,revision,manifest_sha256,manifest_json,state,created_at,updated_at)
            VALUES (:id,:draft,:revision,:sha,:manifest,'prepared',:at,:at)'''),
            {'id':str(execution_id),'draft':str(identifier),'revision':value.expected_revision,
             'sha':digest,'manifest':canonical_json(manifest.model_dump(mode='json')),'at':at})
        return read_execution(actor,execution_id,db)


def advance_execution(actor, identifier, state, db, *, expected_state, **changes):
    current = read_execution(actor,identifier,db)
    _write(actor,current.manifest.conversation_id,db)
    allowed = {'prepared':{'creating_matter','awaiting_facts','failed','blocked'},
        'creating_matter':{'awaiting_facts','failed','blocked'},'awaiting_facts':{'queued','running','failed','blocked'},
        'queued':{'running','failed','blocked'},'running':{'completed','failed','blocked'}}
    if current.state != expected_state or state not in allowed.get(current.state,set()):
        raise ServiceError('STATE_CONFLICT',409)
    fields = {'matter_id','job_id','review_run_id','document_versions','source_versions',
        'prepare_request_id','review_request_id','review_input_sha256','error'}
    if set(changes)-fields:
        raise ValueError('unknown execution fields')
    for name,value in changes.items():
        old = getattr(current,name)
        if name != 'error' and old not in (None,{}) and value != old:
            raise ServiceError('VERSION_CONFLICT',409)
    candidate = d.TaskExecutionView.model_validate({**current.model_dump(mode='python'),**changes,
        'state':state,'updated_at':_at()})
    if candidate.matter_id:
        authorize(actor,candidate.matter_id,'read',db)
    if state in {'awaiting_facts','queued','running','completed'} or candidate.document_versions:
        sources = {media.attachment_id:media for event in candidate.manifest.events
            for media in event.media if not media.excluded}
        if (candidate.matter_id is None or not candidate.document_versions or candidate.prepare_request_id is None
                or set(sources) != set(candidate.source_versions)
                or set(candidate.source_versions.values()) != set(candidate.document_versions)
                or len(set(candidate.source_versions.values())) != len(candidate.source_versions)):
            raise ServiceError('STATE_CONFLICT',409)
        for source_id,version_id in candidate.source_versions.items():
            version = read_version(candidate.matter_id,version_id,actor,db)
            if version.sha256 != candidate.document_versions[version_id] or version.sha256 != sources[source_id].sha256:
                raise ServiceError('VERSION_CONFLICT',409)
    if state == 'completed' or candidate.review_run_id is not None:
        from ..review.storage import read_run
        if (candidate.matter_id is None or candidate.review_run_id is None
                or candidate.review_request_id is None or candidate.review_input_sha256 is None):
            raise ServiceError('STATE_CONFLICT',409)
        run = read_run(candidate.matter_id,candidate.review_run_id,actor,db=db,current=True)
        if (run.manifest.model_provider != 'mock' or dict(run.manifest.document_hashes) != dict(candidate.document_versions)
                or state != ('completed' if run.status == 'completed' else 'failed')):
            raise ServiceError('STATE_CONFLICT',409)
    updates,params = ['state=:state','updated_at=:at'],{'id':str(identifier),'state':state,'at':_at(),'expected':expected_state}
    for name in changes:
        value = getattr(candidate,name)
        column = name + '_json' if name in {'document_versions','source_versions'} else name
        params[name] = canonical_json({str(key):str(item) for key,item in value.items()}) if column.endswith('_json') else str(value) if isinstance(value,UUID) else value
        updates.append(column + '=:' + name)
    changed = db.execute(text('UPDATE task_executions SET '+','.join(updates)+' WHERE id=:id AND state=:expected'),params)
    if changed.rowcount != 1:
        raise ServiceError('STATE_CONFLICT',409)
    return read_execution(actor,identifier,db)


def quarantine_executions(db):
    result = db.execute(text("""UPDATE task_executions SET state='blocked',error='restored_read_only',
        updated_at=:at WHERE state IN ('prepared','creating_matter','awaiting_facts','queued','running')"""),{'at':_at()})
    return result.rowcount


def cancel_execution(actor, identifier, db):
    current = read_execution(actor,identifier,db)
    _write(actor,current.manifest.conversation_id,db)
    if current.state == 'blocked' and current.error == 'TASK_CANCELLED':
        return current
    if current.state not in {'prepared','creating_matter','awaiting_facts','queued'}:
        raise ServiceError('STATE_CONFLICT',409)
    return advance_execution(actor,identifier,'blocked',db,expected_state=current.state,error='TASK_CANCELLED')
