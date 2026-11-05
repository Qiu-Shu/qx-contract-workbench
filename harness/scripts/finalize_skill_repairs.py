"""Close the reviewed 91-item repair batch; never changes original libraries."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs/checks/skills-repair'
FREEZE = ROOT / 'config/skill-repair-freeze.json'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def main():
    if FREEZE.exists():
        print('Reviewed batch already finalized; no changes.')
        return
    groups = {g: json.loads((OUT / f'group-{g}-changes.json').read_text(encoding='utf-8')) for g in 'abc'}
    reviews = {r['name']: r for g in 'abc' for r in json.loads((OUT / f'group-{g}-final-review.json').read_text(encoding='utf-8'))}
    rows = {r['name']: r for group in groups.values() for r in group}
    assert len(rows) == len(reviews) == 91 and rows.keys() == reviews.keys()
    disabled = {n for n, r in rows.items() if r['action'] == 'disable' or reviews[n]['finalStatus'] == 'disable-recommended'}
    dependency_reasons = {}
    while True:
        dependents = {n for n, r in rows.items() if n not in disabled and r.get('replacement') in disabled}
        if not dependents:
            break
        for n in dependents:
            dependency_reasons[n] = f"自身双题通过，但合并目标 {rows[n]['replacement']} 复测未通过并停用，不能保留通向停用目标的入口。"
        disabled.update(dependents)
    changes = []
    for name, row in rows.items():
        file = ROOT / 'workspace/.dsh/skills' / name / 'SKILL.md'
        contents = file.read_bytes()
        assert sha(contents) == row['afterSha256'], name
        if name in disabled and row['action'] != 'disable':
            backup = OUT / 'before-final-disable' / name / 'SKILL.md'
            backup.parent.mkdir(parents=True, exist_ok=True)
            if not backup.exists():
                backup.write_bytes(contents)
            reason = dependency_reasons.get(name, reviews[name]['reason'])
            fallback = 'qx-contract-review' if name.startswith(('chinese-legal-commercial', 'legal-zh-commercial-')) else 'qx-case-work'
            row.update(priorAction=row['action'], action='disable', reason=reason,
                       fallback=fallback, reviewedBodySha256=sha(contents))
            row.pop('replacement', None)
            text = f'''---
name: {name}
description: "Retired workbench entry; retained only for source traceability."
disable-model-invocation: true
user-invocable: false
---

<!-- workbench-skill-repair-v2 -->
<!-- workbench-skill-disabled-v2 -->

# 已停用的专业入口

{reason}

此入口不继续执行旧流程，也不通过原库绕过停用。当前业务可从 `{fallback}` 开始完成一般合同审查或案件材料整理；这不代表该核心入口已获得本专项能力认证。专项判断仍需依据材料和已核来源由律师审查。

原始中英文库和许可保留在 `legal-library/zh/` 与 `legal-library/en/`。状态及原因见 `legal-library/workbench/skill-status.md`。
'''
            file.write_text(text, encoding='utf-8')
            row['afterSha256'] = sha(file.read_bytes())
            changes.append(name)
        elif name not in disabled:
            assert reviews[name]['finalStatus'] == 'pass', name
    # Remove two explicit calls to retired helpers from otherwise passing workflows.
    route_edits = {
        'legal-zh-commercial-review': ('SaaS使用 `legal-zh-commercial-saas-msa-review`', 'SaaS继续由 `qx-contract-review` 按主协议、数据条款及附件审查'),
        'legal-zh-regulatory-comments': ('并转 legal-zh-regulatory-gap-surfacer', '并由 qx-case-work 整理已确认要求、材料状态和待办'),
    }
    for name, (old, new) in route_edits.items():
        assert name not in disabled
        file = ROOT / 'workspace/.dsh/skills' / name / 'SKILL.md'
        text = file.read_text(encoding='utf-8')
        assert old in text, name
        backup = OUT / 'before-route-fix' / name / 'SKILL.md'
        backup.parent.mkdir(parents=True, exist_ok=True)
        if not backup.exists():
            backup.write_bytes(file.read_bytes())
        rows[name]['evaluatedBodySha256'] = sha(file.read_bytes())
        file.write_text(text.replace(old, new), encoding='utf-8')
        rows[name]['afterSha256'] = sha(file.read_bytes())
        rows[name]['postEvaluationRouteChange'] = {'from': old, 'to': new, 'validation': 'Pending official-tool route verification; no new legal instructions.'}
    for g, group in groups.items():
        save(OUT / f'group-{g}-changes.json', group)
    save(OUT / 'final-disable-decisions.json', {'disabled': sorted(disabled), 'dependencyDecisions': dependency_reasons, 'newlyDisabled': changes})
    save(FREEZE, {'status': 'finalized', 'reviewed': 91, 'disabled': len(disabled), 'policy': 'One-off repair generators must not overwrite reviewed or disabled adapters.'})
    print(json.dumps({'reviewed': 91, 'disabled': len(disabled), 'active': 91-len(disabled), 'routeFixes': len(route_edits)}))


if __name__ == '__main__':
    main()
