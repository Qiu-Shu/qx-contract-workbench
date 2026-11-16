"""Independent captured-save replay through MCP and production delivery; no model calls."""
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
    trace_path = HERE / 'e2e/principles-drafts' / (name + '.json')
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
    if name == 'probation-history':
        candidate = candidates[0]
        checks.update(no_provided_period_claim='已给合同期限' not in candidate,
                      no_assumed_wage_review='本次工资审查项' not in candidate,
                      explicit_statutory_limits=all(s in candidate for s in ('一个月','二个月','六个月')),
                      no_false_history='本条不确认本次为首次试用' in candidate)
    elif name == 'attendance-draft':
        five_steps = next(f['action'] for f in original['findings'] if f['topic']=='公司方处理意见（内部）')
        proof = next(f['basis'] for f in original['findings'] if f['topic']=='考勤摘录的具体条目')
        disputed = next(f['basis'] for f in original['findings'] if f['topic']=='双方陈述并列与冲突（事实基础）')
        checks.update(five_steps_exactly_retained=five_steps in body, proof_analysis_exactly_retained=proof in body,
                      whether_oral_agreement_analysis_retained=disputed in body)
    else:
        candidate = candidates[0]
        checks.update(unknown_agreement_preserved='员工是否同意未说明' in body,
                      neutral_intent_question='并确认各方对解除的意思表示' in candidate,
                      no_adopted_agreement_or_payment='不确认任一方已经同意解除、款项已经支付' in candidate,
                      conditional_additional_compensation='如涉及用人单位在竞业限制期限内请求解除' in candidate)
        residual['unfounded_self_report_attribution_remains'] = '目前仅能确认员工自述离职前接触技术秘密' in body
    return dict(case=name, trace_sha256=digest(trace_path), source_sha256=source_digest,
                parameter_changes='Only case_id; all other original arguments unchanged', checks=checks, failed_replays=failed_replays,
                passed=all(checks.values()), residual=residual, note_content=body, word_sha256=digest(word_path),
                word_text=word, protected_response=protected['text'], review_changes=saved['review_changes'])


async def main():
    code_files = ('bridge/employment_drafts.py','bridge/employment_review.py','bridge/employment_source_claims.py',
                  'bridge/source_bound_inputs.py','bridge/business_server.py')
    before = {p:digest(HARNESS/p) for p in code_files}
    report = dict(scope='Independent offline real MCP captured-save replay; not new model results',
                  code_sha256=before, temporary_workspaces_removed=True, cases=[])
    with TemporaryDirectory(prefix='principles-spec-') as temp:
        for name in ('probation-history','attendance-draft','noncompete-draft'):
            workspace=Path(temp)/name
            workspace.mkdir()
            report['cases'].append(await replay(name,workspace))
    report['code_unchanged_during_replay'] = before == {p:digest(HARNESS/p) for p in code_files}
    report['passed'] = report['code_unchanged_during_replay'] and all(r['passed'] for r in report['cases'])
    (HERE/'first-principles-spec-replay.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(passed=report['passed'], code_unchanged=report['code_unchanged_during_replay'],
                         results=[{k:r[k] for k in ('case','checks','residual')} for r in report['cases']]),ensure_ascii=False))
    if not report['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    asyncio.run(main())
