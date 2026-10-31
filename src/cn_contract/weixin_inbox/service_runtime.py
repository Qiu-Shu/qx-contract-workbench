"""Workspace-scoped personal Weixin service using the existing business executor."""
import asyncio
import hashlib
from datetime import datetime, timezone
from io import BytesIO
from types import SimpleNamespace
from uuid import UUID
from sqlalchemy import text
from .. import domain as d, weixin_offline as wire
from ..assistant import service, attachments, attachment_records, business, material_preparation
from ..assistant.providers import attempts
from ..config import canonical_json
from ..ops.storage import require_active
from ..security import ServiceError, authenticate
from ..task_drafts import service as tasks
from ..weixin_transport import PersonalWeixinTransport, ProbeError
from . import accounts, ingress, service_records as journal, runtime_records as records
from .personal_runtime import PersonalWeixinRuntime
from .service_routing import decide,readiness


class ServiceWeixinRuntime(PersonalWeixinRuntime):
    def __init__(self, database, native_model, generation_tasks, *, judge=None, **kwargs):
        previous=native_model.on_policy_change
        super().__init__(database,native_model,generation_tasks,**kwargs)
        native_model.on_policy_change=previous
        self.judge=judge
        self._connection=None
        self._contexts={}
        self._collector_task=None
        self._advance_lock=asyncio.Lock()

    def start(self,payload):
        value=d.NativeServiceWeixinStart.model_validate(payload)
        with self.database.session() as db:
            actor=authenticate(value.session_token,db)
            require_active(db)
            if service._workspace_id(db)!=value.workspace_id:
                raise ServiceError('CROSS_MATTER_DENIED',403)
        if value.automatic_policy and (self.native_model._config is None
                or value.automatic_policy.expected_config_version!=self.native_model._config_version):
            raise ServiceError('BLOCKED_LIVE',403)
        self.disable()
        self._value,self._actor=value,actor
        self._status_actor=(actor.user_id,actor.session_id)
        self._status=d.PersonalWeixinStatus(state='starting',automatic=value.automatic_policy is not None)
        self._task=asyncio.create_task(self._run(self._epoch),name='weixin-service')
        return {'status':'started'}

    def disable(self):
        if self._collector_task:
            self._collector_task.cancel()
        result=super().disable()
        self._collector_task=None
        self._connection=None
        self._contexts={}
        return result

    def require_disconnected(self,cid):
        return  # Connection is workspace-owned; destination checks remain per execution.

    def status(self,actor,cid=None):
        if self._status_actor!=(actor.user_id,actor.session_id):
            return d.PersonalWeixinStatus(state='disconnected')
        if self._value:
            try:self._guard(self._epoch)
            except ServiceError:self.disable()
        return self._status

    def details(self,actor):
        status=self.status(actor).model_dump(mode='json')
        status.update(mode='service',capabilities=['contract','case','court','sales'],
            jev_available=bool(self.judge and self.judge.available()),batches=[])
        if self._value and self._status_actor==(actor.user_id,actor.session_id):
            status['workspace_id']=str(self._value.workspace_id)
            if self._connection:
                with self.database.session() as db:
                    status['batches']=[dict(row) for row in db.execute(text('''SELECT id,revision,state,conversation_id,
                        draft_id,workflow,decision_json FROM weixin_service_batches WHERE connection_id=:id
                        ORDER BY rowid DESC LIMIT 50'''),{'id':self._connection['id']}).mappings()]
        return status

    def _guard(self,epoch):
        if epoch!=self._epoch or self._value is None:
            raise ServiceError('BLOCKED_LIVE',403)
        with self.database.session() as db:
            actor=authenticate(self._value.session_token,db)
            require_active(db)
            if service._workspace_id(db)!=self._value.workspace_id:
                raise ServiceError('CROSS_MATTER_DENIED',403)
            policy=self._value.automatic_policy
            if policy and policy.expected_config_version!=self.native_model._config_version:
                raise ServiceError('BLOCKED_LIVE',403)
            if self._account:
                accounts._account(actor,self._account.id,db,mode='weixin_personal')
        return actor,None,0,False

    def _target(self,epoch,cid):
        actor,_,_,_=self._guard(epoch)
        with self.database.session() as db:
            row=tasks._write(actor,cid,db)
            return actor,service._snapshot(row),row['composer_revision'],bool(row['draft_input'].strip())

    def _bind(self,epoch):
        actor,_,_,_=self._guard(epoch)
        bot,peer=self._transport.identity()
        self._account,self._connection=journal.bind(actor,self._value.workspace_id,bot,peer,self.database)
        self._status=self._status.model_copy(update={'state':'connected','qr_url':None,'notice':'服务台已连接本人微信'})

    async def _run(self,epoch):
        client=None
        try:
            self._guard(epoch)
            client=self.client_factory()
            self._client,self._transport=client,PersonalWeixinTransport(client=client)
            url=await self._io(epoch,self._transport.start_qr)
            self._status=self._status.model_copy(update={'state':'waiting_scan','qr_url':url})
            while True:
                code,self._verify=self._verify,None
                state=await self._io(epoch,self._transport.poll_login,code)
                if state=='confirmed':break
                if state in {'expired','cancelled','error'}:raise ProbeError('LOGIN_NOT_PENDING')
                self._status=self._status.model_copy(update={'state':'need_verifycode' if state=='need_verifycode' else 'waiting_scan'})
                await asyncio.sleep(1)
            self._bind(epoch)
            async def collect():
                while True:
                    await self.advance(epoch)
                    await asyncio.sleep(.2)
            self._collector_task=asyncio.create_task(collect())
            while True:
                if self._collector_task.done():self._collector_task.result()
                raw=await self._io(epoch,self._transport.poll_updates,self._connection['cursor'])
                await self.ingest(epoch,raw)
                await asyncio.sleep(.2)
        except asyncio.CancelledError:
            pass
        except Exception:
            if epoch==self._epoch:
                actor=self._status_actor
                self.disable();self._status_actor=actor
                self._status=d.PersonalWeixinStatus(state='paused',notice='服务台连接已暂停；已收材料保留，未知请求不重发。')
        finally:
            if self._collector_task:self._collector_task.cancel()
            if client:await asyncio.to_thread(client.close)

    async def ingest(self,epoch,raw):
        self._guard(epoch)
        connection=dict(self._connection)
        cursor,messages=ingress._envelope(raw,connection['cursor'])
        values=[]
        identity=SimpleNamespace(bot_account_id=self._account.bot_account_id,sender_peer_id=connection['peer_id'])
        for message in messages:
            request=wire._event(message,identity,self.database.settings)
            self._transport.validate_message(message)
            digest=wire._hash(message)
            identifier=str(records.stable('service-event',connection['id'],request.event_id))
            with self.database.session() as db:
                old=db.execute(text('SELECT source_sha256 FROM weixin_service_events WHERE id=:id'),{'id':identifier}).first()
            media={}
            if old and old[0]!=digest:raise ServiceError('VERSION_CONFLICT',409)
            if not old:
                for item in request.media:
                    index=int(item.media_id.rsplit(':',1)[1])
                    media[item.media_id]=await self._io(epoch,self._transport.download_file,message,item_index=index,
                        max_bytes=min(20,self.database.settings.upload_max_file_mib)*1024**2)
            values.append((request,digest,media))
            # Context capabilities are ephemeral and indexed by immutable source, never newest-message global state.
            if self._transport.message_context(message):self._contexts[identifier]=message
        self._guard(epoch)
        with accounts._transaction(self.database) as db:
            added=journal.collect(connection,values,cursor,db,response_sha256=hashlib.sha256(raw).hexdigest())
            self._connection=dict(db.execute(text('SELECT * FROM weixin_service_connections WHERE id=:id'),
                {'id':connection['id']}).mappings().one())
        return bool(added)

    def _candidates(self,actor):
        result=[]
        with self.database.session() as db:
            ids=list(db.scalars(text('''SELECT id FROM assistant_conversations WHERE owner_id=:owner
                AND workspace_id=:workspace AND archived_at IS NULL ORDER BY rowid'''),
                {'owner':str(actor.user_id),'workspace':str(self._value.workspace_id)}))
            for cid in ids:
                try:
                    row=service._owned(actor,cid,db)
                    # Empty desktop chats do not compete as legal matters.
                    if db.scalar(text('SELECT 1 FROM assistant_messages WHERE conversation_id=:id LIMIT 1'),{'id':cid}) \
                            or db.scalar(text('SELECT 1 FROM weixin_service_batches WHERE conversation_id=:id LIMIT 1'),{'id':cid}):
                        result.append({'id':cid,'title':row['display_title']})
                except ServiceError:continue
        return result

    async def _send(self,epoch,event_id,key,body):
        self._guard(epoch)
        context=self._contexts.get(str(event_id))
        if context is None:
            self._status=self._status.model_copy(update={'notice':'成果已保存；原消息回复上下文已失效，请在桌面查看。'})
            return
        body=records.bounded_reply(body)
        with accounts._transaction(self.database) as db:
            cid=db.scalar(text('''SELECT b.conversation_id FROM weixin_service_batches b
                JOIN weixin_service_batch_events e ON e.batch_id=b.id WHERE e.event_id=:id'''),{'id':str(event_id)})
            claim=journal.claim(self._connection['id'],event_id,key,body,db)
        if claim is None:return
        transport=self._transport
        def send():
            if cid:self._target(epoch,cid)
            return transport.send_text(text=body,client_id=str(claim),context_message=context)
        outcome=await self._io(epoch,send)
        if outcome!='unknown':
            with self.database.session() as db:
                db.execute(text("UPDATE weixin_service_outbox SET status=:status WHERE client_id=:id AND status='unknown'"),
                    {'status':outcome,'id':str(claim)})

    async def advance(self,epoch,*,now=None):
        if self._advance_lock.locked():return
        async with self._advance_lock:
            actor,_,_,_=self._guard(epoch)
            now=now or datetime.now(timezone.utc)
            with self.database.session() as db:
                batches=[dict(row) for row in db.execute(text('''SELECT * FROM weixin_service_batches
                    WHERE connection_id=:id AND state NOT IN ('held','completed') ORDER BY rowid'''),
                    {'id':self._connection['id']}).mappings()]
            for batch in batches:
                if batch['state']!='routed' and datetime.fromisoformat(batch['deadline'])>now:continue
                try:
                    if batch['state']=='executing':
                        await self._execute_batch(epoch,batch)
                    else:
                        await self._advance_batch(epoch,batch)
                except ServiceError as error:
                    if error.code in {'BLOCKED_LIVE','AUTHORIZATION_REQUIRED'}:raise
                    self._status=self._status.model_copy(update={'notice':'材料已保留，目标事项的版本、授权或材料状态需检查。'})

    async def _advance_batch(self,epoch,batch):
        actor,_,_,_=self._guard(epoch)
        with self.database.session() as db:
            sources=journal.events(batch['id'],db)
        if not sources:return
        question='\n'.join(journal.payload(e).text for e in sources if journal.payload(e).text.strip())
        source_id=sources[-1]['id']
        if not batch['conversation_id']:
            reference=None
            refs=[journal.payload(e).reply_to_event_id for e in sources if journal.payload(e).reply_to_event_id]
            if refs:
                with self.database.session() as db:
                    targets=set(db.scalars(text('''SELECT b.conversation_id FROM weixin_service_events e
                        JOIN weixin_service_batch_events be ON be.event_id=e.id JOIN weixin_service_batches b ON b.id=be.batch_id
                        WHERE e.connection_id=:id AND e.event_id=:ref AND b.conversation_id IS NOT NULL'''),
                        {'id':self._connection['id'],'ref':refs[-1]}))
                    if len(targets)==1:reference=next(iter(targets))
            candidates=self._candidates(actor)
            decision=decide(question,candidates,reference=reference)
            if self.judge and self._value.automatic_policy is not None and decision.action!='ack' and question.strip():
                assessment=await self.judge.assess(actor,self._connection['id'],batch['id'],candidates,
                    current=lambda:self._epoch==epoch)
                self._guard(epoch)
                with self.database.session() as db:
                    revision=db.scalar(text('SELECT revision FROM weixin_service_batches WHERE id=:id'),{'id':batch['id']})
                if revision!=batch['revision']:return
                if assessment and assessment.status=='ok':
                    answers={key:answer.choice for key,answer in assessment.answers.items() if answer.confidence>=.8}
                    changes={}
                    if answers.get('workflow') in {'case','court','contract','sales'} and not decision.workflow:
                        changes['workflow']=answers['workflow']
                    if answers.get('material_kind'):
                        changes['material_kind']=answers['material_kind']
                    if decision.relation=='unassigned' and answers.get('readiness')=='start':
                        if not candidates and answers.get('relation')=='new' and (decision.workflow or changes.get('workflow')):
                            changes.update(action='start',relation='new')
                        elif len(candidates)==1 and answers.get('relation')=='candidate_a':
                            changes.update(action='start',relation='existing',conversation_id=candidates[0]['id'])
                    # Multiple plausible matters always require an explicit name/reference, even at high confidence.
                    explicit_start=readiness(question)=='collecting'
                    if answers.get('readiness')=='wait' and not explicit_start:
                        changes.update(action='wait',notice='材料已保留，请发送完毕后说“继续”或补充处理要求。')
                    decision=decision.model_copy(update=changes)
            explicit_workflow=next((choice for choice in (business.classify(journal.payload(e).text)
                for e in reversed(sources)) if choice and choice!='ambiguous'),None)
            if explicit_workflow:
                decision=decision.model_copy(update={'workflow':explicit_workflow})
            if decision.action in {'wait','clarify','ack'}:
                with self.database.session() as db:
                    changed=db.execute(text('''UPDATE weixin_service_batches SET state=:state,decision_json=:decision
                        WHERE id=:id AND revision=:revision AND conversation_id IS NULL'''),
                        {'id':batch['id'],'revision':batch['revision'],'state':{'wait':'waiting','clarify':'clarify','ack':'completed'}[decision.action],
                         'decision':canonical_json(decision.model_dump(mode='json'))})
                if changed.rowcount:await self._send(epoch,source_id,'decision:'+batch['id']+':'+str(batch['revision']),decision.notice)
                return
            with accounts._transaction(self.database) as db:
                current=db.execute(text('SELECT * FROM weixin_service_batches WHERE id=:id'),{'id':batch['id']}).mappings().one()
                if current['revision']!=batch['revision'] or current['conversation_id']:return
                if decision.relation=='new':
                    view=service.create_conversation(actor,d.AssistantConversationCreateInput(
                        request_id=records.stable('service-conversation',batch['id']),display_title=question[:60]),db)
                    cid=str(view.scope.conversation_id)
                else:
                    cid=decision.conversation_id
                    tasks._write(actor,cid,db)
                db.execute(text('''UPDATE weixin_service_batches SET state='routed',conversation_id=:cid,
                    workflow=:workflow,decision_json=:decision WHERE id=:id'''),
                    {'id':batch['id'],'cid':cid,'workflow':decision.workflow,'decision':canonical_json(decision.model_dump(mode='json'))})
                batch.update(conversation_id=cid,workflow=decision.workflow,state='routed')
        cid=batch['conversation_id']
        actor,scope,composer,dirty=self._target(epoch,cid)
        if dirty or self._busy(cid):return
        # Route is frozen before registering originals. Later intake is another batch.
        uploaded=[]
        excerpts=[]
        for source in sources:
            event=journal.payload(source)
            for media in event.media:
                identifier=records.stable('service-upload',source['id'],media.media_id)
                original=attachments.find_attachment_request(actor,cid,identifier,database=self.database)
                if original is None:
                    with self.database.session() as db:
                        data=db.execute(text('SELECT data,sha256 FROM weixin_service_media WHERE event_id=:id AND media_id=:media'),
                            {'id':source['id'],'media':media.media_id}).one()
                    if hashlib.sha256(data[0]).hexdigest()!=data[1]:raise ServiceError('VERSION_CONFLICT',409)
                    actor,scope,_,dirty=self._target(epoch,cid)
                    if dirty:return
                    original=attachments.ingest_attachment(actor,cid,d.AssistantAttachmentInput(request_id=identifier,
                        expected_scope=scope,original_name=media.name,mime=media.mime,
                        policy=d.AssistantMaterialPolicy(policy_id='assistant-local-files-v2',material_mode='local',local_processing_accepted=True)),
                        BytesIO(data[0]),database=self.database)
                parse_id=records.stable('parse',identifier)
                parsed=attachments.find_parse_request(actor,cid,original.attachment.id,parse_id,database=self.database)
                if parsed is None:
                    actor,scope,_,_=self._target(epoch,cid)
                    parsed=attachments.parse_attachment(actor,cid,original.attachment.id,
                        d.AssistantAttachmentParseInput(request_id=parse_id,expected_scope=scope),database=self.database)
                if parsed.parse.reading_status!='readable':
                    await self._send(epoch,source_id,'unreadable:'+batch['id'],records.NOTICES['media_not_readable']);return
                uploaded.append((source['id'],media.model_copy(update={'attachment_id':original.attachment.id,
                    'sha256':original.attachment.sha256,'parse_revision':parsed.parse.revision,'status':'ready'})))
                excerpts.extend(anchor.quote for anchor in parsed.parse.result.anchors)
        actor,scope,composer,dirty=self._target(epoch,cid)
        if dirty:return
        with self.database.session() as db:
            history=business.history(actor,cid,db)
            workflow=batch['workflow'] or (history[-1].workflow if history else None)
        if self.judge and self._value.automatic_policy is not None:
            before=scope
            result=None
            if not workflow:
                result=await self.judge.assist(actor,d.SharedJudgeInput(expected_scope=scope,purpose='primary_intent',text=question[:12000]),
                    current=lambda:self._epoch==epoch)
            if self._target(epoch,cid)[1]!=before:return
            if not workflow and result and result.status=='ok':
                answer=result.answers.get('primary_intent')
                if answer and answer.confidence>=.8:
                    workflow={'contract_review':'contract','material_organize':'case','client_reply':'sales'}.get(answer.choice)
            if excerpts:
                material=await self.judge.assist(actor,d.SharedJudgeInput(expected_scope=scope,purpose='material_kind',
                    text='\n'.join(excerpts)[:12000]),current=lambda:self._epoch==epoch)
                if self._target(epoch,cid)[1]!=before:return
                if material and material.status=='ok':
                    answer=material.answers.get('material_kind')
                    if answer and answer.confidence>=.8:
                        with self.database.session() as db:
                            saved=db.scalar(text('SELECT decision_json FROM weixin_service_batches WHERE id=:id'),{'id':batch['id']})
                            decision=d.ServiceRouteDecision.model_validate_json(saved).model_copy(update={'material_kind':answer.choice})
                            db.execute(text('UPDATE weixin_service_batches SET decision_json=:decision WHERE id=:id'),
                                {'id':batch['id'],'decision':canonical_json(decision.model_dump(mode='json'))})
        actor,scope,composer,dirty=self._target(epoch,cid)
        if dirty or self._busy(cid):return
        if not workflow:
            with self.database.session() as db:
                db.execute(text("UPDATE weixin_service_batches SET state='waiting' WHERE id=:id"),{'id':batch['id']})
            return
        if not uploaded and workflow!='sales':
            with self.database.session() as db:
                selected=attachment_records.items(service._owned(actor,cid,db),db)
            if not selected:
                with self.database.session() as db:
                    db.execute(text("UPDATE weixin_service_batches SET state='waiting' WHERE id=:id"),{'id':batch['id']})
                await self._send(epoch,source_id,'needs-material:'+batch['id'],records.NOTICES['main_contract_required']);return
        else:
            selected=tuple(d.AssistantMaterialRef(attachment_id=m.attachment_id,parse_revision=m.parse_revision) for _,m in uploaded)
            # Continuations keep prior case evidence and add late material, without changing earlier manifests.
            if history:
                with self.database.session() as db:
                    prior=attachment_records.items(service._owned(actor,cid,db),db)
                selected=tuple({x.attachment_id:x for x in (*prior,*selected)}.values())
        mains=[m for _,m in uploaded if ('主合同' in m.name or m.name in question)
            and not any(word in m.name for word in ('补充','附件'))]
        if workflow=='contract' and len(uploaded)>1 and len(mains)!=1 and not batch['draft_id']:
            with self.database.session() as db:
                db.execute(text("UPDATE weixin_service_batches SET state='waiting' WHERE id=:id"),{'id':batch['id']})
            await self._send(epoch,source_id,'main:'+batch['id'],'请说明哪份文件是主合同，回复完整文件名；其他材料作为补充。')
            return
        with self.database.session() as db:
            binding=tasks._create_binding(actor,cid,db,channel='weixin_personal')
            if batch['draft_id']:
                draft=tasks.read_draft(actor,batch['draft_id'],db)
            else:
                previous=db.execute(text('''SELECT r.draft_id FROM weixin_service_runs r
                    JOIN weixin_service_batches b ON b.id=r.batch_id WHERE b.conversation_id=:cid ORDER BY r.rowid DESC LIMIT 1'''),
                    {'cid':cid}).first()
                parent=tasks._draft(actor,previous[0],db) if previous else None
                draft_id=tasks._new_draft(cid,db,parent=parent)
                for source in sources:
                    request=journal.payload(source).model_copy(update={'task_id':UUID(draft_id),'reply_to_event_id':None,
                        'media':tuple(m for e,m in uploaded if e==source['id'])})
                    receipt=tasks._receive_batch(actor,binding.id,d.TaskInboxBatchInput(expected_cursor=binding.cursor,
                        next_cursor=binding.cursor+1,events=(request,)),db,channel='weixin_personal')
                    binding=receipt.binding
                    for accepted in receipt.events:
                        if accepted.task_id is None:
                            tasks._attach(draft_id,tasks._row('task_inbox_events',accepted.id,db),db)
                draft=tasks.read_draft(actor,draft_id,db)
                db.execute(text('UPDATE weixin_service_batches SET draft_id=:draft,workflow=:workflow WHERE id=:id'),
                    {'id':batch['id'],'draft':draft_id,'workflow':workflow})
                batch.update(draft_id=draft_id,workflow=workflow)
            if workflow=='contract' and len(uploaded)>1 and draft.main_attachment_id is None:
                if len(mains)==1:
                    draft=tasks.update_draft(actor,draft.id,d.TaskDraftUpdateInput(expected_revision=draft.revision,
                        main_attachment_id=mains[0].attachment_id),db)
        if workflow=='contract' and uploaded and draft.main_attachment_id is None:
            await self._send(epoch,source_id,'main:'+batch['id'],'请说明哪份文件是主合同，回复完整文件名；其他材料作为补充。');return
        if self._value.automatic_policy is None:
            await self._send(epoch,source_id,'collect:'+batch['id'],records.NOTICES['collect_only']);return
        if selected:
            request_id=records.stable('service-selection',batch['id'])
            with self.database.session() as db:
                accepted=attachment_records.operation(cid,request_id,db)
            selection_scope=scope
            if accepted:
                # A committed selection advances only materials_revision. Reconstruct the exact
                # original request so the existing receipt hash also fences other scope changes.
                if scope.materials_revision!=accepted['revision']:
                    raise ServiceError('VERSION_CONFLICT',409)
                selection_scope=scope.model_copy(update={'materials_revision':accepted['revision']-1})
            attachments.select_materials(actor,cid,d.AssistantMaterialSelectionInput(request_id=request_id,
                expected_scope=selection_scope,items=selected),database=self.database)
        actor,scope,composer,dirty=self._target(epoch,cid)
        if dirty:return
        with self.database.session() as db:
            result=business.submit(actor,cid,d.BusinessInput(request_id=records.stable('service-business',batch['id']),
                expected_scope=scope,expected_composer_revision=composer,content=question,workflow=workflow),db,
                personal_draft_id=draft.id if uploaded else None)
            link=dict(id=str(records.stable('service-link',batch['id'])),batch_id=batch['id'],connection_id=self._connection['id'],
                draft_id=str(draft.id),draft_revision=draft.revision,source_event_id=source_id,business_run_id=str(result.run_id),
                model_request_id=str(records.stable('service-model',batch['id'])),scope_json=canonical_json(result.scope.model_dump(mode='json')),
                created_at=service._at())
            ingress._insert('weixin_service_runs',link,db)
            db.execute(text("UPDATE weixin_service_batches SET state='executing' WHERE id=:id"),{'id':batch['id']})
        await self._execute_batch(epoch,batch)

    async def _execute_batch(self,epoch,batch):
        actor,scope,composer,dirty=self._target(epoch,batch['conversation_id'])
        if dirty or self._value.automatic_policy is None:return
        with self.database.session() as db:
            link=db.execute(text('SELECT * FROM weixin_service_runs WHERE batch_id=:id'),{'id':batch['id']}).mappings().one()
            parent=service._owned_run(actor,link['business_run_id'],db)
            material_preparation.require_parent_active(parent)
            stored=db.scalar(text('''SELECT a.id FROM assistant_model_attempts a JOIN assistant_runs r ON r.id=a.run_id
                WHERE r.request_id=:id'''),{'id':link['model_request_id']})
            attempt=attempts.read_attempt(actor,UUID(stored),db) if stored else None
        if attempt is None:
            if scope!=d.ScopeSnapshot.model_validate_json(link['scope_json']):return
            selection=d.MainMaterialSelection(request_id=link['model_request_id'],expected_scope=scope,
                expected_composer_revision=composer,parent_business_run_id=link['business_run_id'])
            basis=material_preparation.preview(actor,selection,self.database,self.native_model._config)
            self._target(epoch,batch['conversation_id'])
            policy=self._value.automatic_policy
            self.native_model.authorize_material(d.NativeMaterialAuthorization(session_token=self._value.session_token,
                expected_config_version=policy.expected_config_version,basis=basis,max_total_usd=policy.max_total_usd,
                valid_for_seconds=120).model_dump(mode='python'))
            attempt=self.generation_tasks.submit_material(actor,scope.conversation_id,selection)
        self._active_run=attempt.run_id
        while attempt.state in {'reserved','sending'}:
            await asyncio.sleep(.1)
            self._target(epoch,batch['conversation_id'])
            with self.database.session() as db:
                attempt=attempts.read_attempt(actor,attempt.id,db)
                material_preparation.require_parent_active(service._owned_run(actor,link['business_run_id'],db))
        self._active_run=None
        self._target(epoch,batch['conversation_id'])
        await self._send(epoch,link['source_event_id'],'model:'+str(attempt.id),records.model_reply(attempt))
        with self.database.session() as db:
            db.execute(text("UPDATE weixin_service_batches SET state='completed' WHERE id=:id"),{'id':batch['id']})
