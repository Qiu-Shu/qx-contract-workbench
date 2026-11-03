"""Apply only the first-content naming override to the existing local profile."""
from datetime import datetime
from pathlib import Path
import json
import shutil
import yaml

ROOT = Path(__file__).resolve().parents[1]


def main():
    template = yaml.safe_load((ROOT / 'config/cordis.patch.yml').read_text(encoding='utf-8-sig'))
    entry = next(plugin for row in template for plugin in row.get('insert', []) if plugin.get('id') == 'qx-first-content-title')
    patches = [{'id': 'session-title-llm', 'disabled': True}, {'insert': [entry]}]
    target = ROOT / '.local/dsh-home/profiles/web/cordis.patch.yml'
    original = target.read_text(encoding='utf-8-sig')
    rows = yaml.safe_load(original)
    existing = [row for row in rows if row.get('id') == 'session-title-llm']
    if existing:
        if existing == [patches[0]] and any(entry in row.get('insert', []) for row in rows):
            print('First-content naming override already configured.')
            return
        raise RuntimeError('Existing title override differs; preserve it and inspect before replacing.')
    backup = ROOT / '.local/backups' / ('session-title-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f') + '.yml')
    backup.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(target, backup)
    if target.read_text(encoding='utf-8-sig') != original:
        raise RuntimeError('Profile changed concurrently; retry against the current profile.')
    with target.open('a', encoding='utf-8') as stream:
        stream.write('\n# qunxing-first-content-title-v1\n' + ''.join('- ' + json.dumps(patch, ensure_ascii=False) + '\n' for patch in patches))
    print('First-content naming override added; existing profile entries preserved.')


if __name__ == '__main__':
    main()
