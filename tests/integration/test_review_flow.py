"""T06 authorised synthetic DOCX to immutable bounded review."""
from uuid import uuid4
import pytest
from tests.unit.test_model_schema import api


def prepared(tmp_path, **options):
    # Locate the absent feature as an assertion before any helper imports.
    api('workflow','run_review')
    from tests.helpers.synthetic_review import prepare
    return prepare(tmp_path, **options)


def execute(env, **options):
    p,s,database,actor,matter,context,parsed=env
    with database.session() as db:
        return api('workflow','run_review')(context,api('model_adapter','MockProvider')(),actor=actor,db=db,**options)


def test_18coverage(tmp_path):
    run=execute(prepared(tmp_path))
    assert len(run.coverage)==18 and len({c.coverage_id for c in run.coverage})==18
    assert run.status=='completed' and all(c.status!='reviewed_no_issue' for c in run.coverage)
    assert any('BLOCKED_RULE_APPROVAL' in x for x in run.limitations)


def test_json_repair_once(tmp_path):
    env=prepared(tmp_path)
    p,s,database,actor,matter,ctx,parsed=env
    with database.session() as db:
        model=api('model_adapter','MockProvider')(raw_outputs=('{broken','{broken'))
        run=api('workflow','run_review')(ctx,model,actor=actor,db=db)
        assert run.status=='failed' and run.error_code=='MODEL_OUTPUT_INVALID'
        attempts=api('storage','read_attempts')(matter.id,run.id,actor,db=db)
        assert len(attempts)==2 and len(run.model_usage)==2
        assert sum(u.input_tokens for u in run.model_usage)>0
        assert all(a['raw_sha256'] and a['raw_ref'] for a in attempts)


def test_no_fake_authority(tmp_path):
    env=prepared(tmp_path)
    run=execute(env)
    from cn_contract.domain import EvidenceBundle
    p,s,database,actor,matter,ctx,parsed=env
    forged=run.model_copy(update={'manifest':run.manifest.model_copy(update={'rules_sha256':'0'*64})})
    with database.session() as db:
        result=api('validator','validate_findings')(forged,EvidenceBundle(anchors={},authorities={},receipts={}),actor=actor,db=db)
        assert not result.ok


def test_missing_appendix(tmp_path):
    run=execute(prepared(tmp_path,paragraphs=['虚构样本','交付以附件《测试SOW》为准。']))
    assert next(c for c in run.coverage if c.coverage_id=='C05').status=='insufficient_material'
    assert any(f.issue_type=='missing_appendix' for f in run.findings)


def test_postsign(tmp_path):
    run=execute(prepared(tmp_path,mode='post_sign',paragraphs=['虚构样本','交付以附件《测试SOW》为准。']))
    assert all('已修改' not in f.recommendation for f in run.findings)
    assert any('履行' in f.recommendation and '补充' in f.recommendation for f in run.findings)


def evidence(parsed):
    from cn_contract.domain import EvidenceBundle
    return EvidenceBundle(anchors={a.id:a for a in parsed.anchors},authorities={},receipts={})


def test_actual_validation_and_read(tmp_path):
    env=prepared(tmp_path);run=execute(env)
    p,s,database,actor,matter,ctx,parsed=env
    with database.session() as db:
        assert api('validator','validate_findings')(run,evidence(parsed),actor=actor,db=db).ok
        assert api('storage','read_run')(matter.id,run.id,actor,db=db)==run
        attempts=api('storage','read_attempts')(matter.id,run.id,actor,db=db)
        assert len(attempts)==3 and {a['operation'] for a in attempts}=={'extract_facts','review_chunk','review_cross_clauses'}
        assert [a['usage'] for a in attempts]==[u.model_dump(mode='json') for u in run.model_usage]
        assert api('storage','read_raw')(matter.id,run.id,attempts[0]['raw_ref'],actor,db=db).startswith('{')


