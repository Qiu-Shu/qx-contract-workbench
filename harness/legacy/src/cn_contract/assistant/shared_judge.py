"""Shared authenticated assistance using the configured Jev provider and a separate claim ledger.

Original run-bound Jev purposes, templates and hashes are unchanged. This path is
pre-business assistance, with one durable send claim per exact scope/input/config.
"""
import asyncio
import json
from sqlalchemy import text
from .. import domain as d
from ..config import canonical_json
from ..ops.storage import require_active
from ..security import ServiceError
from . import service
from .providers import jev_codec
from ..weixin_inbox.runtime_records import stable


class SharedJudgeService:
    def __init__(self, database, runtime):
        self.database, self.runtime = database, runtime

    def available(self):
        try:
            return self.runtime.provider is not None and self.runtime.configuration().enabled
        except ServiceError:
            return False

    async def assist(self, actor, value, *, current=lambda: True):
        value = d.SharedJudgeInput.model_validate(value.model_dump(mode='python'))
        if not self.available():
            return None
        provider, config = self.runtime.provider, self.runtime.configuration()
        authorization = self.runtime._authorization_id
        identity = stable('shared-judge', actor.user_id, actor.session_id,
            service._digest(value.model_dump(mode='json')), service._digest(config.model_dump(mode='json')))
        request_type=d.ServiceJudgeRequest if value.purpose=='service_intake' else d.JudgeRequest
        request = request_type(local_request_id=identity, scope=value.expected_scope,
            purpose=value.purpose, text=value.text)

        def check(*_):
            if (provider is not self.runtime.provider or authorization != self.runtime._authorization_id
                    or not current()):
                return 'stale_scope'
            with self.database.session() as db:
                actual = service._current(actor, db)
                row = service._owned(actual, value.expected_scope.conversation_id, db)
                require_active(db)
                if row['archived_at'] or service._snapshot(row) != value.expected_scope:
                    return 'stale_scope'
            return None

        return await self._dispatch(actor,request,identity,check,config,provider)

    async def assess(self,actor,connection_id,batch_id,candidates,*,current=lambda: True):
        if not self.available():return None
        from ..weixin_inbox import service_records as journal,accounts
        provider,config=self.runtime.provider,self.runtime.configuration()
        authorization=self.runtime._authorization_id
        with self.database.session() as db:
            actor=service._current(actor,db);require_active(db)
            connection=db.execute(text('SELECT * FROM weixin_service_connections WHERE id=:id'),{'id':str(connection_id)}).mappings().one()
            accounts._account(actor,connection['account_id'],db,mode='weixin_personal')
            batch=db.execute(text('SELECT * FROM weixin_service_batches WHERE id=:id'),{'id':str(batch_id)}).mappings().one()
            if batch['connection_id']!=str(connection_id) or connection['owner_id']!=str(actor.user_id):
                raise ServiceError('CROSS_MATTER_DENIED',403)
            scope=d.ServiceJudgeScope(workspace_id=connection['workspace_id'],owner_id=actor.user_id,
                session_id=actor.session_id,connection_id=connection_id,batch_id=batch_id,revision=batch['revision'])
            sources=journal.events(batch_id,db)
            content='\n'.join(journal.payload(e).text+'\n'+', '.join(m.name for m in journal.payload(e).media) for e in sources)[:12000]
            options=[]
            for item in candidates[:12]:
                row=service._owned(actor,item['id'],db)
                if row['archived_at']:raise ServiceError('VERSION_CONFLICT',409)
                options.append(d.ServiceJudgeCandidate(conversation_id=item['id'],title=row['display_title'][:120]))
        identity=stable('service-judge',service._digest(scope.model_dump(mode='json')),
            service._digest({'text':content,'candidates':[c.model_dump(mode='json') for c in options]}),
            service._digest(config.model_dump(mode='json')))
        request=d.ServiceJudgeRequest(local_request_id=identity,scope=scope,text=content,candidates=tuple(options))
        def check(*_):
            if provider is not self.runtime.provider or authorization!=self.runtime._authorization_id or not current():
                return 'stale_scope'
            with self.database.session() as db:
                service._current(actor,db);require_active(db)
                accounts._account(actor,connection['account_id'],db,mode='weixin_personal')
                row=db.execute(text('SELECT revision,state FROM weixin_service_batches WHERE id=:id'),{'id':str(batch_id)}).mappings().one()
                if row['revision']!=scope.revision or row['state'] not in {'collecting','waiting','clarify'}:
                    return 'stale_scope'
                for option in options:
                    owned=service._owned(actor,option.conversation_id,db)
                    if owned['archived_at'] or owned['display_title'][:120]!=option.title:return 'stale_scope'
            return None
        return await self._dispatch(actor,request,identity,check,config,provider)

    async def _dispatch(self,actor,request,identity,check,config,provider):
        is_service=type(request.scope) is d.ServiceJudgeScope
        extended=type(request) is d.ServiceJudgeRequest
        result_type=d.ServiceJudgeResult if extended else d.JudgeResult
        digest=jev_codec.input_hash(request,config)
        if check():
            return None
        with self.database.session() as db:
            db.connection()  # Existing Database begin hook takes the write lease.
            old = db.execute(text('SELECT * FROM assistant_shared_judgments WHERE id=:id'), {'id':str(identity)}).mappings().first()
            if old:
                return result_type.model_validate_json(old['result_json']) if old['state']=='received' else None
            db.execute(text('''INSERT INTO assistant_shared_judgments
                (id,actor_id,session_id,conversation_id,batch_id,request_json,config_json,input_hash,state,created_at)
                VALUES (:id,:actor,:session,:cid,:batch,:request,:config,:hash,'unknown',:at)'''),
                {'id':str(identity),'actor':str(actor.user_id),'session':str(actor.session_id),
                 'cid':str(request.scope.conversation_id) if not is_service else None,'batch':str(request.scope.batch_id) if is_service else None,'request':canonical_json(request.model_dump(mode='json')),
                 'config':canonical_json(config.model_dump(mode='json')),'hash':digest,'at':service._at()})
        result = None
        try:
            result = await asyncio.wait_for(provider.judge(request, expected_config=config, preflight=check),
                timeout=config.timeout_ms/1000)
            result = result_type.model_validate(result.model_dump(mode='python'))
            if (result.local_request_id != identity or result.scope != request.scope
                    or result.input_hash != digest or check()):
                result = None
            if result and extended and result.status=='ok':
                questions=jev_codec.service_questions(request)
                if any(set(answer.probabilities)!=set(questions[key]['criteria']) for key,answer in result.answers.items()):
                    result=None
        except asyncio.CancelledError:
            raise
        except Exception:
            # Durable unknown claim survives interruption and never retransmits.
            return None
        with self.database.session() as db:
            db.execute(text('''UPDATE assistant_shared_judgments SET result_json=:result,state=:state
                WHERE id=:id AND state='unknown' '''),
                {'id':str(identity),'result':canonical_json(result.model_dump(mode='json')) if result else None,
                 'state':'received' if result else 'discarded'})
        return result


