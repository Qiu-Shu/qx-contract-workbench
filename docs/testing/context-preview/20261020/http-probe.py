"""Synthetic Windows loopback HTTP probe; this is not Electron/installer/GUI evidence."""
import asyncio
from contextlib import asynccontextmanager
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
from uuid import uuid4

import uvicorn
from sqlalchemy import text
from cn_contract import domain as d
from cn_contract.config import canonical_json
from cn_contract.assistant.providers.main import DeepSeekProvider
from cn_contract.assistant.providers.jev import JevProvider
from cn_contract.assistant.providers.registry import MainModelRegistry
from cn_contract.assistant.tools.library import LegalLibraryAdapter
from cn_contract.web.local_server import build_local_app, initialize_workspace
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tests.integration.test_assistant_library_adapter import library


BASE = Path(__file__).resolve().parent
DATA = BASE / ('http-data-' + uuid4().hex[:10])
REPORT = BASE / 'http-report.json'
counts = {'provider_generate':0, 'secret_resolver':0, 'jev_judge':0,
          'library_search':0, 'library_read_original':0}
report = {'kind':'Windows Python-source TCP HTTP synthetic probe', 'platform':platform.platform(),
    'not_evidence_for':['Electron', 'installer', 'GUI', 'live model', 'real legal data'],
    'input_hashes':[], 'checks':[], 'connects':[], 'data_root':str(DATA)}
original_generate = DeepSeekProvider.generate
original_judge = JevProvider.judge
original_search = LegalLibraryAdapter.search
original_read = LegalLibraryAdapter.read_original
server = thread = listener = None


async def forbidden_generate(*args, **kwargs):
    counts['provider_generate'] += 1
    raise AssertionError('preview attempted generation')


async def forbidden_judge(*args, **kwargs):
    counts['jev_judge'] += 1
    raise AssertionError('preview attempted Jev')


def forbidden_secret():
    counts['secret_resolver'] += 1
    raise AssertionError('preview resolved a secret')


def search(self, *args, **kwargs):
    counts['library_search'] += 1
    return original_search(self, *args, **kwargs)


def read_original(self, *args, **kwargs):
    counts['library_read_original'] += 1
    return original_read(self, *args, **kwargs)


def digest(value):
    return sha256(canonical_json(value).encode('utf-8')).hexdigest()


def table_counts(database):
    with database.session() as db:
        names = db.scalars(text("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'assistant_%' ORDER BY name")).all()
        return {name:db.scalar(text('SELECT COUNT(*) FROM '+name)) for name in names}


