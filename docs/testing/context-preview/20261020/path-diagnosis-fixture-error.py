import hashlib, json, traceback, uuid
from pathlib import Path
from io import BytesIO
from cn_contract.acceptance import sample_runner as s
from cn_contract.acceptance.registry import load_dataset
from cn_contract.persistence import read_matter, get_parse_result, get_fact_snapshot, transition_matter
from cn_contract.facts.confirm import confirm_facts
from cn_contract.domain import FactDecision
root=Path.cwd(); folder=root/'.local/library-context-20261020'
paths=['src/cn_contract/acceptance/sample_runner.py','src/cn_contract/persistence.py','src/cn_contract/documents/ingest.py','src/cn_contract/domain.py']
before={p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in paths}
sample=load_dataset()[0]
result={'hypotheses':[{'name':'directory depth','prediction':'same synthetic sample fails only in deep independently owned directory'}, {'name':'source/model regression','prediction':'same sample also fails in short directory'}, {'name':'shared test side effects','prediction':'isolated deep and short samples both pass'}], 'sample_id':sample.id,'inputs_before':before,'runs':[]}
for label,parent in [('short',root/'.local'/('pd-'+uuid.uuid4().hex[:8])),('deep',folder/('path-probe--'+uuid.uuid4().hex)/'test_40_samples_really_parse_c0')]:
    parent.mkdir(parents=True,exist_ok=False); work=parent/('samples-'+uuid.uuid4().hex); work.mkdir()
    database=s.Database('sqlite:///'+str(work/'protected-state.db'),work/'protected',s.load_settings())
    stage='initialize'
    item={'label':label,'root':str(work),'root_chars':len(str(work))}
    try:
        s.initialize_storage(database)
        with database.session() as db:
            s.provision_user('T11-synthetic-engineer','synthetic-local-evaluation-only',{s.Role.HANDLING_LAWYER},db)
            token,_=s.login('T11-synthetic-engineer','synthetic-local-evaluation-only',db); actor=s.authenticate(token,db)
        data=s.safe_file(sample.path,within=s.BASE)
        with database.session() as db:
            stage='create_matter'
            position={'sales':'buyer','service':'customer','lease':'lessee','nda':'recipient','unknown':'buyer'}[sample.contract_type]
            matter=s.create_matter(s.MatterCreateInput(title='T11独立虚构 '+sample.id,contract_type=sample.contract_type,review_mode='pre_sign',position=position,objectives=('仅工程材料处理，不作现实法律结论',)),actor,db)
            stage='ingest'
            version=s.ingest(BytesIO(data),s.UploadMeta(matter_id=matter.id,original_name=Path(sample.path).name,mime=s.DOCX_MIME,baseline_view='original',supersedes_id=None),actor,db=db)
            item['original_path']=str(database.storage_root/version.storage_ref);item['original_path_chars']=len(item['original_path'])
            stage='candidate_parse';s.candidate_parse(matter.id,version.id,actor,db)
            parsed=get_parse_result(matter.id,version.id,actor,db); active=read_matter(matter.id,actor,db);facts=get_fact_snapshot(matter.id,active.active_fact_version,actor,db)
            stage='confirm'
            confirmed=confirm_facts(matter.id,facts.version,[FactDecision(fact_id=f.id,decision='confirmed',confirmed_value=f.typed_value,reason='独立路径诊断，仅合成资料') for f in facts.facts],actor,db=db)
            transition_matter(matter.id,'ready_for_review',actor,db)
            stage='mock_review';run=s.run_review(s.context(matter.id,actor,db),s.MockProvider(),actor=actor,db=db)
            item.update(state='completed',parse_status=parsed.status,facts=len(confirmed.facts),coverage=len(run.coverage),run_status=run.status)
    except Exception as exc:
        item.update(state='failed',stage=stage,type=type(exc).__name__,code=getattr(exc,'code',None),message=str(exc),trace=traceback.format_exc())
    finally:database.engine.dispose()
    result['runs'].append(item)
result['inputs_after']={p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in paths}
result['inputs_unchanged']=result['inputs_before']==result['inputs_after']
(folder/'path-diagnosis-single.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
print(json.dumps(result,ensure_ascii=False,indent=2,default=str))
