"""Apply reviewed workbench lifecycle metadata without deleting original libraries."""
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs/checks/skills-repair'


def prepare():
    rows = sum((json.loads((OUT / f'group-{g}-changes.json').read_text(encoding='utf-8')) for g in 'abc'), [])
    assert len(rows) == len({r['name'] for r in rows}) == 91
    expected = {r['name'] for r in json.loads((OUT / 'baseline-decisions.json').read_text(encoding='utf-8'))['decisions'] if r['modelResult'] != 'pass'}
    assert {r['name'] for r in rows} == expected
    dependency_file = OUT / 'dependency-changes.json'
    dependencies = json.loads(dependency_file.read_text(encoding='utf-8')) if dependency_file.exists() else []
    assert not expected.intersection(r['name'] for r in dependencies)
    rows += dependencies
    for row in rows:
        file = ROOT / 'workspace/.dsh/skills' / row['name'] / 'SKILL.md'
        assert hashlib.sha256(file.read_bytes()).hexdigest() == row['afterSha256'], row['name']
        text = file.read_text(encoding='utf-8')
        assert '<!-- workbench-skill-repair-v2 -->' in text
        if row['action'] == 'disable':
            assert re.search(r'^disable-model-invocation:\s*true$', text, re.M)
            assert re.search(r'^user-invocable:\s*false$', text, re.M)
    policy = {'version': 2, 'originalBatchCount': 91, 'dependencyCount': len(dependencies), 'skills': rows, 'scope': '91 reviewed workbench skills plus dependent aliases whose targets were retired.'}
    (ROOT / 'config/skill-lifecycle.json').write_text(json.dumps(policy, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    disabled = {r['name']: r for r in rows if r['action'] == 'disable'}
    lines = ['# Skill 调用状态', '', '此表是工作台适配决策，不改变原始法律资料。停用条目不进入自动技能目录，原名称仅供迁移和查阅来源；不能加载旧原文绕过停用并声称执行了已停用流程。', '',
             '用户明确要查阅历史模板时可把原文件作为参考资料说明，不能把教学、旧插件或未验证行为改名冒充当前实务能力。普通办案继续使用四项主业务，按需要加载仍可调用的专业技能。', '',
             '| 停用入口 | 原因 | 一般业务去向（非专项替代认证） |', '|---|---|---|']
    for row in disabled.values():
        lines.append(f"| {row['name']} | {row['reason'].replace('|', '／')} | {row.get('fallback', '四项主业务；原文仅作参考')} |")
    lines.extend(['', '## 合并与替代', '', '| 原入口 | 去向或共享流程 |', '|---|---|'])
    for row in rows:
        if row['action'] in ('merge', 'replace'):
            lines.append(f"| {row['name']} | {str(row.get('replacement') or row['reason']).replace('|', '／')} |")
    body = '\n'.join(lines) + '\n'
    for folder in ['config/skill-references', 'workspace/legal-library/workbench']:
        (ROOT / folder / 'skill-status.md').write_text(body, encoding='utf-8')
    # Domain menus must not continue instructing the model to load retired children.
    routes = []
    for file in sorted((ROOT / 'workspace/.dsh/skills').glob('chinese-legal-*/SKILL.md')):
        if file.parent.name in disabled:
            continue
        old = file.read_text(encoding='utf-8')
        updated = []
        for line in old.splitlines(keepends=True):
            if re.match(r'^-\s+`[a-z0-9-]+`', line) and any(f'`{name}`' in line for name in disabled):
                continue
            updated.append(line)
        text = ''.join(updated)
        if text != old:
            backup = OUT / 'route-before' / file.parent.name / 'SKILL.md'
            backup.parent.mkdir(parents=True, exist_ok=True)
            if not backup.exists():
                backup.write_bytes(file.read_bytes())
            file.write_text(text, encoding='utf-8')
            routes.append(file.relative_to(ROOT).as_posix())
    if routes:
        record = OUT / 'route-changes.json'
        previous = json.loads(record.read_text(encoding='utf-8')) if record.exists() else []
        record.write_text(json.dumps(sorted(set(previous + routes)), ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'reviewed': len(rows), 'disabled': len(disabled), 'domainRoutesAdjusted': len(routes)}))


if __name__ == '__main__':
    prepare()
