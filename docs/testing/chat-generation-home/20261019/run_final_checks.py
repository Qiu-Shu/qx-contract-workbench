"""Record targeted regression and the existing four development gates."""
import hashlib, json, subprocess, time, sys
from pathlib import Path
from xml.etree import ElementTree as ET

root=Path(__file__).resolve().parents[2]
out=Path(__file__).resolve().parent
if len(sys.argv)>1:
    out=Path(sys.argv[1]).resolve();out.mkdir(parents=True,exist_ok=False)
py=str(root/'.venv/Scripts/python.exe')
def snapshot():
    names=subprocess.check_output(['git','ls-files','-co','--exclude-standard'],cwd=root).decode('utf-8').splitlines()
    files=sorted({p.as_posix() for raw in names if (p:=Path(raw)).suffix in {'.py','.mjs','.cjs','.css','.html','.toml'}
        and (p.parts[0] in {'src','tests','scripts','desktop'} or len(p.parts)==1)})
    return {name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in files}
def save(name,value):
    (out/name).write_text(json.dumps(value,ensure_ascii=False,indent=2),'utf-8')
files=['test_assistant_frontend.py','test_assistant_pages.py','test_assistant_generation_history.py',
       'test_assistant_generation_routes.py','test_assistant_history_routes.py',
       'test_assistant_attachment_routes.py','test_assistant_model_backup.py',
       'test_assistant_routes.py','test_assistant_task_manager.py','test_local_workbench.py']
commands={'targeted':[py,'-X','utf8','-m','pytest',*['tests/integration/'+f for f in files],
      'tests/unit/test_assistant_model_contract.py','-q','--tb=short','--junitxml='+str(out/'final-targeted.xml')],
    'defaults':[py,'scripts/verify_defaults.py'],
    'sources':[py,'scripts/verify_sources.py'],
    'dependencies':[py,'scripts/verify_runtime_dependencies.py'],
    'schema':[py,'-m','cn_contract.cli','schema','--check']}
before=snapshot();save('final-source-before.json',before)
results={}
for label,command in commands.items():
    save(label+'-command.json',command)
    start=time.monotonic()
    with (out/(label+'.log')).open('w',encoding='utf-8') as log:
        result=subprocess.run(command,cwd=root,stdout=log,stderr=subprocess.STDOUT)
    (out/(label+'.exit')).write_text(str(result.returncode),'ascii')
    results[label]={'exit':result.returncode,'seconds':time.monotonic()-start}
    print(label,result.returncode,flush=True)
after=snapshot();save('final-source-after.json',after)
save('final-checks.json',{'results':results,'source_count':len(before),'source_unchanged':before==after})
raise SystemExit(0 if before==after and all(v['exit']==0 for v in results.values()) else 1)
