"""Eight bounded files, atomic registration and authorization on every download."""
import csv
import hashlib
from io import BytesIO,StringIO
import json
import mimetypes
import os
from pathlib import Path
from uuid import uuid4,UUID
from zipfile import ZipFile,ZIP_DEFLATED

from word_render import document_from_text
from . import domain as d
from .reviews import package_validation,validate_review
from .store import encoded,safe

LIMIT=10*1024*1024


def csv_cell(value):
    value=str(value)
    return "'"+value if value.lstrip().startswith(('=','+','-','@')) or value.startswith(('\t','\r','\n')) else value


def render_files(store,full,mode):
    values={ref.kind:store.load(ref)['value'] for ref in full if ref.kind in ('project','brief','script','shooting_plan')}
    script=values['script']; plan=values['shooting_plan']; brief=values['brief']
    label='草稿 · 未经最终审阅' if mode=='draft' else '已审阅拍摄稿'
    speech='\n\n'.join(segment['text'] for segment in script['segments'])
    text=f'{label}\n\n## 标题候选\n'+'\n'.join(script['titles'])+'\n\n## 口播稿\n'+speech+'\n\n## 发布说明\n'+script['caption']+'\n\n## 封面文字\n'+script['cover_text']
    word=BytesIO(); document_from_text(values['project']['title'],text).save(word)
    csvout=StringIO(newline=''); writer=csv.writer(csvout)
    columns=['序号','对应台词','景别','机位','建议秒数','动作','运镜','光线','收音','设备','简单替代']
    writer.writerow(columns); segments={s['id']:s['text'] for s in script['segments']}
    for i,shot in enumerate(plan['shots'],1):
        writer.writerow([csv_cell(v) for v in [i,' / '.join(segments[k] for k in shot['script_segment_ids']),shot['shot_size'],
            shot['camera_position'],shot['estimated_duration_ms']/1000,shot['subject_action'],shot['movement_intent'],
            shot['lighting_note'],shot['audio_note'],'、'.join(shot['equipment_required']),shot['simple_alternative']]])
    sources=[]
    for claim in brief['claims']:
        source=store.load(claim['source_ref'])['value']
        sources.append({'source_ref':claim['source_ref'],'title':source['title'],'url':source['url'],
            'quote':claim['evidence_quote'],'published_at':source['published_at'],'event_at':source['event_at'],
            'fetched_at':source['fetched_at'],'content_origin':source['content_origin'],'content_scope':source['content_scope'],
            'verification':source['verification'],'law_name':claim['law_name'],'law_status':claim['law_status'],
            'applicability':claim['applicability'],'effective_at':claim['effective_at']})
    return {'brief.md':(label+'\n\n受众：'+brief['audience']+'\n角度：'+brief['angle']+'\n待核：'+'；'.join(brief['pending'])).encode(),
        'script.docx':word.getvalue(),'script.md':text.encode(),
        'teleprompter.txt':(label+'\n\n'+speech).encode(),
        'shot_list.csv':csvout.getvalue().encode('utf-8-sig'),
        'shooting_checklist.md':(label+'\n\n'+'\n'.join('- '+item for item in plan['shooting_checklist'])+'\n\n时长为估计；拍摄前试读并试听收音。').encode(),
        'sources.json':encoded(sources).encode()}


