"""Replay raw-model errors at the actual save boundary; no model/network calls."""
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

root=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(root/'bridge'))
from test_employment_decisions import source_case
from employment_review import save_employment_review

scenarios=[
    ('D','试用条件','甲方与乙方此前未就同一岗位约定过试用期。'),
    ('H','考勤核实通知','公司人力资源部在核对考勤记录时发现，您在考勤系统中无出勤记录。'),
    ('J','竞业解除核对函','甲员工未就解除作出同意表示。'),
]
rows=[]
compiled='--compiled' in sys.argv
intents={'D':'probation_clause','H':'attendance_inquiry','J':'noncompete_inquiry'}
with TemporaryDirectory(prefix='employment-boundary-') as temp:
    for code,topic,claim in scenarios:
        raw=json.loads((Path(__file__).parent/'model/retest4'/f'candidate-{code}.json').read_text(encoding='utf-8'))
        cases,cid,ref=source_case(Path(temp)/code,raw['prompt'])
        result=save_employment_review(cases,cid,'hiring' if code=='D' else 'termination' if code=='H' else 'dispute',
            [dict(topic=topic,fact='来源见引用',source='文字题面',basis='适用条件待核',risk='待核',action=claim,citations=[ref],
                  **({'drafts':[intents[code]]} if compiled else {}))])
        body=cases.read_note(cid,result['id'])['content']
        rows.append(dict(case=code,source_prompt=raw['prompt'],candidate_claim=claim,
            citation_matched=all(r['status']=='matched' for r in result['citations']),
            unsupported_claim_persisted=claim in body,review_status=result['review_status']))
outputs=[arg for arg in sys.argv[1:] if arg!='--compiled']
output=Path(outputs[0]) if outputs else Path(__file__).with_name('first-principles-compiled-probe.json' if compiled else 'first-principles-probe.json')
output.write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps([{k:v for k,v in row.items() if k not in ('source_prompt','candidate_claim')} for row in rows]))
assert not any(row['unsupported_claim_persisted'] for row in rows), 'Matched source does not constrain new assertions in draft action'
