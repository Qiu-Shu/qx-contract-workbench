"""Independent zero-model replay of two paid traces after LIVE-1/2/3 fixes."""
import asyncio
from copy import deepcopy
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
from tempfile import TemporaryDirectory

HERE = Path(__file__).resolve().parent
HARNESS = HERE.parents[2]
sys.path.insert(0, str(HARNESS / 'bridge'))
from check_business_mcp import client, call
from docx import Document


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


async def replay(name, workspace):
    trace_path = HERE / 'e2e/attribution-final' / (name + '.json')
    trace = json.loads(trace_path.read_text(encoding='utf-8'))
    captured = [c for rd in trace['rounds'] for c in rd.get('toolResults', [])
                if c['name'] == 'save_employment_review']
    successful = [c for c in captured if not c['result']['is_error']]
    assert len(successful) == 1, 'Review every successful revision'
    original = json.loads(successful[0]['arguments'])
    source = workspace / '合成材料.txt'
    source.write_text(trace['scenario']['material'], encoding='utf-8')
    source_digest = digest(source)
    assert source_digest == trace['actual']['source_sha256']
    async with client('server.py', workspace) as materials:
        await call(materials, 'import_material', path=source.name)
        await call(materials, 'parse_material', path=source.name)
    messages = [dict(role='user', content=trace['scenario']['prompt'])]
    async with client('business_server.py', workspace) as legal:
        cid = (await call(legal, 'create_case', title='独立候选重放-' + name))['id']
        await call(legal, 'link_case_materials', case_id=cid, paths=[source.name])
        material = await call(legal, 'read_case_material', case_id=cid, path=source.name)
        assert material['sha256'] == source_digest
        failed_replays = []
        for c in captured:
            args = json.loads(c['arguments'])
            args['case_id'] = cid
            if c['result']['is_error']:
                failed = await legal.call_tool('save_employment_review', args)
                assert failed.is_error, 'Original schema failure must remain rejected'
                state = await call(legal, 'get_case', case_id=cid)
                assert not state['notes'], 'Failed validation must not persist partial notes'
                failed_replays.append(dict(expected_error=True, rejected=True, notes_created=0,
                                           original_arguments_unchanged={k:v for k,v in args.items() if k!='case_id'} == {k:v for k,v in json.loads(c['arguments']).items() if k!='case_id'}))
            else:
                saved = await call(legal, 'save_employment_review', **args)
        pages, start = [], 0
        while True:
            note = await call(legal, 'read_case_note', case_id=cid, note_id=saved['id'], start=start, limit=16000)
            pages.append(note['content'])
            if note['next_start'] is None:
                break
            start = note['next_start']
        body = ''.join(pages)
        export_args = dict(case_id=cid, note_ids=[saved['id']], audience='internal', filename='独立候选重放.docx')
        exported = await call(legal, 'export_case', **export_args)
        for ident, tool, params, result in [('save', 'save_employment_review', args, saved), ('export', 'export_case', export_args, exported)]:
            messages.extend([
                dict(role='assistant', tool_calls=[dict(id=ident, type='function', function=dict(name=tool, arguments=json.dumps(params, ensure_ascii=False)))]),
                dict(role='tool', tool_call_id=ident, content=json.dumps(dict(executed=True, is_error=False, result=result), ensure_ascii=False)),
            ])
    with closing(sqlite3.connect((workspace / '.qx-materials/index.sqlite').resolve().as_uri() + '?mode=ro', uri=True)) as db:
        stored = db.execute('SELECT content FROM legal_notes WHERE case_id=? AND id=?', (cid, saved['id'])).fetchone()[0]
    word_path = Path(exported['path'])
    word = '\n'.join(p.text for p in Document(word_path).paragraphs).replace('\r\n', '\n')
    audit_path = Path(saved['internal_path'])
    audit = '\n'.join(p.text for p in Document(audit_path).paragraphs)
    marker = '故意未核验回复：员工已经同意解除且从未试用。'
    delivery = subprocess.run([os.environ['QX_TEST_NODE'], str(HARNESS / 'scripts/check_verified_delivery.mjs')],
        cwd=HARNESS, input=json.dumps(dict(workspace=str(workspace), messages=messages,
            result=dict(choices=[dict(message=dict(content=marker), finish_reason='stop')])), ensure_ascii=False),
        text=True, encoding='utf-8', capture_output=True, check=True)
    protected = json.loads(delivery.stdout)
    candidates = [c['text'] for c in saved['candidate_drafts']]
    checks = dict(
        only_case_id_changed={k:v for k,v in args.items() if k!='case_id'} == {k:v for k,v in original.items() if k!='case_id'},
        source_bytes_unchanged=digest(source)==source_digest,
        sqlite_matches_readback=stored==body,
        full_note_in_real_word=body.replace('\r\n','\n') in word,
        full_note_in_protected_delivery=body in protected['text'],
        candidate_in_all=all(c in body and c in word and c in protected['text'] for c in candidates),
        semantic_not_certified=saved['content_assurance']['semantic_verified'] is False,
        protected_turn=protected['protectedTurn'],
        fabricated_final_response_removed=marker not in protected['text'],
        actual_word_link_delivered='[已保存记录的 Word]' in protected['text'],
    )
    residual = {}
    prior_body = trace['actual']['case']['notes'][0]['content']
    old_saved = successful[0]['result']['result']
    changes = old_saved['review_changes']
    expected = prior_body
    checks.update(
        original_schema_failures_still_rejected=bool(failed_replays) and all(r['rejected'] and r['notes_created']==0 and r['original_arguments_unchanged'] for r in failed_replays),
        no_new_attribution_changes=not any('来源归属复述' in c['reason'] for c in saved['review_changes']),
        candidate_does_not_adopt_facts=all('不确认任一方已经同意解除、款项已经支付或竞业义务已经终止' in c for c in candidates),
    )
    if name == 'attribution-conflict':
        evidence = '单方转述难以证明通知已作出或未作出。'
        unsupported = '举证的现实困难在于口头通话内容缺少记录'
        correct = '本项陈述媒介及内容以所引原文为准'
        old_basis = next(c for c in changes if c['label']=='第6项basis')
        new_basis = original['findings'][5]['basis'].replace(unsupported,correct)
        old_risk = next(c for c in changes if c['label']=='第1项risk')
        old_timing = next(c for c in changes if c['label']=='第5项basis')
        timing = '情形一（解除已作出并到达）：竞业义务自到达时终止，并按解释（一）第39条考虑额外三个月经济补偿，已履行期间的补偿另行结算。'
        new_timing = old_timing['replacement'].replace(timing,'')
        for before, after in [(old_basis['replacement'],new_basis),(old_risk['replacement'],old_risk['original']),(old_timing['replacement'],new_timing)]:
            assert expected.count(before)==1, 'Expected old target must occur exactly once'
            expected=expected.replace(before,after)
        checks.update(
            live1_independent_evidence_reasoning_in_all=all(evidence in x for x in [body,word,protected['text']]),
            live1_medium_claim_points_to_source=new_basis in body and unsupported not in body,
            live1_no_irrelevant_attendance_text='考勤具体内容及违纪判断' not in body,
            live2_pending_list_preserved_in_all=all(old_risk['original'] in x for x in [body,word,protected['text']]),
            live2_no_dangling_prefix='凡涉及期限起止、补偿状态按' not in body,
            live3_automatic_arrival_rule_removed=all(timing not in x for x in [body,word,protected['text']]),
            live3_effective_time_must_be_checked='先核有效解除时间' in body,
            four_steps_exactly_retained=original['findings'][5]['action'] in body,
            both_conflicting_claims_kept=all(x in body for x in ['员工邮件称公司本月电话通知解除竞业，自己未同意。','公司邮件称尚未发出解除通知，并要求继续履行。']),
            disputed_time_not_decided='何时生效均待核' in body,
            changed_original_fields_retained_in_audit=all(original['findings'][i][f] in audit for i,f in [(5,'basis'),(4,'basis')]),
            unchanged_original_risk_retained_without_false_audit=original['findings'][0]['risk'] in body and not any(c['label']=='第1项risk' for c in saved['review_changes']),
        )
    else:
        checks.update(
            speaker_explicitly_unknown='陈述主体未标明' in body,
            employee_agreement_still_unknown='员工是否同意未说明' in body,
            source_contact_fact_kept='员工离职前接触技术秘密，已履行竞业6个月。' in body,
            no_employee_self_report_added='员工自述' not in body,
        )
    checks['whole_body_only_expected_changes'] = body==expected
    if body!=expected:
        import difflib
        residual['unexpected_whole_body_diff']=''.join(difflib.unified_diff(expected.splitlines(True),body.splitlines(True),fromfile='expected',tofile='replayed'))
    return dict(case=name, trace_sha256=digest(trace_path), source_sha256=source_digest,
                parameter_changes='Only case_id; all other original arguments unchanged', checks=checks, failed_replays=failed_replays,
                passed=all(checks.values()), residual=residual, note_content=body, word_sha256=digest(word_path),
                word_text=word, protected_response=protected['text'], review_changes=saved['review_changes'],
                internal_audit_sha256=digest(audit_path), internal_audit_text=audit)


async def main():
    code_files = ('bridge/employment_drafts.py','bridge/employment_review.py','bridge/employment_source_claims.py',
                  'bridge/source_bound_inputs.py','bridge/business_server.py','bridge/noncompete_conditions.py')
    before = {p:digest(HARNESS/p) for p in code_files}
    report = dict(scope='Independent offline real MCP captured-save replay; not new model results',
                  code_sha256=before, temporary_workspaces_removed=True, cases=[])
    with TemporaryDirectory(prefix='attribution-live-') as temp:
        for name in ('noncompete-draft','attribution-conflict'):
            workspace=Path(temp)/name
            workspace.mkdir()
            report['cases'].append(await replay(name,workspace))
    report['code_unchanged_during_replay'] = before == {p:digest(HARNESS/p) for p in code_files}
    report['passed'] = report['code_unchanged_during_replay'] and all(r['passed'] for r in report['cases'])
    (HERE/'attribution-live-replay.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(passed=report['passed'], code_unchanged=report['code_unchanged_during_replay'],
                         results=[{k:r[k] for k in ('case','checks','residual')} for r in report['cases']]),ensure_ascii=False))
    if not report['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    asyncio.run(main())
