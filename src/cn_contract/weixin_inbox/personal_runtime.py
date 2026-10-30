"""One native-authorized, ephemeral connection over the existing durable services."""
import asyncio
from contextlib import asynccontextmanager
from io import BytesIO
import re
from uuid import UUID, uuid4
import httpx
from sqlalchemy import text
from .. import domain as d
from ..assistant import service, attachments, attachment_records, business, material_preparation
from ..assistant.providers import attempts
from ..review.model_adapter import strict_json
from ..ops.storage import require_active
from ..security import ServiceError, authenticate
from ..task_drafts import service as tasks
from ..weixin_transport import PersonalWeixinTransport, ProbeError
from . import personal, accounts, ingress, runtime_records as records

TARGET = ('workspace_id', 'conversation_id', 'scope_kind', 'scope_ref', 'binding_revision')
NOTICE = records.NOTICES


class PersonalWeixinRuntime:
    def __init__(self, database, native_model, generation_tasks, *, client_factory=httpx.Client):
        self.database, self.native_model, self.generation_tasks = database, native_model, generation_tasks
        self.client_factory = client_factory
        self._epoch = 0
        self._task = self._transport = self._client = self._value = self._actor = None
        self._account = self._mapping = self._context = self._context_event = None
        self._active_run = None
        self._verify = None
        self._status_actor = None
        self._status = d.PersonalWeixinStatus(state='disconnected')
        native_model.on_policy_change = self._policy_changed

    def _policy_changed(self, session_id=None):
        if session_id is None or self._actor is not None and self._actor.session_id == session_id:
            self.disable()

    def start(self, payload):
        try:
            value = d.NativePersonalWeixinStart.model_validate(payload)
            with self.database.session() as db:
                actor = authenticate(value.session_token, db)
                row = service._owned(actor, value.expected_scope.conversation_id, db)
                require_active(db)
                if service._snapshot(row) != value.expected_scope or row['archived_at']:
                    raise ValueError
            if value.automatic_policy and (value.automatic_policy.expected_config_version != self.native_model._config_version
                    or self.native_model._config is None):
                raise ValueError
            self.disable()
            self._value, self._actor = value, actor
            self._status_actor = (actor.user_id, actor.session_id)
            self._status = d.PersonalWeixinStatus(state='starting', conversation_id=value.expected_scope.conversation_id,
                automatic=value.automatic_policy is not None)
            self._task = asyncio.create_task(self._run(self._epoch), name='personal-weixin')
            return {'status':'started'}
        except (ValueError, TypeError):
            raise ServiceError('BLOCKED_LIVE', 403) from None

    def verify(self, payload):
        if (set(payload) != {'code'} or type(payload['code']) is not str
                or not re.fullmatch(r'[0-9]{4,12}', payload['code']) or self._status.state != 'need_verifycode'):
            raise ServiceError('BLOCKED_LIVE', 403)
        self._guard(self._epoch)
        self._verify = payload['code']
        return {'status':'accepted'}

    def disable(self):
        self._epoch += 1
        if self._active_run is not None and self._actor is not None:
            try:
                with self.database.session() as db:
                    service.cancel_run(self._actor, self._active_run, d.AssistantCancelInput(request_id=uuid4()), db)
            except Exception:
                pass  # Invalid/restored authorization is also fenced by the model runner.
        if self._transport is not None:
            self._transport.close()
        if self._task is not None:
            self._task.cancel()
        self._task = self._transport = self._client = self._value = self._actor = None
        self._account = self._mapping = self._context = self._context_event = self._active_run = self._verify = None
        self._status = d.PersonalWeixinStatus(state='disconnected')
        self._status_actor = None
        return {'status':'disabled'}

    def require_disconnected(self, cid):
        # Archive has already checked the owner/version. Session-hidden status is not a target guard.
        if ((self._value is not None and self._value.expected_scope.conversation_id == cid)
                or (self._status.conversation_id == cid and self._status.state != 'disconnected')):
            raise ServiceError('PERSONAL_WEIXIN_CONNECTED', 409)

    def status(self, actor, cid):
        with self.database.session() as db:
            service._owned(actor, cid, db)
        if self._status_actor != (actor.user_id,actor.session_id) or self._status.conversation_id != cid:
            return d.PersonalWeixinStatus(state='disconnected')
        if self._value is None:
            return self._status
        try:
            self._guard(self._epoch)
        except ServiceError:
            self.disable()
        return self._status

    def _guard(self, epoch):
        if epoch != self._epoch or self._value is None:
            raise ServiceError('BLOCKED_LIVE', 403)
        value = self._value
        if value.automatic_policy and value.automatic_policy.expected_config_version != self.native_model._config_version:
            raise ServiceError('BLOCKED_LIVE', 403)
        with self.database.session() as db:
            actor = authenticate(value.session_token, db)
            row = service._owned(actor, value.expected_scope.conversation_id, db)
            require_active(db)
            scope = service._snapshot(row)
            if row['archived_at'] or any(getattr(scope, key) != getattr(value.expected_scope, key) for key in TARGET):
                raise ServiceError('VERSION_CONFLICT', 409)
            if self._account:
                accounts._account(actor, self._account.id, db, mode='weixin_personal')
                mapping = accounts._mapping(accounts._mapping_row(self._mapping.id, db))
                if mapping.revoked_at or mapping.task_binding_id != self._mapping.task_binding_id:
                    raise ServiceError('BLOCKED_LIVE', 403)
            return actor, scope, row['composer_revision'], bool(row['draft_input'].strip())

    def _refresh(self, epoch):
        actor, scope, _, _ = self._guard(epoch)
        if self._mapping is None:
            return
        with self.database.session() as db:
            mapping = accounts._mapping(accounts._mapping_row(self._mapping.id, db))
            old = accounts._effective_scope(mapping, db)
            revision = len(accounts._grant_history(mapping, db))
        if old != scope:
            personal.refresh_personal_peer(actor, mapping.id, d.WeixinPeerRefreshInput(
                request_id=records.stable('scope', mapping.id, service._digest(scope.model_dump(mode='json'))),
                expected_grant_revision=revision, expected_scope_sha256=service._digest(old.model_dump(mode='json')),
                expected_scope=scope, reason='本次原生连接授权内的同任务材料与输入更新'), database=self.database)

    async def _io(self, epoch, callback, *args, **kwargs):
        self._guard(epoch)
        transport = self._transport
        def invoke():
            # Executor queueing can outlive the authority checked on the event loop.
            try:
                self._guard(epoch)
                if self._transport is not transport:
                    raise ServiceError('BLOCKED_LIVE', 403)
            except Exception:
                if transport is not None:
                    transport.close()
                raise
            return callback(*args, **kwargs)
        worker = asyncio.create_task(asyncio.to_thread(invoke))
        try:
            while not worker.done():
                await asyncio.wait((worker,), timeout=.2)
                self._guard(epoch)
            return worker.result()
        finally:
            # Cancelling the await does not stop its thread. Discard late results.
            if not worker.done():
                worker.add_done_callback(lambda task: None if task.cancelled() else task.exception())
            elif not worker.cancelled():
                worker.exception()

    async def _run(self, epoch):
        client = None
        try:
            self._guard(epoch)
            client = self.client_factory()
            transport = PersonalWeixinTransport(client=client)
            self._client, self._transport = client, transport
            url = await self._io(epoch, transport.start_qr)
            self._status = self._status.model_copy(update={'state':'waiting_scan','qr_url':url})
            while True:
                code, self._verify = self._verify, None
                state = await self._io(epoch, transport.poll_login, code)
                if state == 'confirmed':
                    break
                if state in {'expired', 'cancelled', 'error'}:
                    raise ProbeError('LOGIN_NOT_PENDING')
                self._status = self._status.model_copy(update={'state':'need_verifycode' if state == 'need_verifycode' else 'waiting_scan'})
                await asyncio.sleep(1)
            self._bind(epoch)
            errors, pending = 0, False
            while True:
                self._refresh(epoch)
                with self.database.session() as db:
                    self._account, _ = accounts._account(self._actor, self._account.id, db, mode='weixin_personal')
                try:
                    raw = await self._io(epoch, transport.poll_updates, self._account.upstream_cursor)
                except ProbeError:
                    errors += 1
                    if errors >= 3:
                        raise
                    await asyncio.sleep(min(errors * 2, 6))
                    continue
                errors = 0
                received = await self.ingest(epoch, raw)
                # Drain a burst before running; never execute on its first attachment.
                if not received:
                    await self.advance(epoch)
                    pending = False
                else:
                    pending = True
                await asyncio.sleep(1.5 if pending else 1)
        except asyncio.CancelledError:
            pass
        except Exception:
            if epoch == self._epoch:
                cid = self._status.conversation_id
                status_actor = self._status_actor
                self.disable()
                self._status_actor = status_actor
                self._status = d.PersonalWeixinStatus(state='paused', conversation_id=cid,
                    notice='连接已暂停。请在桌面检查登录、授权或材料格式后重新连接；未知发送不会自动重试。')
        finally:
            if client is not None:
                await asyncio.to_thread(client.close)

    def _bind(self, epoch):
        actor, scope, _, _ = self._guard(epoch)
        bot, peer = self._transport.identity()
        # Reconnect only refreshes the same historical target before binding.
        with self.database.session() as db:
            row = db.execute(text('SELECT * FROM weixin_accounts WHERE bot_account_id=:bot AND workspace_id=:wid'),
                {'bot':bot,'wid':str(scope.workspace_id)}).mappings().first()
            if row:
                account, _ = accounts._account(actor, row['id'], db, mode='weixin_personal')
                maps = db.execute(text('SELECT * FROM weixin_peer_bindings WHERE account_id=:id'),
                    {'id':row['id']}).mappings().all()
                if len(maps) != 1:
                    raise ServiceError('BLOCKED_LIVE',403)
                mapping = accounts._mapping(maps[0])
                if mapping.sender_peer_id != peer or any(getattr(mapping.scope,k) != getattr(scope,k) for k in TARGET):
                    raise ServiceError('BLOCKED_LIVE',403)
                self._account, self._mapping = account, mapping
        self._refresh(epoch)
        self._account, self._mapping = personal.bind_personal_peer(actor,
            d.WeixinAccountCreateInput(bot_account_id=bot, initial_cursor=self._account.initial_cursor if self._account else ''),
            sender_peer_id=peer, expected_scope=scope, database=self.database)
        self._status = self._status.model_copy(update={'state':'connected','qr_url':None,'notice':'已连接本人微信'})

    async def ingest(self, epoch, raw):
        actor, scope, _, _ = self._guard(epoch)
        # A desktop-started attempt may have begun while the long poll was in flight.
        while self._busy(scope.conversation_id):
            await asyncio.sleep(.2)
            actor, scope, _, _ = self._guard(epoch)
        self._refresh(epoch)
        _, messages = ingress._envelope(raw, self._account.upstream_cursor)
        accepted, contexts = [], []
        with self.database.session() as db:
            originals = {}
            for ordinal, message in enumerate(messages,1):
                descriptor = ingress._describe(actor, self._account, message, uuid4(), ordinal, originals, db, self.database.settings)
                if descriptor.status == 'accepted_pending_dispatch':
                    self._transport.validate_message(message)
                    accepted.append((message, descriptor.payload, descriptor.source_sha256))
                    contexts.append((message,descriptor.payload.event_id))
                elif descriptor.status == 'duplicate':
                    self._transport.validate_message(message)
                    contexts.append((message,descriptor.source_event_id))
        for message, payload, digest in accepted:
            for index, item in enumerate(message['item_list']):
                if item['type'] != 4:
                    continue
                identifier = records.stable('upload', self._account.id, payload.event_id, index, digest)
                original = attachments.find_attachment_request(actor, scope.conversation_id, identifier, database=self.database)
                if original is None:
                    data = await self._io(epoch, self._transport.download_file, message, item_index=index,
                        max_bytes=min(20, self.database.settings.upload_max_file_mib)*1024**2)
                    actor, current, _, _ = self._guard(epoch)
                    media = next(value for value in payload.media if value.media_id == payload.event_id + ':' + str(index))
                    original = attachments.ingest_attachment(actor, scope.conversation_id,
                        d.AssistantAttachmentInput(request_id=identifier, expected_scope=current,
                            original_name=media.name, mime=media.mime,
                            policy=d.AssistantMaterialPolicy(policy_id='assistant-local-files-v2', material_mode='local',
                                local_processing_accepted=True)), BytesIO(data), database=self.database)
                parse_id = records.stable('parse', identifier)
                parsed = attachments.find_parse_request(actor, scope.conversation_id, original.attachment.id, parse_id, database=self.database)
                if parsed is None:
                    actor, current, _, _ = self._guard(epoch)
                    parsed = attachments.parse_attachment(actor, scope.conversation_id, original.attachment.id,
                        d.AssistantAttachmentParseInput(request_id=parse_id, expected_scope=current), database=self.database)
                if parsed.parse.reading_status != 'readable':
                    raise ServiceError('MATERIAL_NOT_READABLE',409)
        self._refresh(epoch)
        receipt = personal.record_personal_poll(actor, self._account.id, d.WeixinPollInput(
            request_id=records.stable('poll', self._account.id, self._account.checkpoint_revision, service._digest(strict_json(raw.decode('utf-8')))),
            expected_revision=self._account.checkpoint_revision, expected_cursor=self._account.upstream_cursor), raw, database=self.database)
        # Dispatch durable pending history as well, including a crash after cursor commit.
        with self.database.session() as db:
            identifiers = tuple(db.scalars(text('''SELECT de.id FROM weixin_inbox_descriptors de
                JOIN weixin_poll_receipts p ON p.id=de.poll_id LEFT JOIN weixin_dispatch_receipts r ON r.descriptor_id=de.id
                WHERE p.account_id=:id AND de.status='accepted_pending_dispatch' AND r.id IS NULL
                ORDER BY p.next_revision,de.ordinal'''), {'id':str(self._account.id)}))
        for identifier in identifiers:
            self._guard(epoch)
            personal.dispatch_personal_descriptor(actor, self._account.id, identifier, database=self.database)
        self._resolve(epoch)
        for message, source_event_id in contexts:
            if self._transport.message_context(message):
                with self.database.session() as db:
                    event = db.scalar(text('SELECT id FROM task_inbox_events WHERE binding_id=:id AND event_id=:event'),
                        {'id':str(self._mapping.task_binding_id),'event':source_event_id})
                self._context, self._context_event = message, UUID(event) if event else None
        with self.database.session() as db:
            self._account, _ = accounts._account(actor, self._account.id, db, mode='weixin_personal')
        return bool(accepted)

    def _resolve(self, epoch):
        actor, scope, _, _ = self._guard(epoch)
        with self.database.session() as db:
            drafts = tasks.list_drafts(actor, scope.conversation_id, db).items
        for draft in drafts:
            if draft.state not in {'collecting','paused'}:
                continue
            resolved = {(x.event_id,x.media_id) for x in draft.media_resolutions}
            changes = []
            for event in draft.events:
                if event.binding_id != self._mapping.task_binding_id:
                    continue
                for media in event.media:
                    if (event.id,media.media_id) in resolved:
                        continue
                    ordinal = media.media_id.rsplit(':',1)[-1]
                    with self.database.session() as db:
                        digest = db.scalar(text('''SELECT de.source_sha256 FROM weixin_inbox_descriptors de
                            JOIN weixin_dispatch_receipts r ON r.descriptor_id=de.id WHERE r.task_event_id=:id'''),
                            {'id':str(event.id)})
                    upload = records.stable('upload', self._account.id, event.event_id, ordinal, digest)
                    original = attachments.find_attachment_request(actor, scope.conversation_id, upload, database=self.database)
                    if original is None:
                        raise ServiceError('VERSION_CONFLICT',409)
                    parsed = attachments.find_parse_request(actor, scope.conversation_id, original.attachment.id,
                        records.stable('parse',upload), database=self.database)
                    if parsed is None or parsed.parse.reading_status != 'readable':
                        raise ServiceError('MATERIAL_NOT_READABLE',409)
                    changes.append(d.TaskMediaResolutionInput(event_id=event.id,media_id=media.media_id,action='resolve',
                        replacement=media.model_copy(update={'attachment_id':original.attachment.id,
                            'sha256':original.attachment.sha256,'parse_revision':parsed.parse.revision,'status':'ready'})))
            if changes:
                with self.database.session() as db:
                    tasks.update_draft(actor,draft.id,d.TaskDraftUpdateInput(expected_revision=draft.revision,
                        media_resolutions=tuple(changes)),db)

    async def _reply(self, epoch, key, body, event_id=None):
        actor, _, _, _ = self._guard(epoch)
        if self._context is None or self._context_event is None:
            return
        body = records.bounded_reply(body)
        with self.database.session() as db:
            claim = records.claim(db, self._mapping.id, event_id or self._context_event, key, body)
        if claim is None:
            return
        outcome = await self._io(epoch, self._transport.send_text, text=body,
            client_id=str(claim.client_id), context_message=self._context)
        if outcome != 'unknown':
            with self.database.session() as db:
                db.execute(text('UPDATE weixin_personal_outbox SET status=:status WHERE client_id=:id AND status=\'unknown\''),
                    {'status':outcome,'id':str(claim.client_id)})

    async def advance(self, epoch):
        actor, scope, composer, dirty = self._guard(epoch)
        if dirty:
            self._status = self._status.model_copy(update={'notice':NOTICE['dirty_composer']})
            return
        if self._busy(scope.conversation_id):
            return
        # Desktop assignment can attach already-downloaded events between polls.
        self._resolve(epoch)
        with self.database.session() as db:
            view = tasks.list_drafts(actor, scope.conversation_id, db)
            known = records.links(db, self._mapping.id)
        if view.unassigned_events:
            await self._reply(epoch, 'ambiguous:' + str(view.unassigned_events[-1].id), NOTICE['ambiguous'])
            return
        linked = {item.draft_id for item in known}
        candidates = [draft for draft in view.items if draft.state == 'collecting' and draft.id not in linked
            and any(event.binding_id == self._mapping.task_binding_id for event in draft.events)]
        if len(candidates) > 1:
            await self._reply(epoch, 'ambiguous:' + str(self._context_event), NOTICE['ambiguous'])
            return
        if candidates:
            draft = candidates[0]
            with self.database.session() as db:
                manifest, blockers = tasks._manifest(actor, tasks._draft(actor,draft.id,db),db)
                parent_events = {row['id'] for row in tasks._events(draft.parent_draft_id,db)} if draft.parent_draft_id else set()
                fresh = [event for event in draft.events if event.id not in {UUID(value) for value in parent_events}]
                personal_source = next((event for event in reversed(fresh)
                    if event.binding_id == self._mapping.task_binding_id), None)
                question = '\n'.join(event.text for event in fresh if event.text.strip())
                parent_links = [item for item in known if item.draft_id == draft.parent_draft_id]
                previous = business._record(service._owned_run(actor,parent_links[-1].business_run_id,db),db)[1] if parent_links else None
            if personal_source is None:
                return
            if not question and previous and any(event.media for event in fresh):
                question = '请结合本次补充材料继续处理当前任务。'
            workflow = business.classify(question) or (previous.workflow if previous else None)
            reuse = {}
            if workflow in {'case','court'} and not any(event.media for event in manifest.events):
                with self.database.session() as db:
                    history = business.history(actor,scope.conversation_id,db)
                    by_task = {item.task_id:item for item in history if item.task_id}
                    source = previous or (next(iter(by_task.values())) if len(by_task)==1 else None)
                    if source and source.scope.materials_revision == scope.materials_revision:
                        reuse = {item.attachment_id:item for item in attachment_records.items(
                            service._owned(actor,scope.conversation_id,db),db)}
                        previous = source
            reason = ('instruction_required' if not question else 'ambiguous' if not workflow or workflow == 'ambiguous'
                else next((x for x in blockers if x not in {'main_contract_required','main_contract_selection_required','instruction_required'}),None)
                or ('main_contract_required' if workflow != 'sales' and not any(e.media for e in manifest.events) and not reuse else None)
                or ('main_contract_selection_required' if workflow == 'contract' and 'main_contract_selection_required' in blockers else None))
            if reason:
                await self._reply(epoch, f'notice:{draft.id}:{draft.revision}:{reason}',
                    NOTICE.get(reason,NOTICE['media_not_readable']), personal_source.id)
                return
            if self._value.automatic_policy is None:
                await self._reply(epoch, f'notice:{draft.id}:{draft.revision}:collect', NOTICE['collect_only'], personal_source.id)
                return
            selected = dict(reuse)
            for event in manifest.events:
                for media in event.media:
                    if not media.excluded and media.attachment_id:
                        selected[media.attachment_id] = d.AssistantMaterialRef(attachment_id=media.attachment_id,parse_revision=media.parse_revision)
            actor, scope, composer, dirty = self._guard(epoch)
            if dirty:
                return
            attachments.select_materials(actor, scope.conversation_id, d.AssistantMaterialSelectionInput(
                request_id=records.stable('selection',draft.id,draft.revision),expected_scope=scope,items=tuple(selected.values())),database=self.database)
            actor, scope, composer, dirty = self._guard(epoch)
            if dirty:
                return
            with self.database.session() as db:
                result = business.submit(actor,scope.conversation_id,d.BusinessInput(
                    request_id=records.stable('business',draft.id,draft.revision),expected_scope=scope,
                    expected_composer_revision=composer,content=question,workflow=workflow,
                    task_id=previous.task_id if previous and previous.workflow == workflow else None),db,personal_draft_id=draft.id)
                link = records.add_link(db,self._mapping.id,draft,personal_source.id,result)
            await self._execute(epoch, link)
        else:
            # Existing attempt lookup is replay-safe; missing attempts may only use unchanged parent scope.
            for link in known:
                await self._execute(epoch, link)

    def _busy(self, cid):
        with self.database.session() as db:
            return bool(db.scalar(text('''SELECT 1 FROM assistant_runs WHERE conversation_id=:id
                AND state IN ('queued','preparing','routing','retrieving','generating','persisting')'''), {'id':str(cid)}))

    def _execution_parent(self, actor, link, db, attempt=None):
        parent = service._owned_run(actor, link.business_run_id, db)
        run = service._owned_run(actor, attempt.run_id, db) if attempt else None
        cancelled = parent['cancel_requested'] or parent['state'] == 'cancelled'
        if not cancelled:
            material_preparation.require_parent_active(parent)
        # Only explicit per-run cancellation is local; other authority errors propagate.
        if cancelled or (run and (run['cancel_requested'] or run['state'] == 'cancelled')):
            if attempt and attempt.state in {'reserved','sending'}:
                service.cancel_run(actor, attempt.run_id, d.AssistantCancelInput(request_id=uuid4()), db)
            return None
        return parent

    async def _execute(self, epoch, link):
        actor, scope, composer, dirty = self._guard(epoch)
        if dirty or self._value.automatic_policy is None:
            return
        with self.database.session() as db:
            stored = db.execute(text('''SELECT a.id FROM assistant_model_attempts a JOIN assistant_runs r ON r.id=a.run_id
                WHERE r.request_id=:id'''),{'id':str(link.model_request_id)}).first()
            if stored:
                attempt = attempts.read_attempt(actor,UUID(stored[0]),db)
                # A durable claim (including unknown) permanently ends this reply's replay.
                if attempt.state not in {'reserved','sending'} and db.scalar(text(
                        'SELECT 1 FROM weixin_personal_outbox WHERE client_id=:id'),
                        {'id':str(records.stable('reply',self._mapping.id,'model:' + str(attempt.id)))}):
                    return
            else:
                attempt = None
            parent = self._execution_parent(actor,link,db,attempt)
            if parent is None or attempt is None and d.ScopeSnapshot.model_validate_json(parent['scope_snapshot']) != scope:
                return
        if attempt is None:
            selection = d.MainMaterialSelection(request_id=link.model_request_id,expected_scope=scope,
                expected_composer_revision=composer,parent_business_run_id=link.business_run_id)
            basis = material_preparation.preview(actor,selection,self.database,self.native_model._config)
            self._guard(epoch)
            policy = self._value.automatic_policy
            self.native_model.authorize_material(d.NativeMaterialAuthorization(session_token=self._value.session_token,
                expected_config_version=policy.expected_config_version,basis=basis,max_total_usd=policy.max_total_usd,
                valid_for_seconds=120).model_dump(mode='python'))
            attempt = self.generation_tasks.submit_material(actor,scope.conversation_id,selection)
        self._active_run = attempt.run_id
        while attempt.state in {'reserved','sending'}:
            await asyncio.sleep(.1)
            self._guard(epoch)
            with self.database.session() as db:
                attempt = attempts.read_attempt(actor,attempt.id,db)
                if self._execution_parent(actor,link,db,attempt) is None:
                    self._active_run = None
                    return
        self._active_run = None
        self._refresh(epoch)
        with self.database.session() as db:
            if self._execution_parent(actor,link,db,attempt) is None:
                return
        body = records.model_reply(attempt)
        await self._reply(epoch,'model:' + str(attempt.id),body,link.source_event_id)


