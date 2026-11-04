"""Build a clean redistributable from explicit code/runtime sources, never user state."""
import argparse
import json
import os
from pathlib import Path
import shutil
import sys
import hashlib
import yaml

ROOT=Path(__file__).resolve().parents[1]
LEGACY=Path('D:/qx-contract-workbench-20261102')
TOOLS=Path('C:/Users/Lenovo/.codex/tools')
RUNTIME=Path('C:/Users/Lenovo/.cache/codex-runtimes/codex-primary-runtime/dependencies')
IGNORED={'__pycache__','.git','.codegraph','.pytest_cache','.local','.env','node_modules'}

def copytree(source,target,extra=()):
    # pnpm paths exceed Win32 MAX_PATH; the extended form preserves all assets.
    source='\\\\?\\'+str(source.absolute())
    target='\\\\?\\'+str(target.absolute())
    shutil.copytree(source,target,dirs_exist_ok=True,ignore=shutil.ignore_patterns(*IGNORED,*extra,'*.pyc','*.pyo'))

def package_source(start,name):
    for parent in [start,*start.parents]:
        candidate=parent/'node_modules'/name
        if (candidate/'package.json').is_file():return candidate.resolve()
    return None

def bundle_node(entry,destination):
    """Hoist equal package versions; nest conflicts, preserving Node lookup semantics."""
    root_modules=destination/'node_modules'
    installed={}
    queue=[]
    def add(source,name,parent):
        source=source.resolve()
        meta=json.loads((source/'package.json').read_text(encoding='utf-8'))
        identity=(meta['name'],meta.get('version'))
        shadowed=False
        for ancestor in [parent,*parent.parents]:
            candidate=ancestor/'node_modules'/name
            if candidate in installed:
                if installed[candidate]==identity:return
                shadowed=True
                break
            if ancestor==destination:break
        target=parent/'node_modules'/name if shadowed else root_modules/name
        if target in installed and installed[target]!=identity:target=parent/'node_modules'/name
        if target in installed:
            if installed[target]!=identity:raise RuntimeError('Dependency conflict: '+name)
            return
        installed[target]=identity
        copytree(source,target)
        queue.append((source,target,meta))
    for source,name in entry:add(source,name,destination)
    index=0
    while index<len(queue):
        source,target,meta=queue[index];index+=1
        deps={**meta.get('dependencies',{}),**meta.get('optionalDependencies',{}),**meta.get('peerDependencies',{})}
        for name in deps:
            found=package_source(source,name)
            if found:add(found,name,target)
            elif name in meta.get('dependencies',{}) and name not in meta.get('optionalDependencies',{}):
                raise RuntimeError(f'Missing dependency {meta["name"]}: {name}')
    return len(installed)

def python_runtime(base,site,target):
    target.mkdir(parents=True,exist_ok=True)
    for item in base.iterdir():
        if item.is_file() and (item.suffix in {'.exe','.dll','.zip','.txt'}):shutil.copy2(item,target/item.name)
    for folder in ['DLLs','Lib','tcl']:
        if (base/folder).exists():copytree(base/folder,target/folder,('site-packages',))
    copytree(site,target/'Lib/site-packages',('pip','setuptools','wheel','pytest','_pytest'))
    # Development editable-install hooks contain machine paths; actual sources ship below.
    for file in (target/'Lib/site-packages').glob('__editable__*'):
        if file.is_file():file.unlink()
    for file in (target/'Lib/site-packages').glob('*.pth'):
        if 'D:\\' in file.read_text(errors='replace') or 'D:/' in file.read_text(errors='replace'):file.unlink()

