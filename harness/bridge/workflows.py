"""Load authored legal methods without importing the legacy execution protocols."""
import hashlib
import json
from pathlib import Path


SKILLS = Path(__file__).resolve().parents[1] / 'config' / 'skills'
PACKAGED_SKILLS = Path(__file__).resolve().parents[1] / 'workspace-seed' / '.dsh' / 'skills'
VERSION = 'qx-legal-methods-v2'
_WORKFLOWS = {
    'reception': ('qx-client-reception', '客户接待与跟进',
                  ('legal-zh-clinic-client-intake', 'qx-case-work')),
    'contract': ('qx-contract-review', '合同审查',
                 ('legal-zh-commercial-nda-review', 'legal-zh-commercial-vendor-agreement-review',
                  'legal-zh-privacy-dpa-review')),
    'case': ('qx-case-work', '案件整理与文书',
             ('legal-zh-litigation-chronology', 'qx-evidence-analysis')),
    'hearing': ('qx-mock-hearing', '庭审演练',
                ('legal-zh-litigation-deposition-prep', 'qx-evidence-analysis')),
    'evidence': ('qx-evidence-analysis', '证据分析与实务摘要', ('qx-case-work',)),
}
_ALIASES = {'sales': 'reception', 'court': 'hearing'}
_ALIASES.update({value[0]: key for key, value in _WORKFLOWS.items()})


def workflow(name: str) -> dict:
    """Return one method and its provenance; all business answers remain natural text."""
    if not isinstance(name, str):
        raise ValueError('请提供工作方法名称。')
    selected = _ALIASES.get(name.strip(), name.strip())
    if selected not in _WORKFLOWS:
        raise ValueError('未知工作方法；可选 ' + '、'.join(_WORKFLOWS) + '。')
    skill, title, suggested = _WORKFLOWS[selected]
    directory = (SKILLS if SKILLS.is_dir() else PACKAGED_SKILLS) / skill
    try:
        method = (directory / 'references' / 'method.md').read_text(encoding='utf-8')
        provenance = json.loads((directory / 'references' / 'sources.json').read_text(encoding='utf-8'))
    except (OSError, ValueError) as error:
        raise ValueError(f'{title}的方法文件暂不可读取；可保留已完成的回答，待方法恢复后继续。') from error
    return {
        'name': selected, 'title': title, 'version': VERSION,
        'output_protocol': 'natural_language',
        'method': method, 'method_sha256': hashlib.sha256(method.encode('utf-8')).hexdigest(),
        'sources': provenance['sources'],
        'adaptation': provenance.get('adaptation', {}),
        'suggested_skills': list(suggested),
        'references': [f'.dsh/skills/{skill}/references/{path.name}'
                       for path in sorted((directory / 'references').glob('*.md'))
                       if path.name != 'method.md'],
    }
