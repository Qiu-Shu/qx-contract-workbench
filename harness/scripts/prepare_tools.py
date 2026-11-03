"""Install project-owned skills and append MCP entries without replacing settings."""
import json
import os
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MARKER = '# qunxing-web-desktop-tools-v1'


def install():
    backup = ROOT / '.local' / ('tools-backup-' + datetime.now().strftime('%Y%m%d-%H%M%S'))
    changed = []

    def update(target, data):
        before = target.read_bytes() if target.exists() else None
        if before == data:
            return
        if before is not None:
            saved = backup / target.relative_to(ROOT)
            saved.parent.mkdir(parents=True, exist_ok=True)
            saved.write_bytes(before)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(target.name + '.qx-tools-tmp')
        temporary.write_bytes(data)
        if target.exists() and target.read_bytes() != before:
            temporary.unlink()
            raise RuntimeError('File changed during preparation; preserved: ' + str(target))
        os.replace(temporary, target)
        changed.append(target.relative_to(ROOT).as_posix())

    # Preserve local edits on subsequent deployments rather than silently replacing them.
    for source in (ROOT / 'config/skills').rglob('*'):
        if not source.is_file() or source.name == 'sources.json':
            continue
        target = ROOT / 'workspace/.dsh/skills' / source.relative_to(ROOT / 'config/skills')
        if target.exists() and target.read_bytes() != source.read_bytes():
            raise RuntimeError('Skill has local edits: ' + str(target))
        update(target, source.read_bytes())

    instructions = ROOT / 'workspace/AGENTS.md'
    heading = '## 网页、桌面与报告呈现'
    addition = (ROOT / 'config/workspace-AGENTS.md').read_text(encoding='utf-8').split(heading, 1)[1]
    before = instructions.read_text(encoding='utf-8-sig')
    if heading not in before:
        update(instructions, (before.rstrip() + '\n\n' + heading + addition).encode('utf-8'))

    servers = [
        ('qx-bb-browser', 'bb_browser', 'D:/qx-contract-workbench-20261102/.venv/Scripts/python.exe', [str(ROOT/'bridge/browser.py')]),
        ('qx-scrapling', 'scrapling', 'C:/Users/Lenovo/.codex/tools/scrapling/venv/Scripts/scrapling.exe', ['mcp', '--executable-path', 'C:/Program Files/Google/Chrome/Application/chrome.exe']),
        ('qx-windows', 'windows', 'C:/Users/Lenovo/.codex/tools/windows-mcp/venv/Scripts/windows-mcp.exe', ['serve', '--transport', 'stdio']),
    ]
    entries = []
    for identity, name, command, args in servers:
        if not Path(command).is_file():
            raise RuntimeError('Required local tool missing: ' + command)
        entries.append({'id': identity, 'name': '@deepseek-ai/dsh-mcp-client', 'config': {
            'transport': 'stdio', 'serverName': name, 'command': command, 'args': args,
            'cwd': str(ROOT/'workspace'), 'env': {'PYTHONIOENCODING': 'utf-8'}, 'toolCallTimeoutMs': 120000}})
        if name == 'bb_browser':
            entries[-1]['config']['env']['QX_BROWSER_ADAPTER_VERSION'] = '1.1.1'
    block = '\n' + MARKER + '\n- insert:\n' + ''.join('    - ' + json.dumps(e, ensure_ascii=False) + '\n' for e in entries)
    for target in [ROOT/'config/cordis.patch.yml', ROOT/'.local/dsh-home/profiles/web/cordis.patch.yml']:
        before = target.read_text(encoding='utf-8-sig')
        if MARKER not in before:
            if any(e['id'] in before for e in entries):
                raise RuntimeError('MCP entries already customized; inspect before merging')
            update(target, (before.rstrip() + '\n' + block).encode('utf-8'))
    summary = {'changed': changed, 'backup': str(backup), 'servers': [e['config']['serverName'] for e in entries]}
    evidence = ROOT / 'docs/checks/web-tools'
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence/'installation.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'changedFiles': len(changed), 'backup': str(backup), 'servers': summary['servers']}))


if __name__ == '__main__':
    install()
