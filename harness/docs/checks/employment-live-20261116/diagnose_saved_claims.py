"""Offline diagnosis: replay unsupported prose through the actual save boundary.

This intentionally records observed gaps, not a regression that endorses them.
Only synthetic data in an automatically removed temporary workspace is used.
"""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from business_store import CaseStore
from reader import parse
from employment_review import save_employment_review


def main():
    source = ('独立虚构材料。公司提供考勤摘录，员工称已申请产检假。'
              '具体考勤条目本次未展示，请假审批记录未提供。'
              '陈述媒介未说明。协商记录本次未提供。')
    probes = [
        ('attendance-content', '公司考勤记录显示上述期间存在未出勤记录。'),
        ('source-medium', '本轮为员工口头陈述。'),
        ('existing-negative-guard', '公司没有协商记录。'),
    ]
    results = []
    with TemporaryDirectory(prefix='qx-employment-diagnosis-') as temporary:
        root = Path(temporary)
        cases = CaseStore(root)
        cid = cases.create('独立虚构语义边界探针')['id']
        (root/'source.txt').write_text(source, encoding='utf-8')
        cases.store.register('source.txt')
        parse(cases.store, 'source.txt')
        cases.link_materials(cid, ['source.txt'])
        for name, claim in probes:
            result = save_employment_review(cases, cid, 'termination', [{
                'topic':'事实状态诊断', 'fact':claim,
                'basis':'诊断输入，不作法律结论', 'source':'source.txt合成材料',
                'risk':'仅检查保存边界是否改变该句', 'action':'内部诊断，不发送',
                'citations':[{'path':'source.txt','quote':source}],
            }], request_id='diagnosis-'+name)
            note = cases.read_note(cid, result['id'])
            results.append({'id':name, 'inputClaim':claim,
                'claimPersists':('事实/陈述：'+claim) in note['content'],
                'citationStatus':[r['status'] for r in note['citations']],
                'reviewStatus':note['review_status'],
                'changes':result['review_changes'],
                'storedFact':next(line for line in note['content'].splitlines() if line.startswith('事实/陈述：'))})
    output = {'scope':'Offline actual save/readback, synthetic data only; not legal certification',
              'source':source, 'results':results}
    destination = Path(__file__).with_name('saved-claim-diagnosis.json')
    destination.write_text(json.dumps(output, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
