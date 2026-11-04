"""Refresh only distributable application code after coordinated parallel changes."""
from pathlib import Path
import json
import shutil
import sys
import re
from stage import ROOT,RUNTIME,copytree,portable_config,bundle_node,package_source,bundle_office_engine
import yaml

stage=Path(sys.argv[1]).resolve()
assert stage.is_relative_to(ROOT/'.local') and (stage/'workbench/runtime/node.exe').is_file()
payload=stage/'workbench'
bundle_office_engine(payload)
if len(sys.argv)>2:
    version=sys.argv[2]
    assert re.fullmatch(r'\d+\.\d+\.\d+',version)
    package=stage/'app/package.json';metadata=json.loads(package.read_text(encoding='utf-8'));metadata['version']=version
    package.write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding='utf-8')
shutil.copy2(ROOT/'packaging/LICENSE.node.txt',payload/'runtime/LICENSE.node.txt')
(payload/'desktop-runner').mkdir(exist_ok=True)
for name in ['installed-host.cjs','installed-runtime.cjs','installed-migrations.cjs','host-recovery.cjs','stop-installed.cjs']:shutil.copy2(ROOT/'desktop'/name,payload/'desktop-runner'/name)
shutil.copy2(ROOT/'desktop/installed-migrations.cjs',stage/'app/installed-migrations.cjs')
for file in (stage/'app').iterdir():
    source=ROOT/'desktop'/file.name
    if source.is_file():shutil.copy2(source,file)
for name in ['updates.cjs','update-download.cjs','update-integrity.cjs','update-config.json','host-recovery.cjs']:
    shutil.copy2(ROOT/'desktop'/name,stage/'app'/name)
package=stage/'app/package.json';metadata=json.loads(package.read_text(encoding='utf-8'))
metadata.setdefault('dependencies',{})['electron-updater']='6.8.11'
package.write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding='utf-8')
bundle_node([(ROOT/'node_modules/electron-updater','electron-updater')],stage/'app')
# Refresh managed UI patches too; an existing stage otherwise keeps old Skill labels.
patched=yaml.safe_load((ROOT/'pnpm-workspace.yaml').read_text(encoding='utf-8'))['patchedDependencies']
for spec in patched:
    name=spec.rsplit('@',1)[0]
    source=package_source((ROOT/'node_modules/@deepseek-ai/dsh').resolve(),name)
    if source is None:raise RuntimeError('Missing patched dependency: '+name)
    copytree(source,payload/'node_modules'/name)
for folder in ['bridge','plugins/account','plugins/knowledge','plugins/privacy','plugins/session-title','desktop/integration']:
    copytree(ROOT/folder,payload/folder,('test','tests','check*.mjs','test_*.py','selfcheck.py'))
copytree(ROOT/'plugins/wechat',payload/'plugins/wechat',('*.vsix','test','tests','docs','scripts','.github','vscode-extension'))
copytree(ROOT/'desktop/integration',payload/'node_modules/@qunxing/desktop-session')
reader=payload/'bridge/reader.py'
reader.write_text(reader.read_text(encoding='utf-8').replace("Path('D:/qx-contract-workbench-20261102')","Path(os.environ['QX_LEGACY_ROOT'])"),encoding='utf-8')
copytree(ROOT/'workspace/.dsh/skills',payload/'workspace-seed/.dsh/skills')
copytree(ROOT/'config/skills',payload/'workspace-seed/.dsh/skills')
copytree(ROOT/'config/templates',payload/'config/templates')
shutil.copy2(ROOT/'packaging/contract-0.2.0-defaults.json',payload/'config/contract-0.2.0-defaults.json')
instructions=(ROOT/'config/workspace-AGENTS.md').read_text(encoding='utf-8').replace(str(RUNTIME/'node/bin/node.exe').replace('\\','/'),'@APP@/runtime/node.exe')
(payload/'workspace-seed/AGENTS.md').write_text(instructions,encoding='utf-8')
(payload/'config/portable.json').write_text(json.dumps(portable_config(),ensure_ascii=False,indent=2),encoding='utf-8')
print('Distributable sources refreshed; user state excluded.')
