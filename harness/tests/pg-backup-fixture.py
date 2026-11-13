"""Synthetic-only native PostgreSQL fixture; never used by the backup runtime."""
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import sys
import uuid


def fixture(action, root, tools):
    root=Path(root); tools=Path(tools)
    runtime=root/'.local/case-memory-runtime'; cluster=runtime/'database'
    env={k:v for k,v in os.environ.items() if k.upper() in ('SYSTEMROOT','WINDIR','PATH','TEMP','TMP')}
    env.update(PGCLIENTENCODING='UTF8',LC_ALL='C',LANG='C')
    def command(name,args,input=None):
        # PostgreSQL grandchildren can retain inherited pipe handles after pg_ctl exits on Windows.
        with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
            result=subprocess.run([str(tools/'bin'/name),*args],input=input,stdout=out,stderr=err,
                                  env=env,creationflags=subprocess.CREATE_NO_WINDOW,timeout=45)
            out.seek(0);err.seek(0);stdout=out.read();stderr=err.read()
        if result.returncode:
            raise RuntimeError(name+': '+stderr.decode('utf-8',errors='replace'))
        return stdout.decode('utf-8').strip().replace('\r\n','\n')
    if action=='seed':
        runtime.mkdir(parents=True)
        identity={'id':str(uuid.uuid4()),'databasePassword':'ab'*32}
        (runtime/'instance.json').write_text(json.dumps(identity))
        password=root.parent/('synthetic-pg-password-'+uuid.uuid4().hex)
        password.write_text(identity['databasePassword'])
        try:
            command('initdb.exe',['-D',str(cluster),'-U','qx_memory','--auth=scram-sha-256','--encoding=UTF8','--locale=C','--pwfile='+str(password)])
        finally:
            password.unlink()
    else:
        identity=json.loads((runtime/'instance.json').read_text())
    env['PGPASSWORD']=identity['databasePassword']
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    def query(sql,database='hindsight'):
        return command('psql.exe',['-X','-w','-qAt','-v','ON_ERROR_STOP=1','-h','127.0.0.1','-p',str(port),'-U','qx_memory','-d',database],sql.encode('utf-8'))
    log=root.parent/('synthetic-pg-log-'+uuid.uuid4().hex)
    started=False
    try:
        command('pg_ctl.exe',['-D',str(cluster),'-w','-t','30','-l',str(log),'-o',f'-h 127.0.0.1 -p {port} -c shared_buffers=32MB','start'])
        started=True
        if action=='seed':
            query('CREATE DATABASE hindsight;','postgres')
            # Match pg0's bootstrap administrator, in addition to the application's role.
            query("CREATE ROLE postgres WITH SUPERUSER LOGIN PASSWORD '"+identity['databasePassword']+"';")
            query("""CREATE EXTENSION vector;
CREATE TABLE synthetic_memories(id int PRIMARY KEY, bank text NOT NULL, content text, embedding vector(3));
INSERT INTO synthetic_memories SELECT i,CASE WHEN i<=20 THEN 'case-a' ELSE 'case-b' END,'虚构记忆-'||i,('[1,'||i||',3]')::vector FROM generate_series(1,40) i;
CREATE INDEX synthetic_vector ON synthetic_memories USING hnsw(embedding vector_l2_ops);
BEGIN; INSERT INTO synthetic_memories VALUES(999,'case-a','uncommitted','[0,0,0]');ROLLBACK;
""")
        counts=query("SELECT bank,count(*) FROM synthetic_memories GROUP BY bank ORDER BY bank;")
        lookup="SELECT id FROM synthetic_memories ORDER BY embedding <-> '[1,3,3]' LIMIT 1;"
        index=query("SELECT am.amname,i.indisvalid,i.indisready FROM pg_index i JOIN pg_class c ON c.oid=i.indexrelid JOIN pg_am am ON am.oid=c.relam WHERE c.oid='public.synthetic_vector'::regclass AND i.indrelid='public.synthetic_memories'::regclass;")
        assert index=='hnsw|t|t',index
        plan=json.loads(query('SET enable_seqscan=off; EXPLAIN (FORMAT JSON) '+lookup))
        assert plan[0]['Plan']['Plans'][0]['Index Name']=='synthetic_vector',plan
        nearest=query('SET enable_seqscan=off; '+lookup)
        content=query('SELECT content FROM synthetic_memories WHERE id=3;')
        system=query('SELECT system_identifier FROM pg_control_system();')
        assert counts=='case-a|20\ncase-b|20',counts
        assert nearest=='3' and content=='虚构记忆-3'
        assert query('SELECT count(*) FROM synthetic_memories WHERE id=999;')=='0'
        assert query("SELECT extversion FROM pg_extension WHERE extname='vector';")=='0.8.5'
        result={'records':40,'banks':2,'nearest':3,'systemIdentifier':system,'readback':True,'hnswIndexUsed':True}
    finally:
        if started or (cluster/'postmaster.pid').exists():
            command('pg_ctl.exe',['-D',str(cluster),'-w','-t','30','-m','fast','stop'])
        log.unlink(missing_ok=True)
    assert not (cluster/'postmaster.pid').exists()
    return result


if __name__=='__main__':
    print(json.dumps(fixture(*sys.argv[1:])))
