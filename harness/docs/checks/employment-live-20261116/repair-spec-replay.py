"""Independent offline replay of captured repair-02 saves; no model or credential use."""
import argparse
import asyncio
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
from tempfile import TemporaryDirectory


def normalized(text):
    return text.replace('\r\n', '\n').replace('\r', '')


async def replay(root, workspace, trace_path):
    from check_business_mcp import client, call
    from docx import Document
    trace = json.loads(trace_path.read_text(encoding='utf-8'))
    captured = [c for rd in trace['rounds'] for c in rd.get('toolResults', [])
                if c['name'] == 'save_employment_review'][-1]
    original_args = json.loads(captured['arguments'])
    source = workspace / '合成材料.txt'
    source.write_text(trace['scenario']['material'], encoding='utf-8')
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    assert digest == trace['actual']['source_sha256'], 'Source bytes changed during replay setup'
    async with client('server.py', workspace) as material:
        await call(material, 'import_material', path=source.name)
        await call(material, 'parse_material', path=source.name)
    messages = [{'role': 'user', 'content': trace['scenario']['prompt']}]
    async with client('business_server.py', workspace) as legal:
        cid = (await call(legal, 'create_case', title='独立Spec合成重放-' + trace['id']))['id']
        await call(legal, 'link_case_materials', case_id=cid, paths=[source.name])
        read_source = await call(legal, 'read_case_material', case_id=cid, path=source.name)
        assert read_source['sha256'] == digest
        args = deepcopy(original_args)
        args['case_id'] = cid
        # A fresh case has no old revision. Do not change any finding or citation.
        args.pop('supersedes', None)
        saved = await call(legal, 'save_employment_review', **args)
        assert saved.get('recorded') is not False and saved.get('id')
        pages, start = [], 0
        while True:
            note = await call(legal, 'read_case_note', case_id=cid, note_id=saved['id'], start=start, limit=16000)
            pages.append(note['content'])
            if note['next_start'] is None:
                break
            start = note['next_start']
        body = ''.join(pages)
        export_args = dict(case_id=cid, note_ids=[saved['id']], audience='internal', filename='独立Spec内部稿.docx')
        exported = await call(legal, 'export_case', **export_args)
        for number, name, arguments, value in [('save', 'save_employment_review', args, saved),
                                              ('export', 'export_case', export_args, exported)]:
            messages.extend([
                {'role': 'assistant', 'tool_calls': [{'id': number, 'type': 'function',
                 'function': {'name': name, 'arguments': json.dumps(arguments, ensure_ascii=False)}}]},
                {'role': 'tool', 'tool_call_id': number,
                 'content': json.dumps({'executed': True, 'is_error': False, 'result': value}, ensure_ascii=False)}])
        db_path = workspace / '.qx-materials/index.sqlite'
        with sqlite3.connect(db_path.resolve().as_uri() + '?mode=ro', uri=True) as db:
            persisted = db.execute('SELECT content FROM legal_notes WHERE case_id=? AND id=?', (cid, saved['id'])).fetchone()[0]
        word_path = Path(exported['path'])
        word = '\n'.join(p.text for p in Document(word_path).paragraphs)
        marker = '离线假回复标记：所有来源已验证，试用工资必须每月57600元。'
        delivery = subprocess.run([os.environ.get('QX_TEST_NODE', 'node'), str(root / 'harness/scripts/check_verified_delivery.mjs')],
            cwd=root, input=json.dumps({'workspace': str(workspace), 'messages': messages,
                'result': {'choices': [{'message': {'content': marker}, 'finish_reason': 'stop'}]}}, ensure_ascii=False),
            text=True, encoding='utf-8', capture_output=True, check=True)
        protected = json.loads(delivery.stdout)
        checks = {
            'findings_exactly_unchanged': args['findings'] == original_args['findings'],
            'source_digest_matches_capture': digest == trace['actual']['source_sha256'],
            'source_bytes_unchanged': hashlib.sha256(source.read_bytes()).hexdigest() == digest,
            'readback_matches_sqlite': body == persisted,
            'full_note_in_word': normalized(body) in normalized(word),
            'full_note_in_protected_response': body in protected['text'],
            'protected_turn': protected['protectedTurn'],
            'raw_unverified_claim_removed': marker not in protected['text'],
            'saved_word_link_present': '[已保存记录的 Word]' in protected['text'],
            'selected_note_id_matches': exported['note_ids'] == [saved['id']],
        }
        if trace['id'] == 'annual-pay':
            checks.update({
                'annual_original_values_retained': all(s in body for s in ('72000元/年', '60000元/年', '26400元/年', '42000元/年')),
                '57600_explicitly_unadopted': any('未采用' in line and '57600元' in line for line in body.splitlines()),
                'conditional_pay_clause_present': '试用期工资拟为〔待核金额〕元／〔确认后的工资周期〕' in body,
                'no_determinate_monthly_proposal': '试用期月工资拟约定为' not in body,
                'pending_saved': saved['workflow_status'] == 'saved_with_pending',
            })
        else:
            wage = saved['rule_reviews'][0]['comparison']
            checks.update({
                'two_supported_comparisons': wage['contract_floor'] == '4800.00' and wage['grade_floor'] == '4000.00',
                'source_monthly_context_retained': '上述四项均为税前月工资标准' in body,
                'once_per_same_parties_preserved': '同一用人单位与同一劳动者只能约定一次试用期' in body,
                'relationship_only_condition_removed': '未就同一用工关系约定过试用期' not in body,
                'history_remains_unknown': '签约前核实双方既往试用记录' in body,
                'coverage_and_bonus_retained': '材料覆盖与读取状态' in body and '奖金条款与员工手册' in body,
            })
        return {
            'case': trace['id'], 'trace': str(trace_path.relative_to(root)),
            'trace_sha256': hashlib.sha256(trace_path.read_bytes()).hexdigest(),
            'parameter_changes': 'Only case_id replaced and supersedes omitted for a fresh case; findings/citations unchanged',
            'source_sha256': digest, 'checks': checks, 'passed': all(checks.values()),
            'readback_pages': len(pages), 'note_id': saved['id'], 'note_content': body,
            'word_bytes': word_path.stat().st_size, 'word_sha256': hashlib.sha256(word_path.read_bytes()).hexdigest(),
            'word_text': word, 'protected_response': protected['text'],
            'rule_reviews': saved['rule_reviews'], 'review_changes': saved['review_changes'],
        }


