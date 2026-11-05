"""Build the one-time default-Skill upgrade manifest from recorded pre-change hashes.

Only project instruction files are inspected. No installed user data is read or changed.
"""
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parents[1]
CHECKS = ROOT / 'docs/checks/skills-quality'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def prepare():
    baseline = json.loads((CHECKS / 'baseline/report.json').read_text(encoding='utf-8'))['workspaces'][0]
    v1 = json.loads((CHECKS / 'after/report.json').read_text(encoding='utf-8'))['workspaces'][0]
    v1_rows = {row['name']: row for row in v1['rows']}
    route_file = ROOT / 'docs/checks/candidate-install/routes-changes.json'
    route_defaults = {}
    if route_file.exists():
        for change in json.loads(route_file.read_text(encoding='utf-8'))['changes']:
            if change['path'].startswith('workspace/'):
                relative = change['path'][len('workspace/'):]
                backup = ROOT / 'docs/checks/candidate-install/routes-before' / change['path']
                if digest(backup.read_bytes()) != change['beforeSha256']:
                    raise ValueError(f'Route backup mismatch: {relative}')
                route_defaults[relative] = change['beforeSha256']
    practice_defaults = {}
    practice_root = ROOT / 'docs/checks/practice-gaps/before'
    for change in json.loads((practice_root / 'manifest.json').read_text(encoding='utf-8')):
        if change['path'].startswith('workspace/'):
            if digest((practice_root / change['path']).read_bytes()) != change['beforeSha256']:
                raise ValueError(f"Practice backup mismatch: {change['path']}")
            practice_defaults[change['path'][len('workspace/'):]] = change['beforeSha256']
    if baseline['discovered'] != 185 or baseline['loaded'] != 185:
        raise ValueError('Expected the recorded 185-Skill baseline')
    released = ROOT / '.local/update-release-0.2.6/win-unpacked/resources/workbench/workspace-seed'
    entries = []
    for row in baseline['rows']:
        base = Path('.dsh/skills') / row['name']
        for child, previous in row['fileHashes'].items():
            relative = base / child
            current = ROOT / 'workspace' / relative
            if not current.is_file():
                raise ValueError(f'Existing Skill resource removed: {relative}')
            target_hash = digest(current.read_bytes())
            configured = ROOT / 'config/skills' / row['name'] / child
            if configured.is_file() and digest(configured.read_bytes()) != target_hash:
                raise ValueError(f'Config and workspace copies differ: {relative}')
            if target_hash == previous:
                continue
            known = {previous}
            known.add(v1_rows[row['name']]['fileHashes'][child])
            if relative.as_posix() in route_defaults:
                known.add(route_defaults[relative.as_posix()])
            if relative.as_posix() in practice_defaults:
                known.add(practice_defaults[relative.as_posix()])
            candidate = released / relative
            if candidate.is_file():
                known.add(digest(candidate.read_bytes()))
            known.discard(target_hash)
            entries.append({'path': relative.as_posix(), 'previousSha256': sorted(known), 'sha256': target_hash})
    resources = []
    for name in ['practice-context.md', 'source-verification.md', 'skill-status.md']:
        relative = Path('legal-library/workbench') / name
        contents = (ROOT / 'workspace' / relative).read_bytes()
        canonical = ROOT / 'config/skill-references' / name
        canonical.parent.mkdir(exist_ok=True)
        canonical.write_bytes(contents)
        resources.append({'path': relative.as_posix(), 'sha256': digest(contents)})
    manifest = {'version': 'skill-quality-v3', 'sourceBaseline': '2026-11-04:185-skills-and-reviewed-defaults-through-2026-11-05', 'resources': resources,
                'policy': 'Replace only known shipped defaults; preserve user edits and exact backups.',
                'files': entries}
    target = ROOT / 'config/skill-quality-upgrades.json'
    target.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'manifest': str(target), 'files': len(entries)}, ensure_ascii=False))


if __name__ == '__main__':
    prepare()
