from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,subprocess
root=Path.cwd();out=root/'.local/jev-confirm-20261020'
def inputs():
    paths=list((root/'desktop').glob('*'))+list((root/'desktop/tests').glob('*.test.cjs'))
    return {p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
            for p in paths if p.is_file() and p.suffix in ('.cjs','.js','.html','.css','.json')}
before=inputs();args=['node','--test','desktop/tests/*.test.cjs']
with (out/'node-all.log').open('wb') as log:
    code=subprocess.run(args,stdout=log,stderr=subprocess.STDOUT).returncode
after=inputs();report={'command':args,'exit_code':code,'utc':datetime.now(timezone.utc).isoformat(),
                      'before':before,'after':after,'stable':before==after}
(out/'node-all.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps({'exit_code':code,'stable':before==after,'inputs':len(before)}))
print('\n'.join((out/'node-all.log').read_text('utf-8').splitlines()[-9:]))
raise SystemExit(code or (0 if before==after else 2))