def test_long_tail_and_repeated_quote_positions(tmp_path):
    env=prepared(tmp_path,paragraphs=['独立虚构样本']+['重复观察']*70+['保证安排须核验。'])
    run=execute(env);parsed=env[-1]
    assert run.status=='completed'
    assert len(set(run.coverage[-1].examined_anchor_ids))==len(parsed.anchors)==72
    assert any(parsed.anchors[-1].id in f.anchor_ids for f in run.findings if f.issue_type=='guarantee_material')
    assert len(run.model_usage)==7


def test_duplicate_issue_merges_all_positions(tmp_path):
    env=prepared(tmp_path,paragraphs=['虚构样本','保证安排须核验。']+['其他材料']*65+['保证安排须核验。'])
    run=execute(env);parsed=env[-1]
    findings=[f for f in run.findings if f.issue_type=='guarantee_material']
    assert len(findings)==1
    assert set((*findings[0].anchor_ids,*findings[0].cross_anchor_ids))=={parsed.anchors[1].id,parsed.anchors[-1].id}


@pytest.mark.parametrize('raws,status',[((),()),(('{bad','{bad'),()),((),('sent_unknown',))])
def test_intake_attempts_persist_including_failures(tmp_path,raws,status):
    p,s,database,actor,matter,ctx,parsed=prepared(tmp_path)
    with database.session() as db:
        try:
            api('workflow','extract_document_candidates')(parsed,api('model_adapter','MockProvider')(raw_outputs=raws,statuses=status),matter_id=matter.id,actor=actor,db=db)
        except s.ServiceError:pass
    with database.session() as db:
        records=api('storage','read_intakes')(matter.id,actor,db=db)
        assert len(records)==2
        last=records[-1]
        assert len(last['attempts'])==(2 if raws else 1)
        assert all(a['raw_ref'] and a['raw_sha256'] and a['input_sha256'] and a['usage']['input_tokens']>0 for a in last['attempts'])
        assert last['error_code']==('MODEL_OUTPUT_INVALID' if raws else 'QUERY_STATE_UNKNOWN' if status else None)


def test_fixture_hashes_and_paths_are_actual():
    import hashlib,json
    from cn_contract.review.synthetic import FIXTURES,EXPECTED_HASHES,select_fixture,fixture_directory
    manifest=json.loads((fixture_directory()/'provenance.json').read_text(encoding='utf-8'))
    assert len(manifest['fixtures'])==4 and manifest['synthetic'] is True
    for kind,(name,position,_) in FIXTURES.items():
        selected,pos,path,data=select_fixture(str(fixture_directory()/name))
        assert selected==kind and pos==position and path.is_file()
        assert hashlib.sha256(data).hexdigest()==EXPECTED_HASHES[kind]


def test_demo_cli_registered(tmp_path,capsys):
    from cn_contract.cli import main
    # Exactly one local demo validation; four CLI acceptance runs belong to parent.
    assert main(['demo','--fixture','sales','--provider','mock','--qcc','off','--output-root',str(tmp_path)])==0
    import json
    from pathlib import Path
    payload=json.loads(capsys.readouterr().out)
    assert payload['synthetic'] and payload['qcc_calls']==0 and payload['coverage_count']==18
    assert payload['intake_attempt_count']==1 and payload['model_attempt_count']==3
    assert all(Path(path).is_file() for path in payload['outputs'].values())


@pytest.mark.parametrize('arguments',[['--provider','real'],['--qcc','on']])
def test_demo_live_arguments_block_before_output(tmp_path,capsys,arguments):
    from cn_contract.cli import main
    assert main(['demo','--fixture','sales','--output-root',str(tmp_path),*arguments])==1
    import json
    value=json.loads(capsys.readouterr().out)
    assert value['error_code']=='BLOCKED_LIVE' and value['model_sends']==0 and value['qcc_calls']==0
    assert list(tmp_path.iterdir())==[]


def test_demo_arbitrary_file_rejected(tmp_path,capsys):
    from cn_contract.cli import main
    arbitrary=tmp_path/'not-a-fixture.docx';arbitrary.write_bytes(b'not-read-as-approved-data')
    assert main(['demo','--fixture',str(arbitrary),'--output-root',str(tmp_path/'output')])==1
    assert 'DATA_POLICY_UNAPPROVED' in capsys.readouterr().out
    assert not (tmp_path/'output').exists()