def validate_records(db):
    if not db.scalar(text("SELECT 1 FROM sqlite_master WHERE name='assistant_shared_judgments'")):
        return
    for row in db.execute(text('SELECT * FROM assistant_shared_judgments')).mappings():
        is_service=row['batch_id'] is not None
        extended=json.loads(row['request_json']).get('purpose')=='service_intake'
        request_type=d.ServiceJudgeRequest if extended else d.JudgeRequest
        result_type=d.ServiceJudgeResult if extended else d.JudgeResult
        request=request_type.model_validate_json(row['request_json'])
        config=d.JevConfig.model_validate_json(row['config_json'])
        if is_service:
            expected=stable('service-judge',service._digest(request.scope.model_dump(mode='json')),
                service._digest({'text':request.text,'candidates':[c.model_dump(mode='json') for c in request.candidates]}),
                service._digest(config.model_dump(mode='json')))
            batch=db.execute(text('SELECT * FROM weixin_service_batches WHERE id=:id'),{'id':row['batch_id']}).mappings().one()
            connection=db.execute(text('SELECT * FROM weixin_service_connections WHERE id=:id'),{'id':batch['connection_id']}).mappings().one()
            if (str(request.scope.batch_id)!=row['batch_id'] or str(request.scope.connection_id)!=connection['id']
                    or str(request.scope.owner_id)!=connection['owner_id'] or str(request.scope.workspace_id)!=connection['workspace_id']
                    or str(request.scope.session_id)!=row['session_id'] or request.scope.revision>batch['revision']):
                raise ValueError('SERVICE_JUDGE_INTEGRITY')
            from ..weixin_inbox.service_records import events,payload
            originals=events(row['batch_id'],db)[:request.scope.revision-1]
            content='\n'.join(payload(e).text+'\n'+', '.join(m.name for m in payload(e).media) for e in originals)[:12000]
            if request.text!=content or str(request.scope.owner_id)!=row['actor_id']:
                raise ValueError('SERVICE_JUDGE_SOURCE_INTEGRITY')
        else:
            value=d.SharedJudgeInput(expected_scope=request.scope,purpose=request.purpose,text=request.text)
            expected=stable('shared-judge',row['actor_id'],row['session_id'],
                service._digest(value.model_dump(mode='json')),service._digest(config.model_dump(mode='json')))
            if (str(request.scope.conversation_id)!=row['conversation_id']
                    or db.scalar(text('SELECT owner_id FROM assistant_conversations WHERE id=:id'),{'id':row['conversation_id']})!=row['actor_id']):
                raise ValueError('SHARED_JUDGE_INTEGRITY')
        if (str(expected)!=row['id'] or request.local_request_id!=expected
                or jev_codec.input_hash(request,config)!=row['input_hash']
                or db.scalar(text('SELECT user_id FROM sessions WHERE id=:id'),{'id':row['session_id']})!=row['actor_id']):
            raise ValueError('SHARED_JUDGE_INTEGRITY')
        if row['state']=='received':
            result=result_type.model_validate_json(row['result_json'])
            if result.local_request_id!=expected or result.scope!=request.scope or result.input_hash!=row['input_hash']:
                raise ValueError('SHARED_JUDGE_INTEGRITY')
            if extended and result.status=='ok':
                questions=jev_codec.service_questions(request)
                if any(set(answer.probabilities)!=set(questions[key]['criteria']) for key,answer in result.answers.items()):
                    raise ValueError('SERVICE_JUDGE_OPTIONS')
        elif row['result_json'] is not None:
            raise ValueError('SHARED_JUDGE_INTEGRITY')
