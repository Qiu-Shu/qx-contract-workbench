"""Independent native HTTP + real adapter + synthetic loopback browser fixture."""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hashlib
import json
from io import BytesIO
from pathlib import Path
import socket
from threading import Event, Thread
import time
from types import SimpleNamespace
from uuid import UUID, uuid4

from docx import Document
from sqlalchemy import select
import uvicorn

from cn_contract import domain as d
from cn_contract.assistant.providers.main import DeepSeekProvider
from cn_contract.assistant.providers.policy import MainModelRuntime, encoded, sha
from cn_contract.persistence import UserRow
from cn_contract.web.local_server import initialize_workspace, build_local_app, _database


TEXTS = {
    'first':'独立合成第一问：请整理虚构交货咨询。',
    'second':'独立合成第二问：请列出虚构交货日期待核事项。',
    'edit':'独立合成待发送草稿：这是等待回复时新写的一句。',
    'unknown':'独立合成丢失回执：请整理虚构的验收事项。',
    'cancel':'独立合成取消场景：请整理虚构的取消材料。',
    'switch':'独立合成切换场景：请整理虚构的迟到回复。',
    'revoked':'独立合成撤权场景：请整理虚构的保密事项。',
    'blocked':'独立合成阻断场景：未获外发权限的附件和技能。',
}
OUTPUTS = {key:f'独立合成候选 {key}：请律师核对消息原文。' for key in TEXTS}
OUTPUTS['first'] += '\n<img src="https://external.invalid/x" onerror="alert(1)">保持为纯文字。'


@contextmanager
def serve(app):
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        sock.listen(32)
        server = uvicorn.Server(uvicorn.Config(app, log_level='critical', access_log=False))
        thread = Thread(target=lambda:server.run(sockets=[sock]), daemon=True)
        thread.start()
        deadline = time.monotonic()+30
        try:
            while not server.started:
                assert thread.is_alive() and time.monotonic()<deadline, 'native startup failed'
                time.sleep(.02)
            yield 'http://127.0.0.1:'+str(sock.getsockname()[1])
        finally:
            server.should_exit = True
            thread.join(30)
            assert not thread.is_alive(), 'native shutdown failed'


@contextmanager
def ui_fixture(target):
    target = Path(target).resolve()
    target.mkdir(parents=True, exist_ok=True)
    root = target/'合成 首页 工作区'
    assert not root.exists(), 'use a fresh synthetic output directory'
    secret = 'SYNTHETIC_UI_FIXTURE_NOT_A_REAL_KEY'
    credentials = {'username':'首页生成合成律师', 'password':'fixture123'}
    received, errors = [], []
    entered, release = Event(), Event()
    release.set()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_POST(self):
            try:
                assert self.path == '/chat/completions', 'unexpected loopback path'
                assert self.headers.get('Authorization') == 'Bearer '+secret, 'synthetic authorization mismatch'
                raw = self.rfile.read(int(self.headers['Content-Length']))
                payload = json.loads(raw)
                source = json.loads(payload['messages'][1]['content'])
                name = next((key for key,value in TEXTS.items() if value == source['content']), None)
                assert name is not None, 'unapproved synthetic source'
                received.append({'case':name, 'message_id':source['message_id'],
                    'source_sha256':sha(source['content']), 'wire_sha256':sha(raw.decode('utf-8'))})
                entered.set()
                assert release.wait(25), 'synthetic response gate timed out'
                candidate = {'text':OUTPUTS[name], 'citations':[
                    {'message_id':source['message_id'], 'quote_sha256':source['quote_sha256']}]}
                body = json.dumps({'id':'synthetic-ui-'+name, 'model':'deepseek-flash',
                    'object':'chat.completion', 'created':1,
                    'choices':[{'index':0, 'finish_reason':'stop', 'message':{
                        'role':'assistant', 'content':json.dumps(candidate, ensure_ascii=False)}}],
                    'usage':{'prompt_tokens':30, 'completion_tokens':12, 'total_tokens':42}},
                    ensure_ascii=False).encode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass
            except Exception as error:
                errors.append({'type':type(error).__name__, 'error':str(error)})
                self.send_error(500, 'synthetic fixture failure')

    upstream = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    upstream.daemon_threads = True
    Thread(target=upstream.serve_forever, daemon=True).start()
    try:
        initialize_workspace(root, **credentials, data_parent=target)
        database = _database(root)
        try:
            with database.session() as db:
                actor_id = UUID(db.scalar(select(UserRow.id)))
        finally:
            database.engine.dispose()
        workspace_id = json.loads((root/'workspace.json').read_text('utf-8'))['workspace_id']
        config = d.MainModelConfig(enabled=True, model='deepseek-flash', input_usd_per_million='0.3',
            output_usd_per_million='1.2', price_reference='synthetic-browser-only', timeout_seconds=30)
        policy = d.MainModelPolicy(policy_id=uuid4(), workspace_id=workspace_id, actor_id=actor_id,
            config_sha256=sha(encoded(config)), allowed_content_sha256s=tuple(sha(value) for value in TEXTS.values()),
            max_total_usd='1', max_calls=20, expires_at=datetime.now(timezone.utc)+timedelta(hours=1))
        runtime = MainModelRuntime(DeepSeekProvider.for_synthetic_loopback(config, lambda:secret,
            f'http://127.0.0.1:{upstream.server_port}/chat/completions'), policy)
        app = build_local_app(root, data_parent=target, assistant_model_runtime=runtime)
        document = Document()
        document.add_paragraph('独立虚构的浏览器附件，仅用于验证本机收件与外发阻断。')
        stream = BytesIO()
        document.save(stream)
        attachment = target/'独立合成浏览器附件.docx'
        attachment.write_bytes(stream.getvalue())
        app.state.database._assistant_synthetic_hashes = frozenset({hashlib.sha256(stream.getvalue()).hexdigest()})
        with serve(app) as origin:
            try:
                yield SimpleNamespace(target=target, root=root, app=app, database=app.state.database,
                    origin=origin, runtime=runtime, credentials=credentials, received=received,
                    errors=errors, entered=entered, release=release, texts=TEXTS, outputs=OUTPUTS,
                    attachment=attachment)
            finally:
                release.set()
    finally:
        release.set()
        upstream.shutdown()
        upstream.server_close()