def test_obligation_direction_and_cross_clause_evidence(tmp_path):
    env=prepared(tmp_path,paragraphs=['虚构样本','客户不续约提前90天通知。','供应商涨价提前15天通知。',
        '双方保密。','客户资料允许用于训练。','成果授予许可。','终止时立即失效。'])
    run=execute(env);parsed=env[-1]
    direction=[f.analysis for f in run.findings if f.issue_type=='obligation_direction']
    assert any('客户义务' in a for a in direction) and any('供应商义务' in a for a in direction)
    for issue,ids in [('confidentiality_training',{parsed.anchors[3].id,parsed.anchors[4].id}),
        ('license_termination',{parsed.anchors[5].id,parsed.anchors[6].id})]:
        finding=next(f for f in run.findings if f.issue_type==issue)
        assert ids.issubset(set((*finding.anchor_ids,*finding.cross_anchor_ids)))


def test_no_negotiation_objective_honored(tmp_path):
    import json
    from cn_contract.domain import Matter
    p,s,database,actor,matter,ctx,parsed=prepared(tmp_path,paragraphs=['虚构样本','保证安排须核验。'])
    with database.session() as db:
        row=db.get(p.MatterRow,str(matter.id));payload=json.loads(row.payload)
        payload['objectives']=['无谈判空间，只能评估接受或拒绝；不得建议修改合同。']
        row.payload=Matter.model_validate(payload).model_dump_json()
        ctx=ctx.model_copy(update={'matter':p.read_matter(matter.id,actor,db)})
        run=api('workflow','run_review')(ctx,api('model_adapter','MockProvider')(),actor=actor,db=db)
    assert all('谈判修改' not in f.recommendation and '接受或拒绝' in f.recommendation for f in run.findings)


def test_opposite_positions_change_business_advice(tmp_path):
    buyer_path=tmp_path/'buyer';buyer_path.mkdir()
    seller_path=tmp_path/'seller';seller_path.mkdir()
    buyer=execute(prepared(buyer_path,position='buyer',paragraphs=['虚构样本','保证安排须核验。']))
    seller=execute(prepared(seller_path,position='seller',paragraphs=['虚构样本','保证安排须核验。']))
    assert buyer.findings[0].recommendation!=seller.findings[0].recommendation


@pytest.mark.parametrize('text,expected,forbidden',[
    ('供应商决定不续约，应提前90天通知客户。','供应商不续约','客户不续约通知属于客户义务'),
    ('客户有权涨价，应提前15天通知供应商。','客户涨价','供应商涨价通知属于供应商义务'),
    ('不续约需提前15天通知。','义务主体待确认','客户不续约通知属于客户义务')])
def test_obligation_subject_must_match_original(tmp_path,text,expected,forbidden):
    run=execute(prepared(tmp_path,paragraphs=['虚构样本',text]))
    analyses=[f.analysis for f in run.findings if f.issue_type=='obligation_direction']
    assert any(expected in x for x in analyses) and all(forbidden not in x for x in analyses)


def test_same_anchor_multiple_obligations_preserved(tmp_path):
    run=execute(prepared(tmp_path,paragraphs=['虚构样本','供应商涨价提前90天通知客户；客户不续约提前15天通知供应商。']))
    analyses=[f.analysis for f in run.findings if f.issue_type=='obligation_direction']
    assert len(analyses)==2 and any('供应商涨价' in x for x in analyses) and any('客户不续约' in x for x in analyses)


def test_named_missing_appendices_are_listed(tmp_path):
    run=execute(prepared(tmp_path,paragraphs=['虚构样本','附件《测试SOW甲》约定交付。','附件《测试DPA乙》约定数据范围。']))
    analyses=' '.join(f.analysis for f in run.findings if f.issue_type=='missing_appendix')
    assert '测试SOW甲' in analyses and '测试DPA乙' in analyses