def portable_config():
    value=yaml.safe_load((ROOT/'config/cordis.patch.yml').read_text(encoding='utf-8-sig'))
    def walk(item):
        if isinstance(item,str):
            item=item.replace('\\','/')
            item=item.replace(str(ROOT).replace('\\','/')+'/workspace','@DATA@/workspace')
            item=item.replace(str(ROOT).replace('\\','/')+'/.local','@DATA@/.local')
            item=item.replace(str(ROOT).replace('\\','/'),'@APP@')
            return item.replace(str(LEGACY).replace('\\','/')+'/.venv/Scripts/python.exe','@APP@/runtime/python/python.exe')
        if isinstance(item,list):return [walk(v) for v in item]
        if isinstance(item,dict):return {k:walk(v) for k,v in item.items()}
        return item
    value=walk(value)
    for block in value:
        for plugin in block.get('insert',[]):
            config=plugin.get('config',{})
            if plugin['id']=='qx-legal-search':
                plugin['name']='@DATA@/.local/legal-search-runtime/plugins/legal-search/index.mjs'
                config['python']='@APP@/runtime/scrapling/python.exe'
            if plugin['id']=='qx-scrapling':
                config['command']='@APP@/runtime/scrapling/python.exe'
                config['args']=['@APP@/python-tool.py','scrapling','mcp']
            if plugin['id']=='qx-windows':
                config['command']='@APP@/runtime/windows/python.exe'
                config['args']=['@APP@/python-tool.py','windows','serve','--transport','stdio']
            if plugin['id']=='qx-bb-browser':
                config.setdefault('env',{}).update(BB_BROWSER_NODE='@APP@/runtime/node.exe',BB_BROWSER_CLI='@APP@/browser/node_modules/bb-browser/dist/cli.js')
            if config.get('command','').endswith('python.exe'):
                config.setdefault('env',{}).update(PYTHONPATH='@APP@/legacy/src',QX_LEGACY_ROOT='@APP@/legacy',PYTHONIOENCODING='utf-8')
    return value

def verify_office_engine(payload):
    engine=payload/'node_modules/@deepseek-ai/libreoffice-kit-win32-x64'
    try:
        meta=json.loads((engine/'package.json').read_text(encoding='utf-8'))
        manifest=json.loads((engine/'prebuilds.json').read_text(encoding='utf-8'))
        if meta['name']!='@deepseek-ai/libreoffice-kit-win32-x64' or meta['version']!='0.1.5' or manifest['version']!=meta['version'] or manifest['status']!='built' or manifest['platform']!='win32-x64' or not manifest['files']:
            raise ValueError('incompatible engine')
        for relative,digest in manifest['files'].items():
            file=(engine/relative).resolve()
            if not file.is_relative_to(engine.resolve()) or hashlib.sha256(file.read_bytes()).hexdigest()!=digest:
                raise ValueError('incomplete engine')
    except (OSError,ValueError,KeyError) as error:
        raise RuntimeError('Office preview engine is missing or incomplete; run pnpm install before packaging.') from error

def bundle_office_engine(payload):
    kit=package_source((ROOT/'node_modules/@deepseek-ai/dsh').resolve(),'@deepseek-ai/libreoffice-kit')
    engine=package_source(kit,'@deepseek-ai/libreoffice-kit-win32-x64') if kit else None
    if not engine:raise RuntimeError('Office preview engine is missing; run pnpm install before packaging.')
    bundle_node([(engine,'@deepseek-ai/libreoffice-kit-win32-x64')],payload)
    verify_office_engine(payload)

