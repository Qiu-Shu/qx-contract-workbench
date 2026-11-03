"""Incrementally enable local legal tools; preserve existing profile and workspace text."""
from datetime import datetime
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
PYTHON = 'D:/qx-contract-workbench-20261102/.venv/Scripts/python.exe'
SKILLS = ('qx-client-reception', 'qx-contract-review', 'qx-case-work', 'qx-mock-hearing')
MARKER = '# qunxing-legal-workflows-v1'


def main():
    workspace = ROOT / 'workspace'
    patch = f'''\n{MARKER}
- insert:
    - id: qx-legal
      name: '@deepseek-ai/dsh-mcp-client'
      config:
        transport: stdio
        serverName: qx_legal
        command: {PYTHON}
        args:
          - {ROOT.as_posix()}/bridge/business_server.py
          - --workspace
          - {workspace.as_posix()}
        cwd: {workspace.as_posix()}
        env:
          PYTHONIOENCODING: utf-8
        toolCallTimeoutMs: 600000
'''
    active = ROOT / '.local/dsh-home/profiles/web/cordis.patch.yml'
    for destination in (ROOT / 'config/cordis.patch.yml', active):
        current = destination.read_text(encoding='utf-8-sig')
        if MARKER not in current:
            if destination == active:
                backup = ROOT / '.local/backups' / ('legal-profile-' + datetime.now().strftime('%Y%m%d-%H%M%S') + '.yml')
                backup.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(destination, backup)
            destination.write_text(current.rstrip() + '\n' + patch, encoding='utf-8')
    for skill in SKILLS:
        shutil.copytree(ROOT / 'config/skills' / skill, workspace / '.dsh/skills' / skill, dirs_exist_ok=True)
    template = (ROOT / 'config/workspace-AGENTS.md').read_text(encoding='utf-8')
    start = template.index('## 四项业务入口与连续办理')
    end = template.index('\n文档和图片优先', start)
    section = template[start:end]
    instructions = workspace / 'AGENTS.md'
    current = instructions.read_text(encoding='utf-8-sig')
    if '## 四项业务入口与连续办理' not in current:
        anchor = '\n文档和图片优先'
        if anchor not in current:
            raise RuntimeError('Workspace instructions changed; insert the legal section manually without replacing other sections.')
        current = current.replace(anchor, '\n' + section + '\n' + anchor, 1)
        instructions.write_text(current, encoding='utf-8')
    print('Legal MCP profile entry, four skills and scoped routing deployed; existing extensions preserved.')


if __name__ == '__main__':
    main()