def attach_runtime(app, runtime):
    from fastapi import Request, HTTPException
    from fastapi.responses import Response, JSONResponse
    from ..web.request_context import actor_in
    previous = app.router.lifespan_context
    app.state.personal_weixin_runtime = runtime

    @app.get('/api/assistant/conversations/{identifier}/personal-weixin/status')
    async def status(identifier: UUID, request: Request):
        with runtime.database.session() as db:
            actor = actor_in(request,db)
        return JSONResponse(runtime.status(actor,identifier).model_dump(mode='json'),headers={'Cache-Control':'no-store'})

    @app.get('/api/assistant/conversations/{identifier}/personal-weixin/qr.svg')
    async def qr(identifier: UUID, request: Request):
        with runtime.database.session() as db:
            actor = actor_in(request,db)
        value = runtime.status(actor,identifier)
        if request.query_params:
            raise HTTPException(400)
        if value.state != 'waiting_scan' or not value.qr_url:
            raise HTTPException(404)
        import qrcode
        from qrcode.image.svg import SvgPathImage
        # Only the runtime's validated, ephemeral QR content enters this local encoder.
        image = qrcode.make(value.qr_url, image_factory=SvgPathImage)
        return Response(image.to_string(),media_type='image/svg+xml',headers={
            'Cache-Control':'no-store','X-Content-Type-Options':'nosniff',
            'Content-Security-Policy':"default-src 'none'; style-src 'none'; sandbox"})

    @asynccontextmanager
    async def lifespan(application):
        async with previous(application):
            try:
                yield
            finally:
                runtime.disable()
    app.router.lifespan_context = lifespan
