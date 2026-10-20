"""Windows source-app TCP roundtrip using only independently synthetic DOCX."""
from contextlib import contextmanager
from hashlib import sha256
from http.cookiejar import CookieJar
import json
from pathlib import Path
import platform
import socket
import sys
import threading
import time
import traceback
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, ProxyHandler, Request, build_opener
from uuid import UUID, uuid4

import uvicorn
from cn_contract.config import canonical_json
from cn_contract.documents.ingest import DOCX_MIME
from cn_contract.ops import backup, workspace_backup
from cn_contract.ops.file_paths import filesystem_path
from cn_contract.persistence import read_version
from cn_contract.security import authenticate
from cn_contract.web import local_server
from cn_contract.assistant.providers.main import DeepSeekProvider
from cn_contract.assistant.providers.jev import JevProvider

BASE = Path(__file__).resolve().parent
WORKSPACE = BASE.parent.parent
sys.path.insert(0, str(WORKSPACE))
from tests.integration.test_contract_long_path_backup import long_directory
from tests.integration.test_local_materials import independent_docx
from tests.integration.test_local_workbench import PASSWORD
from tests.integration.test_workspace_backup import PASSPHRASE

DATA = Path('D:/qx-lpt-'+uuid4().hex[:10])
report = {'platform':platform.platform(), 'kind':'real Windows loopback HTTP, Python source app',
    'data_root':str(DATA), 'requests':[], 'servers':[], 'checks':[], 'connects':[]}
calls = {'model_generate':0, 'jev_judge':0}
original_generate, original_judge = DeepSeekProvider.generate, JevProvider.judge
INPUTS = ('src/cn_contract/persistence.py', 'src/cn_contract/ops/file_paths.py',
    'src/cn_contract/ops/backup.py', 'src/cn_contract/ops/workspace_backup.py',
    'src/cn_contract/web/local_server.py', 'src/cn_contract/web/recovery.py',
    'src/cn_contract/web/services.py', 'src/cn_contract/documents/ingest.py',
    'tests/integration/test_contract_long_path_backup.py')


def input_hashes():
    return {name:sha256((WORKSPACE/name).read_bytes()).hexdigest() for name in INPUTS}


async def no_model(*args, **kwargs):
    calls['model_generate']+=1
    raise AssertionError('unexpected model generation')


async def no_jev(*args, **kwargs):
    calls['jev_judge']+=1
    raise AssertionError('unexpected Jev judgment')


def audit(event,args):
    if event=='socket.connect':
        destination=args[1]
        if not isinstance(destination,tuple) or destination[0] not in ('127.0.0.1','::1'):
            raise AssertionError('non-loopback connection forbidden')
        report['connects'].append({'host':destination[0],'port':destination[1]})


@contextmanager
def serving(root, label):
    listener=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
    listener.bind(('127.0.0.1',0))
    listener.listen(128)
    port=listener.getsockname()[1]
    app=local_server.build_local_app(root,data_parent=DATA,port=port)
    server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=port,access_log=False,log_level='warning'))
    thread=threading.Thread(target=server.run,kwargs={'sockets':[listener]},daemon=True)
    item={'label':label,'port':port,'root_chars':len(str(root)),
        'database_chars':len(str(root/'workbench.db')),'started':False,'stopped':False}
    report['servers'].append(item)
    thread.start()
    try:
        deadline=time.monotonic()+15
        while not server.started and time.monotonic()<deadline:
            assert thread.is_alive(), 'server stopped before startup'
            time.sleep(.02)
        assert server.started
        item['started']=True
        yield app,'http://127.0.0.1:'+str(port)
    finally:
        server.should_exit=True
        thread.join(timeout=20)
        listener.close()
        item['stopped']=not thread.is_alive()
        assert item['stopped'], 'owned server did not stop'


class Client:
    def __init__(self,base,cookies):
        self.base=base
        self.cookies=cookies
        self.csrf=None
        self.opener=build_opener(ProxyHandler({}),HTTPCookieProcessor(cookies))

    def request(self,method,path,body=None,*,expected=200,raw=None,content_type=None,headers=None,binary=False):
        data=raw if raw is not None else (canonical_json(body).encode() if body is not None else None)
        meta={'Origin':self.base}
        if data is not None:meta['Content-Type']=content_type or 'application/json'
        if self.csrf:meta['X-CSRF-Token']=self.csrf
        meta.update(headers or {})
        request=Request(self.base+path,data=data,headers=meta,method=method)
        try:response=self.opener.open(request,timeout=15)
        except HTTPError as error:response=error
        with response:
            result=response.read();status=response.status
        report['requests'].append({'method':method,'path':path,'status':status,
            'input_bytes':len(data or b''),'input_sha256':sha256(data or b'').hexdigest(),
            'response_bytes':len(result),'response_sha256':sha256(result).hexdigest()})
        assert status==expected,(method,path,status,result[:200])
        return result if binary else json.loads(result)

    def login(self):
        self.csrf=self.request('POST','/api/login',{'username':'local-lawyer','password':PASSWORD})['csrf_token']


def upload(client,matter,raw):
    boundary='qxsynthetic'+uuid4().hex
    parts=[]
    for name,value in {'baseline_view':'original','local_processing_confirmed':'yes',
        'local_policy_id':'local-workpaper-v1'}.items():
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
    parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="independent.docx"\r\nContent-Type: {DOCX_MIME}\r\n\r\n'.encode())
    parts.extend((raw,b'\r\n',f'--{boundary}--\r\n'.encode()))
    return client.request('POST',f'/api/matters/{matter}/documents',raw=b''.join(parts),
        content_type='multipart/form-data; boundary='+boundary,headers={'Idempotency-Key':'long-path-source-upload'},expected=202)


