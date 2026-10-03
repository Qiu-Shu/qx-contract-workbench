"""T06 standalone imaginary input and actual server confirmation utilities."""
from io import BytesIO
from uuid import uuid4
from xml.sax.saxutils import escape
from cn_contract.domain import (CoverageId,FactDecision,FactSnapshot,PolicySnapshot,ReviewContext,UploadMeta,Matter)
from tests.helpers.synthetic_documents import world,docx,DOCX_MIME


def prepare(tmp_path,*,paragraphs=None,mode='pre_sign',contract_type='sales',position='buyer'):
    import cn_contract.persistence as p
    import cn_contract.security as s
    from cn_contract.authorities.storage import initialize_storage as authorities_init
    from cn_contract.facts.storage import initialize_storage as facts_init
    from cn_contract.rules.storage import initialize_storage as rules_init,policy_sha256
    from cn_contract.rules.loader import save_policy,register_default_cards,read_rule_snapshot
    from cn_contract.documents import ingest,parse_document
    from cn_contract.facts.confirm import confirm_facts
    from cn_contract.review.storage import initialize_storage
    from cn_contract.review.model_adapter import MockProvider
    from cn_contract.review.workflow import extract_document_candidates
    p,s,a,database,actor,initial=world(tmp_path)
    authorities_init(database);rules_init(database);facts_init(database);initialize_storage(database)
    with database.session() as db:
        matter=Matter(**{**initial.model_dump(mode='python'),'id':uuid4(),'review_mode':mode,'contract_type':contract_type,'position':position})
        p.provision_matter(matter,db)
        register_default_cards(actor,matter_id=matter.id,db=db)
        policy=PolicySnapshot(client_ref=matter.client_ref,version=1,sha256=policy_sha256(matter.client_ref,1,()),
            preferences=(),approved_by=None,approved_at=None)
        save_policy(policy,actor,matter_id=matter.id,db=db)
        paragraphs=paragraphs or ['独立虚构T06合同','价款：101元。','付款比例：60%。','付款比例：50%。']
        data=docx(''.join('<w:p><w:r><w:t>'+escape(t)+'</w:t></w:r></w:p>' for t in paragraphs))
        version=ingest(BytesIO(data),UploadMeta(matter_id=matter.id,original_name='SYNTHETIC-T06.docx',mime=DOCX_MIME,
            baseline_view=None,supersedes_id=None),actor,db=db)
        parsed=parse_document(version,None,actor=actor,db=db)
        facts=extract_document_candidates(parsed,MockProvider(),matter_id=matter.id,actor=actor,db=db)
        fs=FactSnapshot(version=1,facts=facts,sha256=p.fact_snapshot_sha256(facts))
        p.save_fact_snapshot(matter.id,fs,actor,db)
        fs=confirm_facts(matter.id,1,[FactDecision(fact_id=f.id,decision='confirmed',confirmed_value=f.typed_value,
            reason='SYNTHETIC test role confirms fictional text; no real lawyer approval') for f in facts],actor,db=db)
        p.transition_matter(matter.id,'ready_for_review',actor,db)
        current=p.read_matter(matter.id,actor,db)
        snapshot=read_rule_snapshot(actor,matter_id=matter.id,db=db)
        context=ReviewContext(matter=current,document_versions=(version,),fact_snapshot=fs,position=current.position,
            rules=snapshot.rules,policy=policy,authority_ids=(),allowed_scope=tuple(CoverageId))
    return p,s,database,actor,matter,context,parsed
