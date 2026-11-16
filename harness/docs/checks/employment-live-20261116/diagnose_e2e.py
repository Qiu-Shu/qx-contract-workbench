"""Offline replay of captured synthetic E2E calls; no credentials or model requests."""
import argparse
import asyncio
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

parser = argparse.ArgumentParser()
parser.add_argument('--root', required=True)
parser.add_argument('--trace', required=True)
parser.add_argument('--output', required=True)
parser.add_argument('--assert-supported', action='store_true')
args = parser.parse_args()
root = Path(args.root)
sys.path.insert(0, str(root / 'harness/bridge'))
from check_business_mcp import client, call
from docx import Document
from employment_parameter_extraction import extract_term_parameters, _extract_lines, parameter_context_warnings
from employment_rule_review import prepare_probation_pay
from test_employment_decisions import source_case

trace = json.loads(Path(args.trace).read_text(encoding='utf-8'))
calls = [(n, c) for n, rd in enumerate(trace['rounds']) for c in rd.get('toolResults', [])]


def narrow(result):
    extraction = result.get('parameter_extraction') or {}
    return {
        'id': result.get('id'),
        'error': result.get('text') or result.get('error'),
        'rule_reviews': [{k: row.get(k) for k in ('finding_index', 'rule', 'comparison', 'pending_reason')}
                         for row in result.get('rule_reviews', [])],
        'groups': [{'raw': row.get('raw', row.get('source_text')), 'warnings': row.get('warnings'),
                    'comparisons': row.get('comparisons'), 'parameters': list(row.get('parameters', {}))}
                   for row in extraction.get('groups', [])],
        'linked_groups': [{'header': row.get('header'), 'warnings': row.get('warnings'),
                           'comparisons': row.get('comparisons')}
                          for row in extraction.get('linked_groups', [])],
    }


async def replay(workspace):
    source = workspace / '合成材料.txt'
    source.write_text(trace['scenario']['material'], encoding='utf-8')
    captured_material = next(c['result']['result'] for _, c in calls if c['name'] == 'read_case_material')
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    assert digest == captured_material['sha256'], 'Replay must preserve exact original source bytes'
    result_rows, note_ids = [], {}
    async with client('server.py', workspace) as material:
        await call(material, 'import_material', path=source.name)
        await call(material, 'parse_material', path=source.name)
    async with client('business_server.py', workspace) as legal:
        cid = (await call(legal, 'create_case', title='合成原调用离线诊断'))['id']
        await call(legal, 'link_case_materials', case_id=cid, paths=[source.name])
        last_note = None
        for n, captured in calls:
            params = json.loads(captured['arguments'])
            params['case_id'] = cid
            if params.get('supersedes'):
                params['supersedes'] = note_ids[params['supersedes']]
            response = await legal.call_tool(captured['name'], params, read_timeout_seconds=60)
            result = response.structured_content
            if result is None:
                raw = '\n'.join(c.text for c in response.content if c.type == 'text')
                try:
                    result = json.loads(raw)
                except ValueError:
                    result = {'text': raw}
            row = {'round_zero_based': n, 'name': captured['name'], 'is_error': response.is_error,
                   'captured_is_error': captured['result']['is_error'], **narrow(result)}
            assert response.is_error == captured['result']['is_error'], row
            if result.get('id') and captured['name'] in ('save_employment_review', 'assess_employment_terms'):
                old_id = captured['result']['result']['id']
                note_ids[old_id] = result['id']
                last_note = result['id']
            result_rows.append(row)
        note = await call(legal, 'read_case_note', case_id=cid, note_id=last_note, limit=16000)
        assert note.get('next_start') is None
        exported = await call(legal, 'export_case', case_id=cid, filename='离线诊断内部稿.docx',
                              audience='internal', note_ids=[last_note])
        word_path = Path(exported['path'])
        if not word_path.is_absolute():
            word_path = workspace / word_path
        document = '\n'.join(p.text for p in Document(word_path).paragraphs)
        pending = result_rows[-1]['rule_reviews'][0]['pending_reason']
        export_check = {'read_note_complete': note.get('next_start') is None,
                        'word_exists': word_path.is_file(), 'word_bytes': word_path.stat().st_size,
                        'selected_note_id_matches': exported['note_ids'] == [last_note],
                        'saved_pending_reason_in_word': pending in document,
                        'source_bytes_unchanged': hashlib.sha256(source.read_bytes()).hexdigest() == digest}
        assert all(export_check[k] for k in ('read_note_complete', 'word_exists', 'selected_note_id_matches', 'saved_pending_reason_in_word', 'source_bytes_unchanged'))
    return {'source_sha256': digest, 'exact_source_bytes_preserved': True,
            'parameter_changes': 'Only case_id and supersedes UUIDs remapped to fresh synthetic case',
            'calls': result_rows, 'explicit_offline_export_after_replay': export_check}


