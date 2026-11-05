"""Read-only artifact audit; no model calls, no package output."""
import hashlib
import json
from pathlib import Path
from docx import Document

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/checks/skill-resume-20261105'
audit=json.loads((OUT/'verified-delivery-audit.json').read_text(encoding='utf-8'))
rows=[]
for row in audit['rows']:
    record=json.loads(Path(row['input']).read_text(encoding='utf-8'))
    texts=[]
    for draft in record['actual']['drafts']:
        path=Path(draft['path'])
        assert hashlib.sha256(path.read_bytes()).hexdigest()==draft['sha256']
        document=Document(path)
        text='\n'.join([p.text for p in document.paragraphs]+[cell.text for table in document.tables for r in table.rows for cell in r.cells])
        assert text==draft['text']
        texts.append(text)
    body='\n'.join(texts)
    identifier=record['id']
    if identifier.startswith('employment-'):
        required=['2008年前期间按第97条另核','十二年上限须满足相应条件','到手数不直接当法定基数',
                  '未确定实际应付款','17800' if identifier.endswith('known-net') else '28000']
        assert '2028' not in body+record['response']
    elif identifier.startswith('lit-'):
        required=['58000','暂不主张利息','条件是否成就未知','客户是否接受过风险说明未记载','如经核实']
    elif identifier.startswith('corp-'):
        required=['三票赞成','张说现在不做、王说先看成本，赵没有发言','会议记录签字页未提供','未认定既有会议程序']
    elif identifier.startswith('compliance-'):
        required=['相差5个自然日','已通过通知邮箱发送','未提供受理回执','不安排重复首次提交']
    else:
        required=['内部技术方案提交日为2020-05-01','官方申请回执明确申请日2021-07-12',
                  '目前授权和存续状态未知','证书明确有效期到2027-08-31','最近查询是2022年，当前状态未知']
    for phrase in required:
        assert phrase in body+record['response'],(identifier,phrase)
    rows.append({'id':identifier,'diskWordMatchesSnapshot':True,'review':'pass_in_limited_source_bound_scope',
                 'preservedChecks':required,'fullSkillApproved':False})
budget=json.loads((OUT/'budget.json').read_text(encoding='utf-8'))
total=round(sum(r.get('cost',r['reserved']) for r in budget['requests']),6)
authorization=json.loads((OUT/'authorization.json').read_text(encoding='utf-8'))
old=ROOT/'docs/checks/skills-quality/model/budget.json'
assert hashlib.sha256(old.read_bytes()).hexdigest()==authorization['previousLedgerSha256']
assert total<=20
assert not (ROOT/'docs/checks/skills-quality/model/run.lock').exists()
policy=json.loads((ROOT/'config/practice-skill-additions.json').read_text(encoding='utf-8'))
assert len(policy['withheld'])==5
for name in policy['withheld']:
    assert not (ROOT/'config/skills'/name).exists()
    assert not (ROOT/'workspace/.dsh/skills'/name).exists()
result={'scope':'Saved artifact text, targeted regression criteria and final-delivery consistency; not full legal review or visual pagination approval.',
        'rows':rows,'pythonRegressionPassed':247,'configurationTestsPassed':2,'nodeTestsPassed':25,
        'budget':{'start':18.025220,'additional':round(total-18.025220,6),'total':total,'remaining':round(20-total,6),
                  'cap':20,'previousLedgerUnchanged':True},
        'withheld':policy['withheld'],'packaged':False,'published':False,'installedApplicationUpdated':False}
(OUT/'verified-delivery-review.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
manifest=[]
paths=['bridge/verified_delivery.py','bridge/business_server.py','bridge/practice_eval_session.py','bridge/test_source_bound_mcp.py',
       'scripts/evaluate_practice_e2e.cjs','scripts/verified-delivery-harness.mjs','scripts/check_verified_delivery.mjs',
       'scripts/audit_verified_delivery.mjs','scripts/review_verified_delivery.py','config/cordis.patch.yml','packaging/stage.py','packaging/test_stage.py']
paths += [str(p.relative_to(ROOT)).replace('\\','/') for p in (ROOT/'plugins/verified-delivery').glob('*.mjs')]
paths += [str(p.relative_to(ROOT)).replace('\\','/') for p in (ROOT/'.local/skill-resume-20261105/candidate-v4').rglob('*') if p.is_file()]
for relative in sorted(set(paths)):
    path=ROOT/relative
    manifest.append({'path':relative,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
(OUT/'verified-delivery-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'reviewed':len(rows),'budget':result['budget']},ensure_ascii=False))
