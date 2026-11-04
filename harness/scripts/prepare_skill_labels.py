"""Apply the project label catalog to a pristine pnpm UI Skill patch directory.

Run pnpm patch first; commit the resulting patch with pnpm patch-commit.
Only presentation changes. Skill IDs, slash tokens and stored calls stay intact.
"""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]


def transform(source, labels):
    def replace(old, new):
        nonlocal source
        if source.count(old) != 1:
            raise ValueError(f'Expected one upstream UI fragment: {old[:90]}')
        source = source.replace(old, new)

    anchor = '\t\t//#region ../../util/workspace-path/src/file-address.ts'
    mapping = json.dumps(labels, ensure_ascii=False, indent=2)
    mapping = '\n'.join('\t\t' + line for line in mapping.splitlines())
    replace(anchor, '\t\t// Generated from config/skill-labels.zh-CN.json. Keep protocol IDs unchanged.\n'
            '\t\tconst qxSkillLabels = ' + mapping.lstrip() + ';\n'
            '\t\tconst qxSkillLabel = name => Object.hasOwn(qxSkillLabels, name) ? qxSkillLabels[name] : name;\n' + anchor)
    replace('const summary = model.state === "stopped" ? t("row.stopped") : model.errorSummary ?? model.name;',
            'const summary = model.state === "stopped" ? `${qxSkillLabel(model.name)} · ${t("row.stopped")}` : model.errorSummary ? `${qxSkillLabel(model.name)}：${model.errorSummary}` : qxSkillLabel(model.name);')
    replace('"data-state": model.state,', '"data-state": model.state,\n\t\t\t\t"data-skill-id": model.name,')
    replace('label: `/${node.data.name}`,', 'label: `/${qxSkillLabel(node.data.name)}`,')
    replace('return (0, _deepseek_ai_dsh_client_ui_primitives.rankByName)(skills, query).map((skill) => ({\n\t\t\t\t\t\tname: skill.name,',
            'return (0, _deepseek_ai_dsh_client_ui_primitives.rankByName)(skills.map(skill => ({name: `${qxSkillLabel(skill.name)} ${skill.name}`, skill})), query).map(({skill}) => ({\n\t\t\t\t\t\tname: skill.name,\n\t\t\t\t\t\tlabel: qxSkillLabel(skill.name),')
    for old, new in [('正在加载 skill', '正在加载技能'), ('skill 加载失败', '技能加载失败'), ('skill 加载已中止', '技能加载已中止')]:
        replace('"' + old + '"', '"' + new + '"')
    return source


if __name__ == '__main__':
    directory = Path(sys.argv[1]).resolve()
    target = directory / 'lib/client.js'
    catalog = json.loads((ROOT / 'config/skill-labels.zh-CN.json').read_text(encoding='utf-8'))
    original = target.read_text(encoding='utf-8')
    updated = transform(original, catalog['labels'])
    target.write_text(updated, encoding='utf-8', newline='\n')
    print(json.dumps({'labels': len(catalog['labels']), 'file': str(target)}, ensure_ascii=False))