def prepare_export(store,project_ref,refs,*,mode='draft',review_ref=None):
    if store.readonly: raise PermissionError('RESTORED_READ_ONLY')
    if mode not in ('draft','approved'): raise ValueError('INVALID_MODE')
    full,errors=package_validation(store,project_ref,refs)
    if mode=='approved':
        if review_ref is None or errors: raise ValueError('REVIEW_REQUIRED')
        validate_review(store,review_ref,full)
    files=render_files(store,full,mode)  # Rendering is outside all database transactions.
    if sum(map(len,files.values()))>LIMIT: raise ValueError('EXPORT_TOO_LARGE')
    identifier=str(uuid4()); now=d.utc_stamp()
    provenance=[]
    from .jobs import MediaJobs
    jobs=MediaJobs(store).list()
    for ref in full:
        if ref.kind not in ('brief','script','shooting_plan'): continue
        job=next((j for j in jobs if j['state']=='succeeded' and j['output'] and j['output'].get('ref')==ref.model_dump()),None)
        provenance.append({'ref':ref.model_dump(),'origin':'model' if job else 'manual',
            'job_id':job['id'] if job else None,'receipts':job['receipt'] if job else None})
    manifest={'id':identifier,'mode':mode,'review_ref':review_ref.model_dump() if review_ref else None,
        'schema_version':1,'provenance':provenance,'content_refs':[r.model_dump() for r in full],'created_at':now,'validation_errors':errors,
        'files':[{'relative_name':name,'sha256':hashlib.sha256(data).hexdigest(),'size':len(data),
                  'mime':mimetypes.guess_type(name)[0] or 'application/octet-stream'} for name,data in files.items()]}
    files['manifest.json']=encoded(manifest).encode()
    blob=BytesIO()
    with ZipFile(blob,'w',ZIP_DEFLATED) as archive:
        for name,data in files.items(): archive.writestr(name,data)
    data=blob.getvalue()
    if len(data)>LIMIT: raise ValueError('EXPORT_TOO_LARGE')
    directory=safe(store.root,store.internal/'exports'); directory.mkdir(exist_ok=True)
    target=safe(store.root,directory/(identifier+'.zip')); temp=target.with_suffix('.tmp')
    safe(store.root,temp)
    with temp.open('xb') as stream: stream.write(data)
    return dict(id=identifier,mode=mode,full=full,review_ref=review_ref,manifest=manifest,target=target,temp=temp,
                sha256=hashlib.sha256(data).hexdigest(),created_at=now,bytes=len(data))


def publish_export(store,db,prepared):
    p=prepared
    for ref in p['full']: store._load(db,ref,current=True)
    if p['review_ref']: store._load(db,p['review_ref'],current=True)
    os.rename(p['temp'],p['target'])
    db.execute('INSERT INTO media_exports VALUES(?,?,?,?,?,?,?,?,?,?)',
        (p['id'],store.actor.workspace_id,store.actor.user_id,p['mode'],encoded([r.model_dump() for r in p['full']]),
         encoded(p['review_ref'].model_dump()) if p['review_ref'] else None,encoded(p['manifest']),p['target'].name,
         p['sha256'],p['created_at']))
    return {'id':p['id'],'mode':p['mode'],'bytes':p['bytes'],'filename':'拍摄内容包-'+p['id'][:8]+'.zip'}


def cleanup_export(store,prepared):
    if prepared['temp'].exists(): safe(store.root,prepared['temp']).unlink()
    with store.db() as db:
        registered=db.execute('SELECT 1 FROM media_exports WHERE id=?',(prepared['id'],)).fetchone()
    if not registered and prepared['target'].exists(): safe(store.root,prepared['target']).unlink()


def build_export(store,project_ref,refs,*,mode='draft',review_ref=None):
    prepared=prepare_export(store,project_ref,refs,mode=mode,review_ref=review_ref)
    try:
        with store.db(write=True) as db: result=publish_export(store,db,prepared)
        return result
    finally: cleanup_export(store,prepared)



def download(store,identifier):
    if str(UUID(identifier))!=identifier: raise ValueError('INVALID_ID')
    if store.readonly: raise PermissionError('RESTORED_READ_ONLY')
    with store.db() as db:
        row=db.execute('SELECT * FROM media_exports WHERE id=?',(identifier,)).fetchone()
        if row is None: raise ValueError('NOT_FOUND')
        if row['workspace_id']!=store.actor.workspace_id or row['owner_user_id']!=store.actor.user_id: raise PermissionError('ACCESS_DENIED')
        refs=[d.MediaRevisionRef.model_validate(ref) for ref in json.loads(row['refs'])]
        for ref in refs: store._load(db,ref,current=True)
        if row['review_ref']: store._load(db,json.loads(row['review_ref']),current=True)
        target=safe(store.root,store.internal/'exports'/row['relative_name'])
        if target.stat().st_size>LIMIT or hashlib.sha256(target.read_bytes()).hexdigest()!=row['sha256']: raise ValueError('EXPORT_INTEGRITY')
        return target