last_save = json.loads(next(c['arguments'] for _, c in reversed(calls) if c['name'] == 'save_employment_review'))
wage_item = next(f for f in last_save['findings'] if f.get('rule') == 'probation_pay')
wage = '合同工资6000元，同岗最低档工资5000元，适用最低工资2200元，试用工资3500元。'
tail = '上述四项均为税前月工资标准。'
bonus = '奖金按员工手册支付，员工手册本次未提供。'
intro = '独立虚构测试，均为同一员工同一工资期间的数据。'
header = '劳动者：测试甲；合同编号：C-1'
variants = {
    'bare_wage_control': wage,
    'unrelated_missing_bonus': wage + '\n' + bonus,
    'monthly_positive_suffix': wage + tail,
    'inline_intro_before_identifier': intro + header + '\n' + wage,
    'separate_intro_before_identifier_control': intro + '\n' + header + '\n' + wage,
    'exact_identifier_header_control': header + '\n' + wage,
    'original_without_bonus_or_suffix': intro + header + '\n合同期限3年，试用期3个月。\n' + wage,
    'original_all_three_removed_control': header + '\n合同期限3年，试用期3个月。\n' + wage,
    'original_exact': trace['scenario']['material'],
}


def variant_probe(workspace, text):
    cases, cid, ref = source_case(workspace, text, name='合成材料.txt')
    material = cases.read_material(cid, ref['path'])
    chunk = material['chunks'][0]
    context = {'path': ref['path'], 'sha256': ref['sha256'], 'chunk': chunk['ordinal'],
               'text': chunk['text'], 'location': chunk.get('location', '')}
    item = deepcopy(wage_item)
    for field, value in item['parameters'].items():
        value['citation'] = {**ref, 'quote': wage}
    _, review = prepare_probation_pay(cases, cid, item, 0)
    local, _ = _extract_lines('hiring', [context])
    linked, _ = extract_term_parameters('hiring', [context])
    return {'text': text, 'comparison_present': review['comparison'] is not None,
            'comparison': review['comparison'], 'pending_reason': review['pending_reason'],
            'whole_chunk_context_warnings_before_identifier_exemption': parameter_context_warnings(context['text']),
            'local_groups': [{'raw': row.get('raw', row.get('source_text')), 'warnings': row['warnings'],
                              'comparison_kinds': [c['kind'] for c in row['comparisons']]}
                             for row in local['groups']],
            'recognized_identity_headers': [row['header']['raw'] for row in linked['linked_groups']]}


async def main():
    summary = {'scope': 'Synthetic offline actual MCP replay and function probes; no model/credential calls',
               'captured_trace': str(Path(args.trace).resolve()), 'captured_status': trace['status'],
               'captured_functional_checks': trace['functionalChecks'],
               'captured_tool_counts': {name: sum(c['name'] == name for _, c in calls)
                                        for name in sorted({c['name'] for _, c in calls})}}
    schema = next(t['function'] for t in trace['tools'] if t['function']['name'] == 'save_employment_review')
    summary['captured_save_schema'] = {'description': schema['description'],
                                      'findings': schema['parameters']['properties']['findings']}
    initial = json.loads(next(c['arguments'] for _, c in calls if c['name'] == 'save_employment_review'))
    summary['first_save_fields'] = [{'finding_index': n, 'source_present': 'source' in f,
                                    'source_type': type(f.get('source')).__name__,
                                    'rule': f.get('rule'),
                                    'parameter_shapes': {k: sorted(v) for k, v in f.get('parameters', {}).items()}}
                                   for n, f in enumerate(initial['findings'])]
    chunk = next(c['result']['result']['chunks'][0]['text'] for _, c in calls if c['name'] == 'read_case_material')
    offset_call = json.loads(next(c['arguments'] for n, c in calls if n == 7))
    summary['round7_offsets'] = [{'quote': c['quote'], 'provided_start': c.get('start'), 'provided_end': c.get('end'),
                                 'actual_start': chunk.find(c['quote']), 'actual_end': chunk.find(c['quote']) + len(c['quote']),
                                 'provided_slice_matches': chunk[c['start']:c['end']] == c['quote']}
                                for c in offset_call['citations']]
    with TemporaryDirectory(prefix='qx-employment-diagnosis-') as temporary:
        base = Path(temporary)
        replay_dir = base / 'replay'
        replay_dir.mkdir()
        summary['replay'] = await replay(replay_dir)
        summary['minimal_variants'] = {name: variant_probe(base / name, text) for name, text in variants.items()}
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'output': str(output.resolve()), 'mcp_replayed_calls': len(summary['replay']['calls']),
                      'replay_error_rounds': [r['round_zero_based'] for r in summary['replay']['calls'] if r['is_error']],
                      'minimal_variants': {k: v['comparison_present'] for k, v in summary['minimal_variants'].items()},
                      'explicit_offline_export': summary['replay']['explicit_offline_export_after_replay']}, ensure_ascii=False))
    if args.assert_supported:
        assert summary['minimal_variants']['original_exact']['comparison_present'], 'Supported same-worker monthly wage fixture remains incorrectly pending'


asyncio.run(main())