def read_snapshot(app,client,matter,document):
    token=next(item.value for item in client.cookies if item.name=='qx_session')
    with app.state.database.session() as db:
        actor=authenticate(token,db)
        version=read_version(UUID(matter),UUID(document['version_id']),actor,db)
    assert not str(app.state.database.storage_root).startswith('\\\\?\\')
    assert not str(app.state.database.engine.url.database).startswith('\\\\?\\')
    return version


def restored_read(root,label,cookies,matter,document,version,raw):
    original=root/'protected'/version.storage_ref
    assert len(str(original.parent))>260 and backup.checked_file(original,root/'protected')==raw
    with serving(root,label) as (app,base):
        client=Client(base,cookies)
        client.request('GET','/api/matters',expected=401)
        client.login()
        payload=client.request('GET',f'/api/recovery/matters/{matter}/originals/{version.id}',binary=True)
        assert payload==raw and sha256(payload).hexdigest()==version.sha256
        historical=read_snapshot(app,client,matter,document)
        assert historical.storage_ref==version.storage_ref and historical.sha256==version.sha256
        for path in ('/api/matters',f'/api/matters/{matter}/documents'):
            assert client.request('POST',path,{},expected=409)['code']=='BLOCKED_LIVE'
    report['checks'].append({'name':label,'original_parent_chars':len(str(original.parent)),
        'storage_ref':version.storage_ref,'original_sha256':version.sha256,'passed':True})


def main():
    DATA.mkdir()
    root=long_directory(DATA,'中文合同',195)
    local_server.initialize_workspace(root,'local-lawyer',PASSWORD,data_parent=DATA)
    raw=independent_docx()
    cookies=CookieJar()
    with serving(root,'source') as (app,base):
        client=Client(base,cookies);client.login()
        matter=client.request('POST','/api/matters',{
            'title':'独立合成长路径合同','contract_type':'sales','review_mode':'pre_sign',
            'position':'buyer','objectives':['核对独立合成资料'],'material_mode':'local'},expected=201)['id']
        document=upload(client,matter,raw)
        deadline=time.monotonic()+20
        while True:
            job=client.request('GET','/api/jobs/'+document['job_id'])
            if job['state'] in ('completed','failed','blocked'):break
            assert time.monotonic()<deadline,'parse did not settle'
            time.sleep(.04)
        assert job['state']=='completed',job
        anchors=client.request('GET',f'/api/matters/{matter}/documents/{document["version_id"]}/anchors')
        assert any('独立虚构材料，仅供工程测试。' in item['quote'] for item in anchors['anchors'])
        version=read_snapshot(app,client,matter,document)
        fetched=client.request('GET',f'/api/matters/{matter}/documents/{version.id}/original?sha256={version.sha256}',binary=True)
        assert fetched==raw and sha256(fetched).hexdigest()==version.sha256
        assert version.storage_ref==f'{matter}/{version.id}/original.bin'
    original=root/'protected'/version.storage_ref
    assert len(str(original.parent))>260 and filesystem_path(original).read_bytes()==raw
    report['checks'].append({'name':'http_upload_parse_original','original_parent_chars':len(str(original.parent)),
        'storage_ref':version.storage_ref,'original_sha256':version.sha256,'passed':True})
    archive=DATA/'backup-first.qxbak'
    created=workspace_backup.create_workspace_backup(root,archive,PASSPHRASE,data_parent=DATA)
    assert created['verified']
    first=workspace_backup.restore_workspace_backup(archive,long_directory(DATA,'中文恢复',160),PASSPHRASE)
    assert first['quarantined']
    restored=Path(first['restored_root'])
    restored_read(restored,'first_recovery',cookies,matter,document,version,raw)
    archive2=DATA/'backup-second.qxbak'
    created2=workspace_backup.create_workspace_backup(restored,archive2,PASSPHRASE,data_parent=DATA)
    second=workspace_backup.restore_workspace_backup(archive2,long_directory(DATA,'二次恢复',160),PASSPHRASE)
    assert second['quarantined'] and created['workspace_id']==first['workspace_id']==created2['workspace_id']==second['workspace_id']
    restored_read(Path(second['restored_root']),'second_recovery',cookies,matter,document,version,raw)
    assert backup.checked_file(original,root/'protected')==raw
    assert calls=={'model_generate':0,'jev_judge':0}
    report['archives']=[created,created2]
    report['success']=True


report['input_hashes_before']=input_hashes()
started=time.monotonic()
sys.addaudithook(audit)
DeepSeekProvider.generate=no_model
JevProvider.judge=no_jev
try:main()
except BaseException as error:
    report['success']=False;report['error_type']=type(error).__name__;report['error']=str(error)
    traceback.print_exc()
finally:
    DeepSeekProvider.generate=original_generate;JevProvider.judge=original_judge
    report['input_hashes_after']=input_hashes()
    report['inputs_stable']=report['input_hashes_before']==report['input_hashes_after']
    report['elapsed_seconds']=time.monotonic()-started
    report['model_calls']=calls
    report['limitations']=['Python source HTTP, not Electron/GUI/installer/frozen backend',
        'Source and recovered original parents exceed 260 characters; database file paths remain below 260',
        'No real documents, external network, model, Jev or F-drive data used']
    report['script_sha256']=sha256(Path(__file__).read_bytes()).hexdigest()
    (BASE/'backup-tcp-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({key:report[key] for key in ('success','inputs_stable','elapsed_seconds','model_calls')},ensure_ascii=False))
raise SystemExit(0 if report.get('success') else 1)