@pytest.mark.parametrize('values,trap',[(('100','1e-90'),False),(('0.'+'1'*81,'20'),True),(('100','1e-300'),False)])
def test_payment_math_precision_and_global_context(tmp_path,values,trap):
    from decimal import Decimal,localcontext,Inexact
    from datetime import datetime,timezone
    from cn_contract.domain import Fact,FactSnapshot
    p,s,database,actor,matter,ctx,parsed=prepared(tmp_path,paragraphs=['虚构数学样本','付款比例应核对。'])
    with database.session() as db:
        facts=[Fact(id=uuid4(),matter_id=matter.id,version=3,field='payment_ratio_'+str(i+1),
            typed_value={'kind':'decimal','value':Decimal(v)},unit='percent',provenance_type='document',anchor_ids=(parsed.anchors[1].id,),
            receipt_ids=(),confirmation_status='confirmed',confirmed_by=actor.user_id,confirmed_at=datetime.now(timezone.utc)) for i,v in enumerate(values)]
        fs=FactSnapshot(version=3,facts=facts,sha256=p.fact_snapshot_sha256(facts));p.save_fact_snapshot(matter.id,fs,actor,db)
        p.transition_matter(matter.id,'ready_for_review',actor,db)
        ctx=ctx.model_copy(update={'matter':p.read_matter(matter.id,actor,db),'fact_snapshot':fs})
        with localcontext() as global_context:
            global_context.traps[Inexact]=trap
            run=api('workflow','run_review')(ctx,api('model_adapter','MockProvider')(),actor=actor,db=db)
        assert run.status=='completed' and len(run.model_usage)==3
        assert any(f.issue_type in ('payment_ratio_sum','payment_math_insufficient') for f in run.findings)
        if values[-1]=='1e-300':assert any(f.issue_type=='payment_math_insufficient' for f in run.findings)


@pytest.mark.parametrize('kind',['facts','documents','position','scope','rules','policy','matter'])
def test_client_context_is_not_authority(tmp_path,kind):
    p,s,database,actor,matter,ctx,parsed=prepared(tmp_path)
    values={}
    if kind=='facts': values['fact_snapshot']=ctx.fact_snapshot.model_copy(update={'sha256':'0'*64})
    if kind=='documents': values['document_versions']=()
    if kind=='position':
        from cn_contract.domain import Position
        values['position']=Position.SELLER
    if kind=='scope':
        from cn_contract.domain import CoverageId
        values['allowed_scope']=(CoverageId.C01,)
    if kind=='rules': values['rules']=()
    if kind=='policy': values['policy']=ctx.policy.model_copy(update={'sha256':'0'*64})
    if kind=='matter': values['matter']=ctx.matter.model_copy(update={'client_ref':'FORGED'})
    with database.session() as db,pytest.raises(s.ServiceError):
        api('workflow','run_review')(ctx.model_copy(update=values),api('model_adapter','MockProvider')(),actor=actor,db=db)


@pytest.mark.parametrize('field',['authority_ids','rule_ids','human_decision','analysis','anchor_ids'])
def test_forged_finding_not_certified(tmp_path,field):
    env=prepared(tmp_path);run=execute(env)
    p,s,database,actor,matter,ctx,parsed=env
    finding=run.findings[0]
    update={field:(uuid4(),)}
    if field=='analysis':update={field:'本合同必然无效；引用存在就支持所有结论。'}
    if field=='human_decision':
        from cn_contract.domain import HumanDecision
        from datetime import datetime,timezone
        update={field:HumanDecision(decision='accept',reason='fake',actor_id=actor.user_id,decided_at=datetime.now(timezone.utc))}
    forged=run.model_copy(update={'findings':(finding.model_copy(update=update),*run.findings[1:])})
    with database.session() as db:
        assert not api('validator','validate_findings')(forged,evidence(parsed),actor=actor,db=db).ok


def test_repair_success_accounted(tmp_path):
    p,s,database,actor,matter,ctx,parsed=prepared(tmp_path)
    with database.session() as db:
        run=api('workflow','run_review')(ctx,api('model_adapter','MockProvider')(raw_outputs=('{bad',)),actor=actor,db=db)
        attempts=api('storage','read_attempts')(matter.id,run.id,actor,db=db)
        assert run.status=='completed' and len(run.model_usage)==4
        assert attempts[0]['valid'] is False and attempts[1]['valid'] is True and attempts[1]['repair'] is True


