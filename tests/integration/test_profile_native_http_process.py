"""Actual owned Windows pipe and TCP profile flow, with a loopback-only provider."""
import hashlib
import json
import os
from pathlib import Path
from queue import Queue
import subprocess
import sys
from threading import Thread
import time
from uuid import uuid4

import httpx

from tests.integration.test_assistant_main_provider import config, server, KEY
from tests.integration.test_assistant_profile_execution import archive_response


def test_private_pipe_authorizes_one_http_profile_job_and_history_never_resends(tmp_path):
    project = Path(__file__).resolve().parents[2]
    network = tmp_path / 'network.json'
    nonce = 'e' * 32
    with server(archive_response()) as (endpoint, received, _):
        process = subprocess.Popen(
            [sys.executable, str(project / 'tests/helpers/synthetic_native_approval_entry.py'), endpoint],
            cwd=project, env={**os.environ, 'QX_PROBE_SETTINGS_NETWORK': str(network)},
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        lines = Queue()
        def read_lines():
            for line in process.stdout:
                lines.put(line)
            lines.put(None)

        Thread(target=read_lines, daemon=True).start()
        sequence = 0

        def send(value):
            process.stdin.write((json.dumps(value, ensure_ascii=False) + '\n').encode('utf-8'))
            process.stdin.flush()
            line = lines.get(timeout=30)
            assert line is not None, 'owned control process closed before replying'
            return json.loads(line)

        def control(operation, payload):
            nonlocal sequence
            sequence += 1
            result = send(dict(event='model-control', protocol='qx-model-control-v1', nonce=nonce,
                               sequence=sequence, operation=operation, payload=payload))
            assert result['sequence'] == sequence
            return result

        try:
            ready = send(dict(data_parent=str(tmp_path / '中文 合成资料'), nonce=nonce,
                              username='synthetic', password='fixture123'))
            assert ready['event'] == 'ready'
            origin = f"http://127.0.0.1:{ready['port']}"
            with httpx.Client(base_url=origin, timeout=15, trust_env=False) as client:
                login = client.post('/api/login', json={'username': 'synthetic', 'password': 'fixture123'})
                assert login.status_code == 200
                headers = {'X-CSRF-Token': login.json()['csrf_token'], 'Origin': origin}
                created = client.post('/api/assistant/conversations', headers=headers,
                                      json={'request_id': str(uuid4())})
                assert created.status_code == 201
                conversation = created.json()
                base = '/api/assistant/conversations/' + conversation['scope']['conversation_id']
                content = '甲称借款35000元。'
                draft = client.put(base + '/draft', headers=headers, json={
                    'expected_scope': conversation['scope'],
                    'expected_composer_revision': conversation['composer_revision'], 'content': content})
                assert draft.status_code == 200
                view = draft.json()
                selection = dict(request_id=str(uuid4()), expected_scope=view['scope'],
                                 expected_composer_revision=view['composer_revision'], project_intake=True)
                submission = {**selection, 'content': content}
                configured = control('configure', {'config': config().model_dump(mode='json'), 'secret': KEY})
                assert configured['ok'] is True
                preview = client.post(base + '/profile-preview', headers=headers, json=selection)
                assert preview.status_code == 200, preview.status_code
                basis = preview.json()
                assert basis['project_intake'] is True and basis['base_profile_revision'] == 0
                assert client.post(base + '/profile-generations', headers=headers, json=submission).status_code == 403
                assert not received
                payload = dict(session_token=client.cookies.get('qx_session'),
                               expected_config_version=configured['config_version'], basis=basis,
                               max_total_usd='1', valid_for_seconds=120)
                authorized = control('authorize_profile', payload)
                assert authorized['ok'] is True and authorized['status'] == 'authorized'
                assert not received
                response = client.post(base + '/profile-generations', headers=headers, json=submission)
                assert response.status_code == 202, response.status_code
                attempt = response.json()
                deadline = time.monotonic() + 20
                while attempt['state'] in ('reserved', 'sending') and time.monotonic() < deadline:
                    time.sleep(.03)
                    response = client.get('/api/assistant/attempts/' + attempt['id'])
                    assert response.status_code == 200
                    attempt = response.json()
                assert attempt['state'] == 'received'
                assert attempt['output']['candidate']['profile_patch']['changes'][0]['verification'] == 'unverified'
                assert attempt['receipt']['usage']['total_tokens'] == 42
                assert len(received) == 1
                assert hashlib.sha256(received[0]['body']).hexdigest() == basis['wire_sha256']
                profile = client.get(base + '/profile')
                assert profile.status_code == 200 and profile.json()['revision'] == 1
                current = client.get(base).json()
                assert current['projection_intake_id'] is not None
                replay = client.post(base + '/profile-generations', headers=headers, json=submission)
                assert replay.status_code == 202 and replay.json()['id'] == attempt['id']
                found = client.get(base + '/generations/by-request/' + selection['request_id'])
                assert found.status_code == 200 and found.json()['id'] == attempt['id']
                run = client.get('/api/assistant/runs/' + attempt['run_id'])
                assert run.status_code == 200
                history = client.get(base + '/generation-history', params={'message_id': run.json()['message_id']})
                assert history.status_code == 200
                assert history.json()['items'][0]['attempt']['id'] == attempt['id']
                existing = control('authorize_profile', payload)
                assert existing['ok'] is True and existing['status'] == 'existing'
                assert len(received) == 1
                assert json.loads(network.read_text('utf-8')) == {'loopback_calls': 1, 'external_requests': 0}
            process.stdin.close()
            assert process.wait(timeout=20) == 0
            assert process.stderr.read() == b''
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=10)
            for stream in (process.stdin, process.stdout, process.stderr):
                stream.close()
