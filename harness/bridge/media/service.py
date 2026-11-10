"""Host-owned operations; no client-supplied actor or filesystem destination."""
import asyncio
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import subprocess
from uuid import uuid4
from urllib.parse import urlsplit

from . import domain as d
from .store import MediaStore,safe
from .jobs import MediaJobs,KnownFailure
from .sources import MediaSources,safe_url
from .retrieval import search_values,fetch_value
from .profiles import add_memory,confirm_memory,revoke_memory
from .content import save_content,validate_script,validate_brief,references
from .shooting import save_plan,validate_shooting_plan
from .reviews import approve_package,collect_dependencies
from .exports import prepare_export,publish_export,cleanup_export,download
from .regions import recommend,save_event,confirm_region
from .deepseek import generate,official_request

ROOT=Path(__file__).resolve().parents[2]


def keys(args,allowed):
    if not isinstance(args,dict) or set(args)-set(allowed): raise ValueError('UNKNOWN_FIELDS')


class MediaService:
    def __init__(self,workspace,*,scraper_python=None):
        root=Path(workspace).absolute();safe(root,root);root.mkdir(parents=True,exist_ok=True)
        internal=safe(root,root/'.qx-media');internal.mkdir(exist_ok=True)
        identity=safe(root,internal/'host-identity.json')
        if not identity.exists():
            if (internal/'RESTORED_READ_ONLY').exists() or (internal/'media.sqlite').exists():
                raise ValueError('MISSING_HOST_IDENTITY')
            try:
                with identity.open('x',encoding='utf-8') as file:
                    json.dump({'workspace_id':str(uuid4()),'user_id':str(uuid4())},file)
            except FileExistsError: pass
        self.store=MediaStore(root,d.MediaActorContext.model_validate(json.loads(identity.read_text(encoding='utf-8'))))
        self.jobs=MediaJobs(self.store);self.sources=MediaSources(self.store)
        self.scraper_python=scraper_python
        self.worker_id=str(uuid4())
        self.registry={item['id']:item for item in json.loads((ROOT/'sources/media-source-registry.json').read_text(encoding='utf-8'))['sources']}

    def dispatch(self,action,args):
        if action=='_conversation':
            from .conversation import MediaConversation
            return MediaConversation(self).dispatch(args)
        if action=='_credential':
            keys(args,['value'])
            if type(args.get('value')) is not str or len(args['value'])>4096: raise ValueError('INVALID_CREDENTIAL')
            os.environ['DEEPSEEK_API_KEY']=args['value']
            return {'configured':bool(args['value'])}
        if action=='status':
            keys(args,[])
            return {'model_configured':bool(os.environ.get('DEEPSEEK_API_KEY')),'sources':list(self.registry.values()),
                    'source_health':[self.sources.health(key) for key in self.registry if self.sources.health(key)],
                    'jobs':self.jobs.list(),'readonly':self.store.readonly}
        if action=='list':
            keys(args,['kind'])
            if args['kind'] not in d.INPUT_MODELS: raise ValueError('UNKNOWN_KIND')
            return self.store.list(args['kind'])
        if action in ('save_profile','save_project'):
            keys(args,['value','expected_revision','entity_id'])
            return self.store.save(action.removeprefix('save_'),**args).model_dump()
        if action=='save_feedback':
            keys(args,['value','expected_revision','entity_id'])
            value=d.MediaFeedbackInput.model_validate(args['value'])
            if value.project_ref.kind!='project': raise ValueError('REFERENCE_MISMATCH')
            self.store.load(value.project_ref,current=True)
            return self.store.save('feedback',**args).model_dump()
        if action=='add_memory':
            keys(args,['profile_ref','category','original','summary'])
            return add_memory(self.store,d.MediaRevisionRef.model_validate(args['profile_ref']),args['category'],args['original'],summary=args.get('summary')).model_dump()
        if action in ('confirm_memory','revoke_memory'):
            keys(args,['ref']);ref=d.MediaRevisionRef.model_validate(args['ref'])
            return (confirm_memory if action=='confirm_memory' else revoke_memory)(self.store,ref).model_dump()
        if action=='import_source': return self.sources.import_source(args).model_dump()
        if action=='confirm_source':
            keys(args,['ref']);return self.sources.confirm(d.MediaRevisionRef.model_validate(args['ref'])).model_dump()
        if action=='save_event':
            keys(args,['value','expected_revision','entity_id','confirm_regions'])
            args=dict(args);confirmed=args.pop('confirm_regions',False)
            if type(confirmed) is not bool: raise ValueError('INVALID_CONFIRMATION')
            value=dict(args['value']);regions=[]
            for region in value.get('regions',[]):
                if confirmed:
                    regions.append(confirm_region(self.store,d.MediaRevisionRef.model_validate(region['source_ref']),
                        region['region_key'],region['relation'],region['evidence_quote'],manual_confirmation=True))
                else:
                    if region.get('status')=='confirmed': raise ValueError('REGION_CONFIRMATION_REQUIRED')
                    regions.append(region)
            args['value']={**value,'regions':regions}
            return save_event(self.store,**args).model_dump()
        if action=='save_content':
            keys(args,['kind','value','expected_revision','entity_id']);kind=args['kind']
            if kind=='shooting_plan':
                return save_plan(self.store,args['value'],expected_revision=args['expected_revision'],entity_id=args.get('entity_id')).model_dump()
            return save_content(self.store,**args).model_dump()
        if action=='approve':
            keys(args,['project_ref','refs'])
            return approve_package(self.store,d.MediaRevisionRef.model_validate(args['project_ref']),args['refs']).model_dump()
        if action=='submit':
            request=d.JOB_INPUT.validate_python(args).model_dump(mode='json')
            if request['kind'] in ('brief','script','shooting_plan','interview','source_search','source_fetch') and not (request['model_authorized'] and os.environ.get('DEEPSEEK_API_KEY')):
                raise PermissionError('MODEL_NOT_AUTHORIZED')
            if request['kind']=='source_refresh' and any(identifier not in self.registry for identifier in request['source_ids']):
                raise ValueError('UNKNOWN_SOURCE_CONFIG')
            return self.jobs.submit(request)
        if action in ('job','cancel'):
            keys(args,['id']);return (self.jobs.get if action=='job' else self.jobs.cancel)(args['id'])
        if action=='job_by_request':
            keys(args,['request_id']);return self.jobs.by_request(args['request_id'])
        if action=='download':
            keys(args,['id']);return {'path':str(download(self.store,args['id']))}
        if action=='recommendations':
            keys(args,['profile_ref'])
            profile=self.store.load(args['profile_ref'],current=True)['value'];rows=[]
            for item in self.store.list('event'):
                value=item['value'];verified=True
                for ref in value['source_refs']:
                    try: verified &= self.store.load(ref,current=True)['value']['verification']=='verified'
                    except (ValueError,PermissionError): verified=False
                result=recommend({**value,'regions':value['regions'] if verified else [],'verified':verified,'heat':None},profile,datetime.now(timezone.utc))
                rows.append({**item,**result})
            return sorted(rows,key=lambda item:(-item['total_score'],item['ref']['entity_id']))
        raise ValueError('UNKNOWN_ACTION')

    def context(self,request):
        if request['kind']=='interview':
            return {'profile':self.store.load(request['profile_ref'],current=True)['value']}
        project=self.store.load(request['project_ref'],current=True)['value']
        values=[]
        for frozen in collect_dependencies(self.store,request['input_refs']):
            ref=frozen.model_dump()
            row=self.store.load(ref,current=True)
            if ref['kind']=='memory':
                if row['value']['confirmation']!='confirmed': raise ValueError('MEMORY_NOT_PUBLIC')
                row={**row,'value':{k:v for k,v in row['value'].items() if k!='original'}}
            values.append(row)
        return {'project_ref':request['project_ref'],'project':project,
                'profile':self.store.load(project['profile_ref'],current=True)['value'],'selected_inputs':values}

    def fetch(self,config):
        if not self.scraper_python: raise ValueError('SCRAPLING_NOT_CONFIGURED')
        result=subprocess.run([self.scraper_python,'-X','utf8',str(Path(__file__).with_name('fetch_worker.py'))],
            input=json.dumps(config),text=True,encoding='utf-8',stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=30,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0,
            env={k:v for k,v in os.environ.items() if not any(secret in k.upper() for secret in ('KEY','TOKEN','SECRET'))})
        response=json.loads(result.stdout)
        if result.returncode or not response.get('ok'): raise ValueError(response.get('error','FETCH_FAILED'))
        return response['result']

    def execute(self,claim):
        request=claim['input'];kind=request['kind']
        if kind in ('source_search','source_fetch'):
            if not request['model_authorized'] or not os.environ.get('DEEPSEEK_API_KEY'): raise PermissionError('MODEL_NOT_AUTHORIZED')
            if kind=='source_search':
                if not request['query'].strip(): raise ValueError('EMPTY_QUERY')
                priors=self.store.list('source');payload={'query':request['query'],'count':request['count'],'need_content':False}
            else:
                source=self.store.load(request['source_ref'],current=True)
                url=source['value']['url']
                if not url: raise ValueError('SOURCE_URL_REQUIRED')
                safe_url(url,{urlsplit(url).hostname})
                payload={'url':url}
            self.jobs.mark_sent(claim)
            response=official_request('search' if kind=='source_search' else 'fetch',payload,os.environ['DEEPSEEK_API_KEY'])
            self.jobs.record_receipt(claim,{'tool':kind,'http_response_received':True,'request_count':1})
            return (search_values(response,priors,request['count']) if kind=='source_search' else fetch_value(response,source)),None
        if kind=='source_refresh':
            results=[self.sources.prepare_refresh(self.registry[identifier],self.fetch) for identifier in request['source_ids']]
            return results,None
        if kind=='export':
            result=prepare_export(self.store,d.MediaRevisionRef.model_validate(request['project_ref']),request['expected_refs'],
                mode=request['mode'],review_ref=d.MediaRevisionRef.model_validate(request['review_ref']) if request.get('review_ref') else None)
            return result,None
        context=self.context(request)
        validator=d.MediaInterviewQuestions if kind=='interview' else d.INPUT_MODELS[kind]
        def authorized():
            self.context(request)
            return request['model_authorized'] and bool(os.environ.get('DEEPSEEK_API_KEY')) and self.jobs.get(claim['id'])['state']=='running'
        def send(payload):
            self.jobs.mark_sent(claim)
            return official_request('content',payload,os.environ['DEEPSEEK_API_KEY'])
        result=generate(kind,context,validator,authorize=authorized,send=send,
            record=lambda receipt:self.jobs.record_receipt(claim,receipt),max_tokens=request['max_tokens'])
        output=result['output']
        try:
            if kind!='interview':
                allowed=collect_dependencies(self.store,[request['project_ref'],*request['input_refs']])
                if any(ref not in allowed for ref in references(output)): raise KnownFailure('UNSELECTED_REFERENCE')
                if output['project_ref']!=request['project_ref']: raise KnownFailure('PROJECT_MISMATCH')
                if kind=='brief': validate_brief(self.store,output)
                if kind=='script':
                    if validate_script(self.store,output).blocking_errors: raise KnownFailure('INVALID_SCRIPT')
                if kind=='shooting_plan':
                    if validate_shooting_plan(self.store,output).blocking_errors: raise KnownFailure('INVALID_SHOOTING_PLAN')
        except (ValueError,PermissionError): raise KnownFailure('INVALID_GENERATED_CONTENT') from None
        return output,None

    async def run_next(self):
        claim=self.jobs.claim(self.worker_id)
        if claim is None: return False
        output=None
        try:
            output,receipt=await asyncio.to_thread(self.execute,claim)
            publish=None
            if claim['kind']=='source_refresh':
                def publish(db,value): return {'sources':[self.sources.publish_refresh(db,p) for p in value]}
            elif claim['kind'] in ('source_search','source_fetch'):
                def publish(db,value): return {'source_refs':[self.sources._save(p['value'],transaction=db,prior=p['prior']).model_dump() for p in value]}
            elif claim['kind']=='export':
                def publish(db,value): return publish_export(self.store,db,value)
            elif claim['kind'] in ('brief','script','shooting_plan'):
                def publish(db,value):
                    ref=self.store.save(claim['kind'],value,entity_id=(claim['input'].get('output_ref') or {}).get('entity_id'),expected_revision=claim['input']['expected_output_revision'],transaction=db)
                    return {'ref':ref.model_dump(),'value':value}
            self.jobs.finish(claim,output,receipt=receipt,publish=publish)
        except (Exception,asyncio.CancelledError) as error:
            current=self.jobs.get(claim['id'])
            self.jobs.finish(claim,error=type(error).__name__+': '+str(error)[:100],
                unknown=bool(current['sent']) and not isinstance(error,KnownFailure))
            if isinstance(error,asyncio.CancelledError): raise
        finally:
            if claim['kind']=='export' and output is not None: cleanup_export(self.store,output)
        return True
