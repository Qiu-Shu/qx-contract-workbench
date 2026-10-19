"""Final native source verification with stable input evidence."""
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
from uuid import uuid4

BASE=Path(__file__).resolve().parent
ROOT=BASE.parents[1]
names=json.loads((BASE/'regression-source-before.json').read_text('utf-8'))
def snapshot(name):
    result={n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in names}
    (BASE/name).write_text(json.dumps(result,indent=2),encoding='utf-8')
    return result

for name in ('native-source-before.json','native-source-after.json','native-verification.json'):
    if (BASE/name).exists():shutil.copy2(BASE/name,BASE/('before-maintenance-'+name))
before=snapshot('native-source-before.json')
target=BASE/('native-current-'+uuid4().hex[:8])
command=[str(ROOT/'desktop/node_modules/electron/dist/electron.exe'),
         str(ROOT/'desktop/tests/model-control-acceptance.cjs'),str(target)]
(BASE/'native-command.json').write_text(json.dumps(command,indent=2),encoding='utf-8')
with (BASE/'native-current.log').open('wb') as output:
    result=subprocess.run(command,cwd=ROOT,stdout=output,stderr=subprocess.STDOUT,
                          creationflags=subprocess.CREATE_NO_WINDOW,timeout=90)
(BASE/'native-current.exit').write_text(str(result.returncode)+'\n',encoding='utf-8')
after=snapshot('native-source-after.json')
assert result.returncode==0 and before==after
report=json.loads((target/'report.json').read_text('utf-8'))
assert report['status']=='passed'
with sqlite3.connect(target/'合成 中文 资料/workspaces/main/workbench.db') as db:
    assert db.execute('PRAGMA quick_check').fetchall()==[('ok',)]
    assert db.execute('PRAGMA foreign_key_check').fetchall()==[]
    counts={t:db.execute('SELECT COUNT(*) FROM '+t).fetchone()[0] for t in
            ('assistant_model_attempts','assistant_model_receipts','assistant_model_outputs')}
    assert list(counts.values())==[1,1,1]
report.update(counts=counts,input_files=len(before),changed_inputs=[],exit_code=0)
(BASE/'native-verification.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report))
