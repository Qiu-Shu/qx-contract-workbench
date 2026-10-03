"""Bounded static pytest execution and separately labelled material processing."""
from collections import Counter
from datetime import datetime,timezone
import json,shlex,subprocess,sys
from pathlib import Path
from uuid import uuid4
from defusedxml import ElementTree

from ..config import PROJECT_ROOT
from ..domain import EvaluationReport,EvaluationCaseResult,ExecutionEvidence,SampleEvaluationResult
from .registry import validate_cases,load_dataset,hash_bytes,STATUSES
from .definitions import DEFINITIONS,MANIFEST_SHA256,SUITE_SHA256


def assess_readiness(results):
    if any(r.hard_gate and (r.status=='FAIL' or r.guard_status=='FAIL' or r.partial_status=='FAIL') for r in results):return 'NO_GO'
    if any(r.status=='FAIL' for r in results):return 'NO_GO'
    # No T11 pathway owns actual qualified-lawyer gold/provider/production grants.
    return 'BLOCKED'


def _source_snapshot(nodes):
    paths={PROJECT_ROOT/n.split('::')[0] for n in nodes}
    paths.update(p for p in (PROJECT_ROOT/'src').rglob('*.py'))
    for folder in ('prompts','config','schemas','sources','tests/helpers','tests/fixtures'):
        paths.update(p for p in (PROJECT_ROOT/folder).rglob('*') if p.is_file())
    paths.update(PROJECT_ROOT.glob('requirements*.lock'))
    paths.update([PROJECT_ROOT/'pyproject.toml',PROJECT_ROOT/'scripts/verify_sources.py',PROJECT_ROOT/'scripts/verify_runtime_dependencies.py'])
    # Source gates consume fixed cached evidence in addition to their locks.
    # These declared paths identify bytes only; they never select execution.
    for name in ('upstream.lock.json','runtime-dependencies.lock.json'):
        manifest=PROJECT_ROOT/'sources'/name
        if not manifest.is_file():continue
        stack=[json.loads(manifest.read_bytes())]
        local_fields={'local_target','local_cache','baseline_lock_cache','command_log',
            'registry_cache','wheel_cache','metadata_cache','inherited_wheel_cache',
            'restricted_fingerprint_file','dependency_evidence','artifact_origin'}
        while stack:
            item=stack.pop()
            if isinstance(item,dict):
                for key,value in item.items():
                    if key in local_fields and isinstance(value,str):
                        path=PROJECT_ROOT/value
                        if path.resolve().is_relative_to(PROJECT_ROOT.resolve()) and path.is_file():paths.add(path)
                    stack.append(value)
            elif isinstance(item,list):stack.extend(item)
    paths.add(PROJECT_ROOT/'tests/acceptance/cases.json')
    paths.update(p for p in (PROJECT_ROOT/'tests/fixtures/acceptance').rglob('*') if p.is_file())
    return {p.relative_to(PROJECT_ROOT).as_posix():hash_bytes(p.read_bytes()) for p in sorted(paths)
        if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc'}


def _execute(nodes,root):
    junit=root/'registered-tests.xml';log=root/'registered-tests.log'
    collection=root/'registered-collection.json'
    argv=[sys.executable,'-X','utf8','-m','pytest','-p','cn_contract.acceptance.pytest_evidence',*nodes,'-q','--tb=short','--junitxml='+str(junit),'--cn-collection-evidence='+str(collection)]
    before=_source_snapshot(nodes);started=datetime.now(timezone.utc)
    result=subprocess.run(argv,cwd=PROJECT_ROOT,capture_output=True,text=True,encoding='utf-8',shell=False)
    log.write_text(result.stdout+result.stderr,encoding='utf-8');ended=datetime.now(timezone.utc)
    states={};observed={};counts=Counter()
    if junit.is_file():
        tree=ElementTree.parse(junit)
        for item in tree.iter('testcase'):
            # Pytest emits an unnamed metadata record on native interruption;
            # retain the original XML, but it is not an executed named test.
            outcome='errors' if item.find('error') is not None else 'failed' if item.find('failure') is not None else 'skipped' if item.find('skipped') is not None else 'passed'
            named=bool(item.attrib.get('classname') and item.attrib.get('name'))
            if not named and outcome=='passed':continue
            counts[outcome]+=1
            if not named:continue
            exact=item.attrib['classname'].replace('.','/')+'.py::'+item.attrib['name']
            node=exact.split('[',1)[0]
            state='FAIL' if outcome in ('failed','errors') else 'NOT_RUN' if outcome=='skipped' else 'PASS'
            states.setdefault(node,[]).append(state);observed.setdefault(node,set()).add(exact)
    expected={}
    if collection.is_file():
        for exact in json.loads(collection.read_bytes())['nodeids']:
            expected.setdefault(exact.split('[',1)[0],set()).add(exact)
    after=_source_snapshot(nodes);stable=before==after
    # Missing/partial collection or drift never certifies the absent assertions.
    final={node:('FAIL' if 'FAIL' in states.get(node,[]) else 'PASS' if stable and result.returncode in (0,1) and expected.get(node) and expected[node]==observed.get(node) and all(s=='PASS' for s in states.get(node,[])) else 'NOT_RUN') for node in nodes}
    evidence=ExecutionEvidence(command=shlex.join(argv),argv=tuple(argv),exit_code=result.returncode,
        executed_at=started,completed_at=ended,passed=counts['passed'],failed=counts['failed'],errors=counts['errors'],skipped=counts['skipped'],
        junit_ref=str(junit) if junit.is_file() else None,junit_sha256=hash_bytes(junit.read_bytes()) if junit.is_file() else None,
        collection_ref=str(collection) if collection.is_file() else None,collection_sha256=hash_bytes(collection.read_bytes()) if collection.is_file() else None,
        output_ref=str(log),output_sha256=hash_bytes(log.read_bytes()),source_hashes=before,source_stable=stable)
    return final,evidence


def evaluate_suite(cases,mode,*,execute=True,output_root=None):
    cases=validate_cases(cases)
    if mode not in {'offline','approved_model','live_guarded'}:raise ValueError('EVALUATION_MODE_INVALID')
    samples=load_dataset();states={};executions=();sample_results=[];root=None
    if execute and mode=='offline':
        parent=Path(output_root) if output_root else PROJECT_ROOT/'.local/evaluation'
        parent.mkdir(parents=True,exist_ok=True);root=parent/uuid4().hex;root.mkdir(exist_ok=False)
        nodes=tuple(dict.fromkeys(node for d in DEFINITIONS.values() for group in ('capability_tests','guard_tests','partial_tests') for node in d[group]))
        states,evidence=_execute(nodes,root);executions=(evidence,)
        from .sample_runner import run_samples
        sample_results=run_samples(samples,root)
    def combine(nodes):
        if not nodes:return 'NOT_RUN'
        selected=[states.get(n,'NOT_RUN') for n in nodes]
        return 'FAIL' if 'FAIL' in selected else 'PASS' if all(v=='PASS' for v in selected) else 'NOT_RUN'
    results=[]
    for case in cases:
        d=DEFINITIONS[case.test_id]
        status='BLOCKED' if mode!='offline' else combine(d['capability_tests']) if d['disposition']=='RUNNABLE' else d['disposition']
        refs=(executions[0].junit_ref,) if executions else ()
        results.append(EvaluationCaseResult(test_id=case.test_id,status=status,
            details=(d['mapping_note'],*d['remaining'],'catalog引用 '+case.fixture+' / '+case.fixture_sha256,
                'catalog材料工程处理与原规格断言分别计分；节点可能自造独立虚构输入。'),
            guard_status=combine(d['guard_tests']),guard_details=d['guard_tests'] or ('此行无已注册guard断言',),
            partial_status=combine(d['partial_tests']),hard_gate=d['hard_gate'],evidence_refs=refs))
    counts={s:sum(r.status==s for r in results) for s in STATUSES}
    return EvaluationReport(mode=mode,results=tuple(results),executions=executions,denominator=84,counts=counts,
        readiness=assess_readiness(results),sample_denominator=40,samples_reviewed=sum(s.run_id is not None for s in sample_results),
        sample_results=tuple(sample_results),sample_type_counts=dict(Counter(s.contract_type for s in samples)),
        sample_partition_counts=dict(Counter(s.partition for s in samples)),sample_family_counts=dict(Counter(s.family for s in samples)),
        registry_sha256=SUITE_SHA256,fixture_manifest_sha256=MANIFEST_SHA256,
        full_capability_numerator=counts['PASS'],guard_numerator=sum(r.guard_status=='PASS' for r in results),
        guard_denominator=sum(bool(d['guard_tests']) for d in DEFINITIONS.values()),
        limitations=('84为规格分母；旧符号/部分断言/guard成功不是全部能力。','40均为短工程片段，家族隔离预留不是独立律师盲测。',
            '两名真实律师gold、规则、地域/provider/预算/许可批准缺失；法律指标和复核用时unknown。',
            '真实模型/QCC未启用，Word/普通浏览器/OS全局网络抓包本评测未运行。'))
