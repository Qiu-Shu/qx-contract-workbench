"""Synthetic HTTP stand-in for lifecycle tests; this is NOT Hindsight API validation."""
import json
import os
from pathlib import Path
import subprocess
from urllib.parse import urlsplit


async def app(scope, receive, send):
    if scope['type'] == 'lifespan':
        while True:
            event = await receive()
            if event['type'] == 'lifespan.startup':
                await send({'type': 'lifespan.startup.complete'})
            if event['type'] == 'lifespan.shutdown':
                await send({'type': 'lifespan.shutdown.complete'})
                return
    elif scope['type'] == 'http':
        result = {'ready': True}
        if scope['path'] == '/v1/default/banks':
            uri = urlsplit(os.environ['HINDSIGHT_API_DATABASE_URL'])
            env = {**os.environ, 'PGPASSWORD': uri.password, 'PGCLIENTENCODING': 'UTF8'}
            sql = """SELECT json_build_object('records',count(*),'groups',count(DISTINCT bank),
                'content',(SELECT content FROM synthetic_memories WHERE id=3),
                'system',(SELECT system_identifier::text FROM pg_control_system())) FROM synthetic_memories;"""
            response = subprocess.run([str(Path(os.environ['TEST_PG_TOOLS'])/'bin/psql.exe'),
                '-X','-w','-qAt','-v','ON_ERROR_STOP=1','-h',uri.hostname,'-p',str(uri.port),
                '-U',uri.username,'-d',uri.path[1:],'-c',sql],env=env,capture_output=True,
                creationflags=subprocess.CREATE_NO_WINDOW,timeout=15)
            if response.returncode:
                raise RuntimeError('Synthetic database readback failed')
            result = json.loads(response.stdout.decode('utf-8'))
        await send({'type':'http.response.start','status':200,'headers':[(b'content-type',b'application/json')]})
        await send({'type':'http.response.body','body':json.dumps(result).encode()})
