import datetime,hashlib,json,os,pathlib,subprocess,time
root=pathlib.Path(__file__).resolve().parents[3]; out=pathlib.Path(__file__).resolve().parent
files=[]
for folder in ['src','tests','scripts','desktop']:
 for p in (root/folder).rglob('*'):
  if p.is_file() and p.suffix in ('.py','.mjs','.cjs','.html','.css','.json') and not any(x in p.parts for x in ('node_modules','__pycache__')):
   files.append(p.relative_to(root).as_posix())
files+=['requirements.lock','pyproject.toml']
def hashes():return {n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in sorted(set(files))}
before=hashes(); (out/'inputs-before.json').write_text(json.dumps(before,indent=2)+'\n',encoding='utf-8')
commands=[('panel',['C:/Program Files/nodejs/node.exe','--test','--test-reporter=tap',str(out/'panel-probes.mjs')]),
 ('history',[str(root/'.venv/Scripts/python.exe'),'-X','utf8','-m','pytest','-q','--tb=short','--basetemp='+str(out/'fresh-d-01'),'--junitxml='+str(out/'history.xml'),str(out/'test_history_probes.py')])]
records=[];env=os.environ.copy();env['PYTHONPATH']=str(root/'tests/integration')+os.pathsep+str(root)
for name,command in commands:
 start=datetime.datetime.now(datetime.timezone.utc).isoformat();clock=time.monotonic()
 r=subprocess.run(command,cwd=root,env=env,capture_output=True)
 (out/(name+'.log')).write_bytes(r.stdout+r.stderr)
 records.append({'name':name,'command':command,'started_utc':start,'exit_code':r.returncode,'seconds':round(time.monotonic()-clock,3)})
 print(name,'exit',r.returncode);print(r.stdout.decode('utf-8',errors='replace')[-2500:])
after=hashes();(out/'inputs-after.json').write_text(json.dumps(after,indent=2)+'\n',encoding='utf-8')
record={'baseline':'5d5e688b14ac53b81029184413cd37ce631b144c','cwd':str(root),'results':records,'input_count':len(before),'inputs_equal':before==after}
(out/'run-result.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print('inputs',len(before),'equal',before==after)
