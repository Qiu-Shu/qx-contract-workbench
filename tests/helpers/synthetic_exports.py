"""Independent fictional T09 DOCX; actual ingest/confirm/review/backend identities."""
from hashlib import sha256
import importlib
from uuid import uuid4
from unittest.mock import patch as substitute_fixture
from cn_contract.domain import Patch,Role,EvidenceBundle
from tests.helpers.synthetic_documents import docx
from tests.helpers.synthetic_review import prepare

W='http://schemas.openxmlformats.org/wordprocessingml/2006/main'
QUOTE='供应商另行提供 履约保证。 '
NEW='供应商按双方另行确认的书面附件提供履约保证。 '
BODY=('<w:p><w:r><w:t>独立虚构合同修订演示</w:t></w:r></w:p>'
 '<w:p><w:r><w:t>价款：101元。</w:t></w:r></w:p>'
 '<w:p><w:r><w:rPr><w:b/></w:rPr><w:t>供应商另行</w:t></w:r>'
 '<w:r><w:rPr><w:i/></w:rPr><w:t xml:space="preserve">提供 </w:t></w:r>'
 '<w:r><w:rPr><w:color w:val="000000"/></w:rPr><w:t xml:space="preserve">履约保证。 </w:t></w:r></w:p>'
 '<w:p><w:r><w:t xml:space="preserve">供应商另行提供 履约保证。 </w:t></w:r></w:p>'
 '<w:p><w:r><w:t>资料要求详见附件清单。</w:t></w:r></w:p>')


def api(name='approvals'):
    try: result=importlib.import_module('cn_contract.exports.'+name)
    except ModuleNotFoundError as error:
        assert error.name not in {'cn_contract.exports','cn_contract.exports.'+name}, 'T09 protected exact export service required'
        raise
    return result


def setup(tmp_path,*,body=BODY,extras=None,reader=False,second_document=False):
    with substitute_fixture('tests.helpers.synthetic_review.docx',lambda _:docx(body,extras=extras)):
        p,security,database,actor,matter,context,parsed=prepare(tmp_path)
    from cn_contract.review.workflow import run_review
    from cn_contract.review.model_adapter import MockProvider
    from cn_contract.review.validator import validate_findings
    extra_anchors=[]
    with database.session() as db:
        reviewer_id=security.provision_user('synthetic-t09-reviewer','local-test-password',{Role.REVIEWING_LAWYER},db)
        security.set_membership(matter.id,reviewer_id,db,can_sign=True)
        token,_=security.login('synthetic-t09-reviewer','local-test-password',db)
        reviewer=security.authenticate(token,db)
        if reader:
            identifier=security.provision_user('synthetic-t09-reader','local-test-password',{Role.ASSISTANT},db)
            security.set_membership(matter.id,identifier,db,can_sign=False)
            reader_token,_=security.login('synthetic-t09-reader','local-test-password',db)
            database._synthetic_t09_reader=security.authenticate(reader_token,db)
        if second_document:
            from io import BytesIO
            from cn_contract.domain import UploadMeta
            from cn_contract.documents import ingest,parse_document
            meta=UploadMeta(matter_id=matter.id,original_name='synthetic_second.docx',mime='application/vnd.openxmlformats-officedocument.wordprocessingml.document',baseline_view=None,supersedes_id=None)
            second=ingest(BytesIO(docx(BODY)),meta,actor,db=db)
            second_parsed=parse_document(second,None,actor=actor,db=db)
            extra_anchors.extend(second_parsed.anchors)
            for state in ('parsed','awaiting_fact_confirmation','ready_for_review'):
                p.transition_matter(matter.id,state,actor,db)
            context=context.model_copy(update={'document_versions':(*context.document_versions,second)})
        context=context.model_copy(update={'matter':p.read_matter(matter.id,actor,db)})
        run=run_review(context,MockProvider(),actor=actor,db=db)
        assert run.status=='completed'
        evidence=EvidenceBundle(anchors={a.id:a for a in (*parsed.anchors,*extra_anchors)},authorities={},receipts={})
        assert validate_findings(run,evidence,actor=actor,db=db).ok
    return database,actor,reviewer,matter,context,parsed,run


def suggestion(world,*,anchor_index=2,old=None):
    _,_,_,_,context,parsed,run=world
    anchor=parsed.anchors[anchor_index]
    finding=next(f for f in run.findings if anchor.id in (*f.anchor_ids,*f.cross_anchor_ids))
    text=anchor.quote if old is None else old
    return Patch(id=uuid4(),finding_id=finding.id,document_version_id=context.document_versions[0].id,
        anchor_id=anchor.id,old_text=text,new_text=NEW,old_text_sha256=sha256(text.encode()).hexdigest(),
        status='proposed',reason='独立虚构示例 建议补充保证附件的书面确认',approved_by=None)


def approved(world,value,*,audiences=('internal','client','counterparty')):
    database,_,reviewer,matter,_,_,run=world
    with database.session() as db:
        api('storage').initialize_storage(database)
        return api().approve_patch(matter.id,run.id,value,reviewer,db=db,audiences=audiences)


def package(world,audience='internal',patches=None):
    database,actor,_,_,_,_,run=world
    api('storage').initialize_storage(database)
    with database.session() as db:
        return api().prepare_exports(run,audience,patches or [],actor,db=db)