@pytest.mark.parametrize('status',['sent_unknown','failed','blocked'])
def test_uncertain_or_failed_does_not_auto_retry(tmp_path,status):
    p,s,database,actor,matter,ctx,parsed=prepared(tmp_path)
    with database.session() as db:
        run=api('workflow','run_review')(ctx,api('model_adapter','MockProvider')(statuses=(status,)),actor=actor,db=db)
        assert run.status=='failed' and len(run.model_usage)==1
        assert run.error_code==('QUERY_STATE_UNKNOWN' if status=='sent_unknown' else 'MODEL_OUTPUT_INVALID')


@pytest.mark.parametrize('kind',['input','output'])
def test_actual_budget_caps_attempts(tmp_path,kind):
    from cn_contract.domain import ModelUsageLimit
    p,s,database,actor,matter,ctx,parsed=prepared(tmp_path)
    limit=ModelUsageLimit(max_input_tokens=0 if kind=='input' else 1000000,max_output_tokens=1,max_cost='0',unit='mock_credit')
    with database.session() as db:
        run=api('workflow','run_review')(ctx,api('model_adapter','MockProvider')(),actor=actor,db=db,usage_limit=limit)
        assert run.error_code=='BUDGET_EXCEEDED'
        assert len(run.model_usage)==(0 if kind=='input' else 1)


def test_full_legal_request_blocked(tmp_path):
    run=execute(prepared(tmp_path),require_legal_rules=True)
    assert run.status=='failed' and run.error_code=='RULE_UNAPPROVED' and not run.model_usage


def test_postrun_material_change_makes_read_stale(tmp_path):
    env=prepared(tmp_path);run=execute(env)
    p,s,database,actor,matter,ctx,parsed=env
    with database.session() as db:
        p.set_position(matter.id,'seller',actor,db)
    with database.session() as db:
        with pytest.raises(s.ServiceError): api('storage','read_run')(matter.id,run.id,actor,db=db)
        assert api('storage','read_run')(matter.id,run.id,actor,db=db,current=False)==run


@pytest.mark.parametrize('kind',['unknown','foreign','labor'])
def test_specialist_scope_is_explicit(tmp_path,kind):
    env=prepared(tmp_path,contract_type='unknown' if kind=='unknown' else 'sales')
    p,s,database,actor,matter,ctx,parsed=env
    if kind=='foreign':
        import json
        from cn_contract.domain import Matter
        with database.session() as db:
            row=db.get(p.MatterRow,str(matter.id));payload=json.loads(row.payload);payload['jurisdiction']='HK'
            row.payload=Matter.model_validate(payload).model_dump_json()
            ctx=ctx.model_copy(update={'matter':p.read_matter(matter.id,actor,db)})
    if kind=='labor':
        from cn_contract.domain import Fact,FactSnapshot
        from datetime import datetime,timezone
        with database.session() as db:
            facts=[f.model_copy(update={'version':3}) for f in ctx.fact_snapshot.facts]
            facts.append(Fact(id=uuid4(),matter_id=matter.id,version=3,field='labor_relationship',typed_value={'kind':'bool','value':True},
                unit=None,provenance_type='client_statement',anchor_ids=(),receipt_ids=(),confirmation_status='confirmed',confirmed_by=actor.user_id,confirmed_at=datetime.now(timezone.utc)))
            fs=FactSnapshot(version=3,facts=facts,sha256=p.fact_snapshot_sha256(facts));p.save_fact_snapshot(matter.id,fs,actor,db)
            p.transition_matter(matter.id,'ready_for_review',actor,db)
            ctx=ctx.model_copy(update={'matter':p.read_matter(matter.id,actor,db),'fact_snapshot':fs})
    with database.session() as db:
        run=api('workflow','run_review')(ctx,api('model_adapter','MockProvider')(),actor=actor,db=db)
        assert any(c.status=='unsupported' for c in run.coverage)