def main():
    global server, thread, listener
    DATA.mkdir()
    library_root, _ = library.__wrapped__(DATA)
    root = DATA/'synthetic-workspace'
    initialize_workspace(root, 'lawyer', 'fixture123', data_parent=DATA)
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(('127.0.0.1', 0))
    port = listener.getsockname()[1]
    listener.listen(128)
    base = 'http://127.0.0.1:'+str(port)
    report['port'] = port
    report['source_hashes'] = {str(path.relative_to(DATA)):sha256(path.read_bytes()).hexdigest()
        for path in (DATA/'cases.csv', *(DATA/'laws').glob('*.md'))}

    def audit(event, args):
        if event == 'socket.connect':
            destination = args[1]
            if not isinstance(destination, tuple) or destination[0] not in {'127.0.0.1','::1'}:
                raise AssertionError('non-loopback network connection forbidden')
            report['connects'].append({'host':destination[0], 'port':destination[1],
                'probe_http':destination[1]==port})
    sys.addaudithook(audit)
    DeepSeekProvider.generate = forbidden_generate
    JevProvider.judge = forbidden_judge
    LegalLibraryAdapter.search = search
    LegalLibraryAdapter.read_original = read_original
    registry = MainModelRegistry()
    app = build_local_app(root, data_parent=DATA, port=port, library_root=library_root,
        assistant_model_runtime=registry)
    loops = []
    original_lifespan = app.router.lifespan_context
    @asynccontextmanager
    async def lifespan(application):
        loops.append(asyncio.get_running_loop())
        async with original_lifespan(application):
            yield
    app.router.lifespan_context = lifespan
    server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=port,
        access_log=False, log_level='warning'))
    thread = threading.Thread(target=server.run, kwargs={'sockets':[listener]}, daemon=True)
    thread.start()
    deadline = time.monotonic()+15
    while not server.started and time.monotonic() < deadline:
        assert thread.is_alive(), 'server stopped before startup'
        time.sleep(.02)
    assert server.started
    report['startup'] = {'server':'uvicorn.Server', 'socket':'AF_INET loopback TCP', 'started':True}
    opener = build_opener(ProxyHandler({}), HTTPCookieProcessor(CookieJar()))
    csrf = None

    def http(method, path, body=None, expected=200, overrides=None):
        payload = canonical_json(body).encode('utf-8') if body is not None else None
        headers = {'Origin':base}
        if payload is not None: headers['Content-Type']='application/json'
        if csrf is not None: headers['X-CSRF-Token']=csrf
        headers.update(overrides or {})
        request = Request(base+path, data=payload, headers=headers, method=method)
        try:
            response = opener.open(request, timeout=10)
        except HTTPError as error:
            response = error
        with response:
            raw = response.read()
            value = json.loads(raw)
            status = response.status
        report['input_hashes'].append({'method':method, 'path':path, 'body_sha256':sha256(payload or b'').hexdigest(),
            'body_bytes':len(payload or b''), 'status':status, 'origin':headers['Origin']})
        assert status == expected, (method,path,status,value)
        return value

    csrf = http('POST','/api/login',{'username':'lawyer','password':'fixture123'})['csrf_token']
    assert http('GET','/api/session')['username'] == 'lawyer'
    view = http('POST','/api/assistant/conversations', {'request_id':str(uuid4()),
        'display_title':'完全合成 TCP 上下文预览'}, expected=201)
    url = '/api/assistant/conversations/'+view['scope']['conversation_id']
    research_id = str(uuid4())
    http('POST',url+'/researches', {'request_id':research_id, 'expected_scope':view['scope'],
        'expected_composer_revision':view['composer_revision'], 'content':'租赁',
        'requested_skill':'legal_research'}, expected=202)
    deadline = time.monotonic()+15
    while True:
        research = http('GET',url+'/researches/by-request/'+research_id)
        if research and research['run']['state'] not in {'queued','retrieving'}: break
        assert time.monotonic()<deadline, 'research did not complete'
        time.sleep(.03)
    assert research['run']['state']=='completed'
    receipt = research['receipts'][0]
    assert receipt['result']['result']['page']['state']=='ready'
    saved_ids = receipt['result']['citation_ids']
    assert saved_ids
    saved = {identifier:http('GET','/api/assistant/library-citations/'+identifier) for identifier in saved_ids}
    view = http('GET',url)
    question = '仅根据所选完全虚构片段，整理需要律师核对的问题。😀\n不作正式法律结论。'
    view = http('PUT',url+'/draft', {'expected_scope':view['scope'],
        'expected_composer_revision':view['composer_revision'], 'content':question})
    selection = {'expected_scope':view['scope'], 'expected_composer_revision':view['composer_revision'],
        'citation_ids':saved_ids}
    before = table_counts(app.state.database)
    before_calls = counts.copy()
    assert before['assistant_messages']==before['assistant_runs']==1
    for name in ('assistant_model_attempts','assistant_model_outputs','assistant_judge_attempts'):
        assert before[name]==0
    previews = {}

    def preview(name, state):
        value = http('POST',url+'/context-preview',selection)
        assert value['state']==state and value['sending_enabled'] is False
        assert value['scope']==view['scope'] and value['composer_revision']==view['composer_revision']
        assert value['manifest']['question']==question and value['manifest_sha256']==digest(value['manifest'])
        assert [item['saved_citation_id'] for item in value['manifest']['sources']]==saved_ids
        for item in value['manifest']['sources']:
            citation = saved[item['saved_citation_id']]['citation']
            assert all(item[key]==citation[key] for key in item if key!='saved_citation_id')
            assert sha256(item['quote'].encode()).hexdigest()==item['quote_sha256']
            assert item['support_status']==item['applicability_status']=='unverified'
        if state=='not_configured':
            assert all(value[key] is None for key in ('model','config_sha256','max_input_bytes',
                'wire_payload_json','wire_sha256','wire_bytes'))
        else:
            wire = value['wire_payload_json'].encode('utf-8')
            assert len(wire)==value['wire_bytes'] and sha256(wire).hexdigest()==value['wire_sha256']
            assert json.loads(value['wire_payload_json'])['messages'][1]['content']==canonical_json(value['manifest'])
        assert table_counts(app.state.database)==before and http('GET',url)==view
        assert counts==before_calls
        previews[name]=value
        report['checks'].append({'name':name, 'state':state, 'passed':True})
        return value

    preview('unconfigured','not_configured')
    async def configure(limit=65536, enabled=True):
        config = d.MainModelConfig(enabled=enabled, model='deepseek-flash', max_input_bytes=limit,
            input_usd_per_million='1', output_usd_per_million='2', price_reference='synthetic probe only')
        registry.configure(DeepSeekProvider(config, forbidden_secret))
    asyncio.run_coroutine_threadsafe(configure(),loops[0]).result(timeout=5)
    ready = preview('configured','ready')
    asyncio.run_coroutine_threadsafe(configure(ready['wire_bytes']),loops[0]).result(timeout=5)
    exact = preview('exact_utf8_budget','ready')
    asyncio.run_coroutine_threadsafe(configure(ready['wire_bytes']-1),loops[0]).result(timeout=5)
    large = preview('one_byte_over_budget','input_too_large')
    assert ready['wire_payload_json']==exact['wire_payload_json']==large['wire_payload_json']
    assert ready['manifest']==large['manifest']
    asyncio.run_coroutine_threadsafe(configure(enabled=False),loops[0]).result(timeout=5)
    preview('disabled','not_configured')
    rejected = http('POST',url+'/context-preview',selection, expected=403,
        overrides={'Origin':'https://independent-synthetic.invalid'})
    assert rejected['code']=='CROSS_MATTER_DENIED'
    rejected = http('POST',url+'/context-preview',selection, expected=403, overrides={'X-CSRF-Token':''})
    assert rejected['code']=='CROSS_MATTER_DENIED'
    stale = selection | {'expected_composer_revision':view['composer_revision']-1}
    rejected = http('POST',url+'/context-preview',stale, expected=409)
    assert rejected['code']=='VERSION_CONFLICT'
    assert table_counts(app.state.database)==before and http('GET',url)==view and counts==before_calls
    assert counts['provider_generate']==counts['secret_resolver']==counts['jev_judge']==0
    report['checks'].extend({'name':name, 'passed':True} for name in
        ('cross_origin_rejected','missing_csrf_rejected','stale_selection_rejected','no_preview_side_effects'))
    report['counts_before_preview']=before
    report['counts_after_preview']=table_counts(app.state.database)
    report['call_counters']=counts.copy()
    report['preview_call_delta']={key:counts[key]-before_calls[key] for key in counts}
    report['previews']=previews
    report['success']=True


try:
    main()
except BaseException as error:
    report['success']=False
    report['error_type']=type(error).__name__
    report['error']=str(error)
    traceback.print_exc()
finally:
    if server is not None: server.should_exit=True
    if thread is not None: thread.join(timeout=20)
    stopped = thread is None or not thread.is_alive()
    if listener is not None: listener.close()
    DeepSeekProvider.generate=original_generate
    JevProvider.judge=original_judge
    LegalLibraryAdapter.search=original_search
    LegalLibraryAdapter.read_original=original_read
    report['server_stopped']=stopped
    report['call_counters']=counts.copy()
    if not stopped: report['success']=False
    report['script_sha256']=sha256(Path(__file__).read_bytes()).hexdigest()
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({key:report[key] for key in ('success','server_stopped','call_counters')}, ensure_ascii=False))
raise SystemExit(0 if report.get('success') else 1)
