"""Native-chat facade. Identity and human messages come only from the host adapter.

The conversation model writes drafts; this module never calls a second model.
Existing validators, revisions, review and durable export jobs remain authoritative.
"""
import re
from uuid import uuid4, uuid5, NAMESPACE_URL

from . import domain as d
from .content import references, validate_script
from .reviews import collect_dependencies, package_validation, validate_review
from .store import digest


def fields(value, allowed):
    if not isinstance(value, dict) or set(value)-set(allowed): raise ValueError('UNKNOWN_FIELDS')


class MediaConversation:
    def __init__(self, service):
        self.service=service
        self.store=service.store

    def current(self, entity_id):
        return self.store.load(self.store.head(entity_id), current=True) if entity_id else None

    def state(self, session):
        # Deliberately query only this host session, never load all conversation bodies.
        with self.store.db() as db:
            row=db.execute('''SELECT e.id,e.revision,r.sha256 FROM media_entities e
                JOIN media_revisions r ON r.entity_id=e.id AND r.revision=e.revision
                WHERE e.kind='conversation' AND e.workspace_id=? AND e.owner_user_id=?
                AND json_extract(r.content,'$.session_id')=?''',
                (self.store.actor.workspace_id,self.store.actor.user_id,session)).fetchone()
            if row:
                return self.store._load(db,dict(kind='conversation',entity_id=row['id'],revision=row['revision'],content_sha256=row['sha256']))
        return {'ref':None,'value':d.MediaConversationSnapshot(session_id=session).model_dump(mode='json')}

    def persist(self, row, state):
        ref=row['ref']
        saved=self.store.save('conversation',state,expected_revision=ref['revision'] if ref else 0,
                              entity_id=ref['entity_id'] if ref else None)
        return self.store.load(saved)

    def content(self, state):
        if not state['project_id']: return {}
        with self.store.db() as db:
            rows=db.execute('''SELECT e.id,e.kind,e.revision,r.sha256 FROM media_entities e
                JOIN media_revisions r ON r.entity_id=e.id AND r.revision=e.revision
                WHERE e.kind IN ('brief','script','shooting_plan') AND e.workspace_id=? AND e.owner_user_id=?
                AND json_extract(r.content,'$.project_ref.entity_id')=?''',
                (self.store.actor.workspace_id,self.store.actor.user_id,state['project_id'])).fetchall()
            return {r['kind']:self.store._load(db,dict(kind=r['kind'],entity_id=r['id'],revision=r['revision'],content_sha256=r['sha256'])) for r in rows}

    def snapshot(self, row):
        state=row['value'];details={k:v for k,v in state['details'].items() if v is not None}
        questions=[]
        if not details.get('title'): questions.append('这次想聊哪个话题，或者想解决什么问题？')
        if not details.get('audience'): questions.append('这条内容主要想让谁看到？例如普通职工、企业负责人或同行律师。')
        content=self.content(state);issues={}
        for kind,item in content.items():
            try:
                collect_dependencies(self.store,[item['ref']])
                if kind=='script': issues[kind]=validate_script(self.store,item['value']).model_dump()
            except (ValueError,PermissionError) as error: issues[kind]={'blocking_errors':[str(error)]}
        review=self.current(state['review_id'])
        if review:
            try:
                project,refs=self.package(state)
                full,_=package_validation(self.store,d.MediaRevisionRef.model_validate(project['ref']),refs)
                validate_review(self.store,d.MediaRevisionRef.model_validate(review['ref']),full)
            except (ValueError,PermissionError) as error:
                issues['review']={'blocking_errors':[str(error)]};review=None
        assumptions={k:v for k,v in {'platform':'通用','target_duration_ms':60000,'regions':['未指定地区'],
            'primary_business':'本次话题','style':'自然、清楚','constraints':d.MediaShootConstraints().model_dump()}.items() if k not in details}
        memories=[]
        for identifier in state['memory_ids']:
            item=self.current(identifier)
            # Originals are not automatically fed back to the model or exported.
            item['value']={k:v for k,v in item['value'].items() if k!='original'}
            memories.append(item)
        return dict(revision=row['ref']['revision'] if row['ref'] else 0, details=details,questions=questions[:2],
            assumptions=assumptions,project=self.current(state['project_id']),content=content,validation=issues,
            sources=[self.current(i) for i in state['source_ids']], memories=memories,
            review=review,pending=state['pending'],job_ids=state['job_ids'])

    def project(self, state):
        project=self.current(state['project_id'])
        if not project: raise ValueError('请先补充话题和受众，再保存稿件。')
        if project['ref']['revision']!=state['project_revision']: raise ValueError('PROJECT_CHANGED_RESUME_REQUIRED')
        return project

    def package(self, state):
        project=self.project(state);content=self.content(state)
        if not {'brief','script','shooting_plan'}<=content.keys(): raise ValueError('INCOMPLETE_PACKAGE')
        refs=[content[k]['ref'] for k in ('brief','script','shooting_plan')]
        return project,refs

    def fingerprint(self, state, target, identifier=None):
        if target=='package':
            project,refs=self.package(state)
            full,errors=package_validation(self.store,d.MediaRevisionRef.model_validate(project['ref']),refs)
            if errors: raise ValueError('REVIEW_BLOCKED: '+','.join(errors))
            return digest([r.model_dump() for r in full])
        if target not in ('source','memory') or identifier not in state[target+'_ids']: raise PermissionError('OUTSIDE_CONVERSATION')
        return digest(self.current(identifier)['ref'])

    def update(self, state, payload):
        changes=d.MediaConversationDetails.model_validate(payload).model_dump(mode='json',exclude_unset=True)
        if any(v is None for v in changes.values()): raise ValueError('EMPTY_DETAIL')
        details={**state['details'],**changes};state['details']=details
        if not details.get('title') or not details.get('audience'): return
        existing=self.project(state) if state['project_id'] else None
        profile=self.current(state['profile_id'])
        profile_value=dict(regions=details.get('regions') or ['未指定地区'],primary_business=details.get('primary_business') or '本次话题',
            audience=details['audience'],style=details.get('style') or '自然、清楚',secondary_business=profile['value']['secondary_business'] if profile else [])
        if profile and profile['value']==profile_value: profile_ref=profile['ref']
        else:
            # A resumed project's profile can be shared with older projects. Preserve it.
            profile_ref=self.store.save('profile',profile_value,expected_revision=0).model_dump()
        project_value=d.MediaProjectInput.model_validate(dict(profile_ref=profile_ref,title=details['title'],audience=details['audience'],
            **{k:details[k] for k in ('platform','target_duration_ms','constraints') if details.get(k) is not None})).model_dump(mode='json')
        if existing and existing['value']==project_value: project_ref=existing['ref']
        else:
            project_ref=self.store.save('project',project_value,expected_revision=existing['ref']['revision'] if existing else 0,
                entity_id=existing['ref']['entity_id'] if existing else None).model_dump()
        state.update(profile_id=profile_ref['entity_id'],project_id=project_ref['entity_id'],project_revision=project_ref['revision'])

    def save(self, state, payload):
        fields(payload,['kind','value','expected_content_revision'])
        kind=payload.get('kind');value=payload.get('value')
        if not isinstance(value,dict): raise ValueError('VALUE_REQUIRED')
        value=dict(value)
        if kind=='source':
            ref=self.service.dispatch('import_source',value)
            state['source_ids'].append(ref['entity_id']);return
        project=self.project(state)
        if kind=='memory':
            fields(value,['category','original','summary'])
            ref=self.service.dispatch('add_memory',dict(profile_ref=project['value']['profile_ref'],**value))
            state['memory_ids'].append(ref['entity_id']);return
        if kind=='feedback':
            fields(value,['status','note'])
            self.service.dispatch('save_feedback',dict(value=dict(project_ref=project['ref'],**value),expected_revision=0));return
        if kind not in ('brief','script','shooting_plan'): raise ValueError('UNKNOWN_STAGE')
        if any(k in value for k in ('project_ref','profile_ref','brief_ref','script_ref','constraints')): raise ValueError('HOST_BOUND_FIELDS')
        content=self.content(state);old=content.get(kind)
        expected=payload.get('expected_content_revision',0)
        if type(expected) is not int or expected!=(old['ref']['revision'] if old else 0): raise ValueError('VERSION_CONFLICT')
        allowed={*state['source_ids'],*state['memory_ids']}
        for ref in references(value):
            if kind=='brief' and old and ref.model_dump()==old['value'].get('event_ref'):
                continue  # Preserve the selected legacy brief's event, not an arbitrary event.
            if ref.entity_id not in allowed or ref.kind not in ('source','memory'): raise PermissionError('OUTSIDE_CONVERSATION')
        value['project_ref']=project['ref']
        if kind=='brief':
            value['profile_ref']=project['value']['profile_ref']
            for claim in value.get('claims',[]): claim.setdefault('id',str(uuid4()))
        elif kind=='script':
            if 'brief' not in content: raise ValueError('BRIEF_REQUIRED')
            value['brief_ref']=content['brief']['ref']
            for segment in value.get('segments',[]):segment.setdefault('id',str(uuid4()))
        else:
            if 'script' not in content: raise ValueError('SCRIPT_REQUIRED')
            value.update(script_ref=content['script']['ref'],constraints=project['value']['constraints'])
            for shot in value.get('shots',[]):shot.setdefault('id',str(uuid4()))
        self.service.dispatch('save_content',dict(kind=kind,value=value,expected_revision=expected,
            **({'entity_id':old['ref']['entity_id']} if old else {})))

    def resume(self, state, payload):
        fields(payload,['project_id'])
        project=self.current(payload.get('project_id'))
        if not project or project['ref']['kind']!='project': raise ValueError('PROJECT_REQUIRED')
        profile=self.store.load(project['value']['profile_ref'])
        state.update(project_id=project['ref']['entity_id'],project_revision=project['ref']['revision'],
            profile_id=profile['ref']['entity_id'],review_id=None,pending=None,source_ids=[],memory_ids=[],job_ids=[])
        state['details']={**{k:project['value'][k] for k in ('title','audience','platform','target_duration_ms','constraints')},
            **{k:profile['value'][k] for k in ('regions','primary_business','style')}}
        # Only dependencies already used in this chosen project are reattached.
        for item in self.content(state).values():
            for ref in references(item['value']):
                if ref.kind in ('source','memory') and ref.entity_id not in state[ref.kind+'_ids']:
                    state[ref.kind+'_ids'].append(ref.entity_id)

    def dispatch(self, args):
        fields(args,['session_id','user_message','op','payload','expected_revision'])
        session=args.get('session_id');d.MediaConversationSnapshot(session_id=session)
        message=args.get('user_message',{});fields(message,['seq','text'])
        if type(message.get('seq')) is not int or message['seq']<0 or not isinstance(message.get('text'),str): raise ValueError('HOST_USER_MESSAGE_REQUIRED')
        op=args.get('op');payload=args.get('payload',{});row=self.state(session);state=row['value']
        if op=='read':
            fields(payload,[]);return self.snapshot(row)
        if op=='schema':
            fields(payload,['kind']);kind=payload.get('kind')
            if kind not in ('details','source','memory','brief','script','shooting_plan','feedback'): raise ValueError('UNKNOWN_STAGE')
            model=d.MediaConversationDetails if kind=='details' else d.MediaSourceImport if kind=='source' else d.INPUT_MODELS[kind]
            schema=model.model_json_schema()
            # Describe the native facade, not internal storage DTO fields which
            # the host binds. Conflicting schemas caused real models to retry.
            omitted=[] if kind=='details' else ['project_ref','profile_ref','brief_ref','script_ref','constraints','confirmation']
            for name in omitted:
                schema['properties'].pop(name,None)
                if name in schema.get('required',[]): schema['required'].remove(name)
            for name in ('MediaClaim','MediaScriptSegment','MediaShotInstruction'):
                item=schema.get('$defs',{}).get(name)
                if item:
                    item['required']=[key for key in item.get('required',[]) if key!='id']
                    item['properties']['id']['description']='新条目可省略，由后台生成；修改已有条目时保留原 id。'
            if kind=='brief':
                schema['properties']['pending']['description']='仅列缺失或矛盾的事实依据；没有事实缺项时用空数组。未审阅、未拍摄、时长待实测是制作事项，不是待核事实；不能清空真正的事实疑点。'
            if kind=='shooting_plan' and state['project_id']:
                equipment=self.current(state['project_id'])['value']['constraints']['equipment']
                requirement=schema['$defs']['MediaShotInstruction']['properties']['equipment_required']
                if equipment:requirement['items']={'type':'string','enum':equipment}
                else:requirement['maxItems']=0
                requirement['description']='使用项目已经提供的器材名称原值，不翻译或另造名称。'
            return {'schema':schema,'omit_host_fields':omitted,'prerequisites':{'script':['brief'],'shooting_plan':['script']}.get(kind,[]),
                    'note':'details 写入 update.data，其他阶段写入 save.value；不向用户展示 JSON、编号或表单。必要的前置提纲由 AI 整理保存，不让用户补填技术字段。'}
        if op=='catalog':
            fields(payload,['offset']);offset=payload.get('offset',0)
            if type(offset) is not int or offset<0: raise ValueError('INVALID_OFFSET')
            with self.store.db() as db:
                rows=db.execute('''SELECT e.id,json_extract(r.content,'$.title') AS title FROM media_entities e
                    JOIN media_revisions r ON r.entity_id=e.id AND r.revision=e.revision
                    WHERE e.kind='project' AND e.workspace_id=? AND e.owner_user_id=? ORDER BY e.created_at DESC LIMIT 20 OFFSET ?''',
                    (self.store.actor.workspace_id,self.store.actor.user_id,offset)).fetchall()
                return {'projects':[dict(r) for r in rows],'next_offset':offset+20 if len(rows)==20 else None}
        if op in ('job','cancel'):
            fields(payload,['id'])
            if payload.get('id') not in state['job_ids']: raise PermissionError('OUTSIDE_CONVERSATION')
            job=self.service.dispatch(op,payload)
            result={'job':{k:job[k] for k in ('id','kind','state','error','created_at','updated_at') if k in job}}
            output=job.get('output') or {}
            if job['state']=='succeeded' and output.get('id'):
                self.service.dispatch('download',{'id':output['id']})
                result['download_url']='/api/qx-media/download?id='+output['id']
                if job['kind']=='export' and job['input']['mode']=='draft' and not state['pending'] and not self.store.readonly:
                    # Delivery freezes what can be reviewed next. This is not an
                    # approval: a later, explicit human confirmation is still required.
                    try: fingerprint=self.fingerprint(state,'package')
                    except (ValueError,PermissionError): fingerprint=None
                    if fingerprint:
                        state['pending']=dict(target='package',entity_id=None,fingerprint=fingerprint,user_seq=message['seq'])
                        row=self.persist(row,state)
                        result['review_notice']='当前草稿版本已准备待核；尚未确认。请展示内容，后续用户明确回复“确认当前版本”后才可确认。'
            result['revision']=row['ref']['revision'] if row['ref'] else 0
            return result
        revision=row['ref']['revision'] if row['ref'] else 0
        if type(args.get('expected_revision')) is not int or args['expected_revision']!=revision: raise ValueError('VERSION_CONFLICT')
        if op=='update':
            before=digest(state)
            self.update(state,payload)
            if digest(state)==before: return self.snapshot(row)
        elif op=='save': self.save(state,payload)
        elif op=='resume': self.resume(state,payload)
        elif op=='new':
            fields(payload,[]);state=d.MediaConversationSnapshot(session_id=session).model_dump(mode='json')
        elif op=='prepare':
            fields(payload,['target','id']);target=payload.get('target');identifier=payload.get('id')
            state['pending']=dict(target=target,entity_id=identifier,fingerprint=self.fingerprint(state,target,identifier),user_seq=message['seq'])
        elif op=='confirm':
            fields(payload,['target','id']);pending=state['pending']
            if not pending: raise ValueError('NO_PENDING_CONFIRMATION')
            if ('target' in payload and payload['target']!=pending['target']) or ('id' in payload and payload['id']!=pending['entity_id']):
                raise PermissionError('CONFIRMATION_TARGET_MISMATCH')
            reply=re.sub(r'[\s，。！!,.]+','',message['text'])
            permitted=('确认','确认当前版本','确认以上内容') if pending['target']=='package' else ('确认','确认当前版本','确认以上内容','确认使用','可以','同意','是的')
            if message['seq']<=pending['user_seq'] or reply not in permitted:
                raise PermissionError('LATER_USER_CONFIRMATION_REQUIRED')
            if self.fingerprint(state,pending['target'],pending['entity_id'])!=pending['fingerprint']: raise ValueError('STALE_CONFIRMATION')
            if pending['target']=='package':
                project,refs=self.package(state)
                state['review_id']=self.service.dispatch('approve',dict(project_ref=project['ref'],refs=refs))['entity_id']
            else:
                self.service.dispatch('confirm_'+pending['target'],{'ref':self.current(pending['entity_id'])['ref']})
            state['pending']=None
        elif op=='export':
            fields(payload,['mode','retry']);mode=payload.get('mode','draft')
            if type(payload.get('retry',False)) is not bool: raise ValueError('INVALID_RETRY')
            project,refs=self.package(state)
            review=self.current(state['review_id']) if mode=='approved' else None
            if mode=='approved' and not review: raise ValueError('REVIEW_REQUIRED')
            request=dict(kind='export',project_ref=project['ref'],expected_refs=refs,mode=mode,
                review_ref=review['ref'] if review else None)
            request['request_id']=str(uuid5(NAMESPACE_URL,session+digest(request)))
            if payload.get('retry'):
                # Export is local. Explicitly retry a terminal failure/cancellation,
                # but reuse any queued/running/successful successor after a lost reply.
                for _ in range(100):
                    previous=self.service.jobs.by_request(request['request_id'])
                    if not previous or previous['state'] not in ('failed','cancelled'): break
                    request['request_id']=str(uuid5(NAMESPACE_URL,previous['id']+':export-retry'))
                else: raise ValueError('RETRY_LIMIT')
            job=self.service.dispatch('submit',request)
            if job['id'] not in state['job_ids']:state['job_ids']=(state['job_ids']+[job['id']])[-100:]
            saved=self.persist(row,state)
            return {'revision':saved['ref']['revision'],'job':{k:job[k] for k in ('id','kind','state','error','created_at','updated_at') if k in job}}
        else: raise ValueError('UNKNOWN_CONVERSATION_ACTION')
        if op in ('update','save','resume','new'):
            state['pending']=None
            if op!='save' or payload.get('kind') in ('brief','script','shooting_plan'):
                state['review_id']=None
        return self.snapshot(self.persist(row,state))