def stage(destination,version='0.2.1'):
    if destination.exists():raise RuntimeError('Use a new staging directory to prevent stale files: '+str(destination))
    payload=destination/'workbench';app=destination/'app'
    payload.mkdir(parents=True);app.mkdir()
    (payload/'desktop-runner').mkdir()
    for name in ['installed-host.cjs','installed-runtime.cjs','installed-migrations.cjs','case-memory-runtime.cjs','host-recovery.cjs','stop-installed.cjs']:shutil.copy2(ROOT/'desktop'/name,payload/'desktop-runner'/name)
    for name in ['main.cjs','preload.cjs','unavailable.html','installed.cjs','installed-runtime.cjs','installed-migrations.cjs','case-memory-runtime.cjs','host-recovery.cjs','model-credentials.cjs','setup-service.cjs','setup-preload.cjs','setup.html','setup.css','setup.js','updates.cjs','update-download.cjs','update-integrity.cjs','update-config.json']:
        shutil.copy2(ROOT/'desktop'/name,app/name)
    (app/'package.json').write_text(json.dumps({'name':'qunxing-harness-desktop','version':version,'private':True,'description':'AI师兄法律助手平台','author':'AI师兄法律助手平台项目','main':'installed.cjs','dependencies':{'electron-updater':'6.8.11'}}),encoding='utf-8')
    bundle_node([(ROOT/'node_modules/electron-updater','electron-updater')],app)
    for folder in ['bridge','plugins/account','plugins/knowledge','plugins/privacy','plugins/session-title','plugins/legal-search','plugins/case-memory','desktop/integration']:
        copytree(ROOT/folder,payload/folder,('test','tests','check*.mjs','test_*.py','selfcheck.py','ui-check.py','practice_eval_session.py'))
    # Only active WeChat runtime assets; exclude development VSIXs, snapshots and tests.
    copytree(ROOT/'plugins/wechat',payload/'plugins/wechat',('*.vsix','test','tests','docs','scripts','.github','vscode-extension'))
    reader=payload/'bridge/reader.py'
    reader.write_text(reader.read_text(encoding='utf-8').replace("Path('D:/qx-contract-workbench-20261102')","Path(os.environ['QX_LEGACY_ROOT'])"),encoding='utf-8')
    copytree(LEGACY/'src/cn_contract',payload/'legacy/src/cn_contract')
    (payload/'legacy/config').mkdir(parents=True)
    shutil.copy2(LEGACY/'config/defaults.json',payload/'legacy/config/defaults.json')
    for name in ['LICENSE','LICENSE.txt']:
        if (LEGACY/name).exists():shutil.copy2(LEGACY/name,payload/'legacy'/name)
    print('Bundling Harness dependency graph',flush=True)
    count=bundle_node([(ROOT/'node_modules/@deepseek-ai/dsh','@deepseek-ai/dsh'),(ROOT/'desktop/integration','@qunxing/desktop-session')],payload)
    verify_office_engine(payload)
    print(f'Bundled {count} Node packages',flush=True)
    bundle_node([(TOOLS/'bb-browser/node_modules/bb-browser','bb-browser')],payload/'browser')
    (payload/'runtime').mkdir(exist_ok=True)
    shutil.copy2(RUNTIME/'node/bin/node.exe',payload/'runtime/node.exe')
    shutil.copy2(ROOT/'packaging/LICENSE.node.txt',payload/'runtime/LICENSE.node.txt')
    print('Bundling portable Python runtimes',flush=True)
    python_runtime(RUNTIME/'python',LEGACY/'.venv/Lib/site-packages',payload/'runtime/python')
    python_runtime(RUNTIME/'python',TOOLS/'scrapling/venv/Lib/site-packages',payload/'runtime/scrapling')
    python_runtime(Path('C:/Users/Lenovo/AppData/Roaming/uv/python/cpython-3.14-windows-x86_64-none'),TOOLS/'windows-mcp/venv/Lib/site-packages',payload/'runtime/windows')
    shutil.copy2(ROOT/'packaging/python-tool.py',payload/'python-tool.py')
    # This seed contains code/library sources only. Never copy the workspace root.
    seed=payload/'workspace-seed'
    copytree(ROOT/'workspace/legal-library',seed/'legal-library')
    copytree(ROOT/'config/skill-references',seed/'legal-library/workbench')
    copytree(ROOT/'workspace/.dsh/skills',seed/'.dsh/skills')
    copytree(ROOT/'config/skills',seed/'.dsh/skills')
    instructions=(ROOT/'config/workspace-AGENTS.md').read_text(encoding='utf-8').replace(str(RUNTIME/'node/bin/node.exe').replace('\\','/'),'@APP@/runtime/node.exe')
    (seed/'AGENTS.md').write_text(instructions,encoding='utf-8')
    (payload/'config').mkdir()
    shutil.copy2(ROOT/'packaging/case-memory-requirements.lock',payload/'config/case-memory-requirements.lock')
    copytree(ROOT/'config/templates',payload/'config/templates')
    shutil.copy2(ROOT/'packaging/contract-0.2.0-defaults.json',payload/'config/contract-0.2.0-defaults.json')
    shutil.copy2(ROOT/'config/skill-quality-upgrades.json',payload/'config/skill-quality-upgrades.json')
    (payload/'config/portable.json').write_text(json.dumps(portable_config(),ensure_ascii=False,indent=2),encoding='utf-8')
    pkg=json.loads((ROOT/'.local/dsh-home/profiles/web/package.json').read_text(encoding='utf-8-sig'))
    pkg['dependencies']={'@qunxing/desktop-session':'0.1.0'}
    (payload/'config/profile-package.json').write_text(json.dumps(pkg),encoding='utf-8')
    shutil.copy2(ROOT/'.local/dsh-home/profiles/web/cordis.yml',payload/'config/profile-cordis.yml')
    print(json.dumps({'stage':str(destination),'nodePackages':count}),flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('destination',type=Path);parser.add_argument('--version',default='0.2.1')
    args=parser.parse_args();stage(args.destination.resolve(),args.version)
