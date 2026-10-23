import datetime,hashlib,json,pathlib,subprocess,time
root=pathlib.Path(__file__).resolve().parents[3]
out=pathlib.Path(__file__).resolve().parent
names=['desktop/'+n for n in ['profile-basis.cjs','profile-approval.cjs','model-control.cjs','backend.cjs','model-session.cjs','model-approval.cjs','model-approval-window.cjs','model-approval.html','model-approval.js','model-approval.css','model-approval-preload.cjs','preload.cjs','main.cjs','package.json']]+['src/cn_contract/domain.py','src/cn_contract/web/app.py','tests/integration/test_assistant_frontend.py']
names+=sorted(str(p.relative_to(root)).replace('\\','/') for p in (root/'desktop/tests').glob('*') if p.is_file())
def snapshot():return {n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in names}
before=snapshot()
command=['C:/Program Files/nodejs/node.exe','--test','--test-reporter=tap',str(out/'probes.cjs')]
start=datetime.datetime.now(datetime.timezone.utc).isoformat(); clock=time.monotonic()
result=subprocess.run(command,cwd=root,capture_output=True)
(out/'probe.log').write_bytes(result.stdout+result.stderr)
after=snapshot()
for name,data in [('inputs-before.json',before),('inputs-after.json',after),('run-result.json',{'command':command,'cwd':str(root),'started_utc':start,'exit_code':result.returncode,'seconds':round(time.monotonic()-clock,3),'input_count':len(before),'inputs_equal':before==after,'baseline':'d3c3b173af0fe3f3f0d878df6793a601e181d081'})]:
 (out/name).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(result.stdout.decode('utf-8'));print('exit',result.returncode,'inputs',len(before),'stable',before==after)