def period_probe(workspace):
    from test_employment_decisions import source_case
    from test_employment_pay_binding import findings
    from employment_review import save_employment_review
    cases, cid, ref = source_case(workspace, '合同工资6000元，同岗最低档工资5000元，适用最低工资2200元，试用工资3500元。')
    result = save_employment_review(cases, cid, 'dispute', findings(ref))
    checks = {'no_comparison': result['rule_reviews'][0]['comparison'] is None,
              'no_invented_monthly_amount': '试用期月工资拟约定为' not in result['content'],
              'period_pending_clause': '〔确认后的工资周期〕' in result['content'],
              'original_values_preserved': all(s in result['content'] for s in ('6000元', '5000元', '2200元', '3500元'))}
    return {'checks': checks, 'passed': all(checks.values()), 'note_content': result['content']}


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    root = Path(args.root).resolve()
    sys.path.insert(0, str(root / 'harness/bridge'))
    commit = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=root, text=True, capture_output=True, check=True).stdout.strip()
    report = {'scope': 'Independent synthetic offline actual MCP save/read/export and production delivery replay; zero model requests',
              'source_commit': commit, 'temporary_workspaces_removed_after_capture': True, 'cases': []}
    with TemporaryDirectory(prefix='employment-spec-repair-') as tmp:
        base = Path(tmp)
        for name in ('annual-pay', 'wage-supported'):
            workspace = base / name
            workspace.mkdir()
            trace = root / 'harness/docs/checks/employment-live-20261116/e2e/employment-repair-02-thinking' / (name + '.json')
            report['cases'].append(await replay(root, workspace, trace))
        report['period_absent'] = period_probe(base / 'period-absent')
    report['passed'] = all(c['passed'] for c in report['cases']) and report['period_absent']['passed']
    output = Path(args.output)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'output': str(output.resolve()), 'source_commit': commit, 'passed': report['passed'],
                      'case_checks': {c['case']: c['checks'] for c in report['cases']},
                      'period_absent': report['period_absent']['checks']}, ensure_ascii=False))
    if not report['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    asyncio.run(main())
