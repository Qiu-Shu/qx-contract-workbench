"""Assemble final review metadata from the recorded independent execution."""
import hashlib
import json
from pathlib import Path

out = Path(__file__).resolve().parent
root = out.parents[2]
run = json.loads((out/'standards-final.json').read_text(encoding='utf-8'))
assert run['exit_code'] == 0 and run['source_stable']
assert all(hashlib.sha256((root/name).read_bytes()).hexdigest() == digest
           for name, digest in run['source_after'].items())
report = {
    'task': 'CH-05B Jev independent ledger and recovery',
    'axis': 'Standards', 'reviewer': '/root/generation_history_api',
    'workspace': str(root), 'baseline': 'a4c3c6706caad31c2335b4d055240dbddbfbd372',
    'comparison': 'Working tree plus untracked source modules; HEAD equalled baseline at review start',
    'result': 'PASS_NO_FINDINGS', 'findings': [],
    'documented_standard_violations': [], 'actionable_smells': [],
    'standards': ['AGENTS.md', 'Ponytail full', 'code-review Standards and its 12 Fowler heuristics',
        'docs/plans/2026-10-20-jev-ledger.md', 'docs/plans/chat-first-architecture-v2.1.md sections 6.4-6.5'],
    'checks': [
        {'file': 'src/cn_contract/domain.py', 'lines': [3092, 3159],
         'conclusion': 'Business DTOs remain centralized immutable snapshots; Decimal USD and UTC, with no I/O or permission decisions.'},
        {'file': 'src/cn_contract/assistant/providers/judge_attempts.py', 'lines': [36, 145],
         'conclusion': 'Original full message/run scope and independent policy/session/config identity are verified; conservative quota accounting in caller-owned short transactions.'},
        {'file': 'src/cn_contract/assistant/providers/judge_attempts.py', 'lines': [173, 256],
         'conclusion': 'Single CAS claim, immutable accounting and conditional decision adoption; recovery/cancel never select provider/model or finish the main run.'},
        {'file': 'src/cn_contract/assistant/providers/judge_execution.py', 'lines': [10, 48],
         'conclusion': 'HTTP occurs after the claim transaction closes; preflight and settlement use separate transactions; exact JevProvider owns the only deadline and cancellation remains conservative.'},
        {'file': 'src/cn_contract/assistant/providers/judge_policy.py', 'lines': [43, 146],
         'conclusion': 'Independent actor/session/workspace/request hash permissions, fixed recipient, policy-id digest ledger, configuration and authorization generations, app-loop execution ownership.'},
        {'file': 'src/cn_contract/assistant/judge_schema.py', 'lines': [5, 40],
         'conclusion': 'Only three additive tables reference existing assistant_runs; immutable input, claim and receipts; no second queue.'},
        {'file': 'src/cn_contract/assistant/judge_integrity.py', 'lines': [45, 175],
         'conclusion': 'Historical input/config/policy/source/identity/receipt/decision and budget evidence cross-checked independently of current live authorization.'},
        {'file': 'src/cn_contract/storage_schema.py', 'lines': [2, 35],
         'conclusion': 'Main schema is captured from baseline, historical versions retained; narrow bootstrap/migration/backup/startup integration.'},
        {'file': 'src/cn_contract/assistant/providers/jev.py', 'lines': [49, 204],
         'conclusion': 'Single-call trusted preflight checked before secret and before POST; default deny, no new SDK, raw-data logs or environment-controlled destination.'}
    ],
    'independent_verification': {
        'command': run['command'], 'exit_code': 0, 'passed': 3, 'failed': 0,
        'pytest_seconds': 1.63,
        'evidence': ['standards-final.log', 'standards-final.exit', 'standards-final.xml', 'standards-final.json'],
        'probe_cases': [
            'Independent write transaction finishes while actual loopback HTTP waits; one POST, repeat execution does not resend; main run and event count unchanged',
            'No runtime/config/policy and Main runtime cannot reserve Jev; no secret lookup or ledger mutation',
            'Frozen Main DDL exactly equals baseline git source; native and non-native schemas add only Jev ledger objects'
        ],
        'loopback_posts': 1, 'external_network_attempts': 0, 'real_model_calls': 0,
        'unknown_cost_occupied_usd': '0.031', 'unit': 'USD',
        'main_run_row_unchanged': True, 'main_run_events_unchanged': True,
        'main_model_attempt_count': 0,
        'source_count': len(run['source_after']), 'source_stable': run['source_stable'],
        'author_targets_included_in_count': False
    },
    'source_sha256': run['source_after'],
    'limitations': [
        'Only local review artifacts were written; no product, author tests, project state or commit changes.',
        'No real credentials/materials or external network/model calls.',
        'Author target regressions and Windows validation were not rerun or counted as independent results.',
        'Native Jev UI, main-runner integration, actual vendor pricing and additional material mapping are explicit later scope, not defects of this slice.',
        'Standards review does not replace the independent Spec axis or production approval.'
    ]
}
(out/'review-standards.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'status': 'saved', 'findings': 0, 'passed': 3, 'source_count': len(run['source_after'])}))
