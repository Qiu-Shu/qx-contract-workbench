"""Real local PDF attachment receipts and the frozen synthetic task bridge."""
import hashlib
from io import BytesIO
from pathlib import Path
import struct
from uuid import uuid4

import pytest
from sqlalchemy import text

from cn_contract import domain as d
from cn_contract.assistant import attachments
from cn_contract.persistence import get_parse_result, read_original
from cn_contract.security import ServiceError
from cn_contract.task_drafts import bridge, service
from tests.helpers.synthetic_documents import pdf
from test_pdf_visual_trust import visual_pdf, VISIBLE, SECOND
from test_assistant_storage import workspace, conversation


@pytest.fixture
def pdf_workspace(workspace):
    from cn_contract.storage_bootstrap import initialize_storage
    initialize_storage(workspace[0])
    return workspace, conversation(workspace)


def upload_pdf(pdf_workspace, raw, *, local=False):
    workspace, value = pdf_workspace
    database, actors, _, _ = workspace
    cid = value.scope.conversation_id
    if local:
        database._local_materials_enabled = True
    database._assistant_synthetic_hashes = set(getattr(database, '_assistant_synthetic_hashes', ())) | {
        hashlib.sha256(raw).hexdigest()}
    current = attachments.read_materials(actors['lawyer'], cid, database=database)
    return attachments.ingest_attachment(actors['lawyer'], cid, d.AssistantAttachmentInput(
        request_id=uuid4(), expected_scope=current.scope, original_name='SYNTHETIC-task.pdf',
        mime='application/pdf', policy=d.AssistantMaterialPolicy(policy_id='assistant-local-files-v2',
            material_mode='local' if local else 'synthetic', local_processing_accepted=True)),
        BytesIO(raw), database=database)


def parse_pdf_attachment(pdf_workspace, uploaded, *, baseline=None, request_id=None):
    workspace, value = pdf_workspace
    database, actors, _, _ = workspace
    current = attachments.read_materials(actors['lawyer'], value.scope.conversation_id, database=database)
    request = d.AssistantAttachmentParseInput(request_id=request_id or uuid4(),
        expected_scope=current.scope, baseline_view=baseline)
    return attachments.parse_attachment(actors['lawyer'], value.scope.conversation_id,
        uploaded.attachment.id, request, database=database), request


def collect_pdf(pdf_workspace, uploaded, parsed):
    workspace, value = pdf_workspace
    database, actors, _, _ = workspace
    file = uploaded.attachment
    with database.session() as db:
        binding = service.create_binding(actors['lawyer'], value.scope.conversation_id, db)
        received = service.receive_batch(actors['lawyer'], binding.id, d.TaskInboxBatchInput(
            expected_cursor=0, next_cursor=1, events=(d.TaskInboxEventInput(event_id='pdf-1',
                text='核对独立虚构PDF合同', media=(d.TaskMediaInput(media_id='pdf-file',
                    name=file.original_name, mime=file.mime, status='ready', attachment_id=file.id,
                    sha256=file.sha256, parse_revision=parsed.parse.revision),)),)), db)
        return received.drafts[0]


def freeze_pdf(pdf_workspace, draft):
    workspace, _ = pdf_workspace
    database, actors, _, _ = workspace
    with database.session() as db:
        return service.freeze_draft(actors['lawyer'], draft.id,
            d.TaskFreezeInput(expected_revision=draft.revision, manifest_sha256=draft.manifest_sha256), db)


def test_pdf_attachment_reads_all_pages_and_preserves_exact_anchors(pdf_workspace):
    raw = pdf(['SYNTHETIC Buyer owes CNY 13750', 'SYNTHETIC prepaid CNY 20000'])
    uploaded = upload_pdf(pdf_workspace, raw)
    receipt, _ = parse_pdf_attachment(pdf_workspace, uploaded)
    parsed = receipt.parse
    assert parsed.reading_status == 'readable'
    assert parsed.baseline_view == 'original'
    assert parsed.parser_version == 'qx-pdf-attachments-v1'
    assert parsed.result.pages == (1, 2)
    assert [(a.page, a.quote) for a in parsed.result.anchors] == [
        (1, 'SYNTHETIC Buyer owes CNY 13750'), (2, 'SYNTHETIC prepaid CNY 20000')]
    assert all(a.kind == 'pdf_span' and a.bbox and a.document_version_id == uploaded.attachment.id
               for a in parsed.result.anchors)


def test_pdf_parse_replay_is_one_revision_and_reparse_preserves_history(pdf_workspace):
    uploaded = upload_pdf(pdf_workspace, pdf(['SYNTHETIC immutable text']))
    first, request = parse_pdf_attachment(pdf_workspace, uploaded)
    workspace, value = pdf_workspace
    database, actors, _, _ = workspace
    repeated = attachments.parse_attachment(actors['lawyer'], value.scope.conversation_id,
        uploaded.attachment.id, request, database=database)
    assert repeated == first
    second, _ = parse_pdf_attachment(pdf_workspace, uploaded, baseline='original')
    assert second.parse.revision == 2 and first.parse.revision == 1
    assert second.parse.result == first.parse.result
    assert attachments.read_parse(actors['lawyer'], value.scope.conversation_id,
        uploaded.attachment.id, 1, database=database) == first.parse
    with database.session() as db:
        assert db.scalar(text('SELECT count(*) FROM assistant_attachment_parses')) == 2


def test_complete_pdf_is_a_freezable_main_contract(pdf_workspace):
    uploaded = upload_pdf(pdf_workspace, pdf(['SYNTHETIC complete contract']))
    parsed, _ = parse_pdf_attachment(pdf_workspace, uploaded)
    draft = collect_pdf(pdf_workspace, uploaded, parsed)
    assert draft.blockers == ()
    assert draft.main_attachment_id == uploaded.attachment.id
    execution = freeze_pdf(pdf_workspace, draft)
    assert execution.state == 'prepared'
    assert execution.manifest.events[0].media[0].reading_status == 'readable'


def test_preparation_copies_pdf_bytes_and_rebinds_page_anchors_to_case_version(pdf_workspace):
    from cn_contract.matters import create_matter
    raw = pdf(['SYNTHETIC first page', 'SYNTHETIC final page'])
    uploaded = upload_pdf(pdf_workspace, raw)
    parsed, _ = parse_pdf_attachment(pdf_workspace, uploaded)
    execution = freeze_pdf(pdf_workspace, collect_pdf(pdf_workspace, uploaded, parsed))
    workspace, _ = pdf_workspace
    database, actors, _, _ = workspace
    with database.session() as db:
        matter = create_matter(d.MatterCreateInput(title='独立合成PDF桥接', contract_type='sales',
            review_mode='pre_sign', position='buyer', objectives=('核对虚构PDF',)), actors['lawyer'], db)
        request = d.TaskExecutionPrepareInput(request_id=uuid4(), matter_id=matter.id)
        prepared = bridge.prepare_execution(actors['lawyer'], execution.id, request, db=db)
        version_id = prepared.source_versions[uploaded.attachment.id]
        assert read_original(matter.id, version_id, actors['lawyer'], db) == raw
        actual = get_parse_result(matter.id, version_id, actors['lawyer'], db)
        assert actual.pages == (1, 2)
        assert [(a.page, a.bbox, a.quote) for a in actual.anchors] == [
            (a.page, a.bbox, a.quote) for a in parsed.parse.result.anchors]
        assert {a.id for a in actual.anchors}.isdisjoint(a.id for a in parsed.parse.result.anchors)
        assert all(a.document_version_id == version_id for a in actual.anchors)
        assert bridge.prepare_execution(actors['lawyer'], execution.id, request, db=db) == prepared
        assert db.scalar(text('SELECT count(*) FROM document_versions')) == 1
        assert db.scalar(text('SELECT count(*) FROM assistant_runs')) == 0


@pytest.mark.parametrize('pages', [[None], ['SYNTHETIC read page', None, 'SYNTHETIC tail']])
def test_unread_pdf_pages_remain_partial_and_cannot_freeze(pdf_workspace, pages):
    uploaded = upload_pdf(pdf_workspace, pdf(pages))
    parsed, _ = parse_pdf_attachment(pdf_workspace, uploaded)
    assert parsed.parse.reading_status == 'partial'
    assert any(issue.startswith('OCR_NOT_DEPLOYED:page:') for issue in parsed.parse.result.quality_issues)
    assert parsed.parse.result.pages == tuple(range(1, len(pages) + 1))
    draft = collect_pdf(pdf_workspace, uploaded, parsed)
    assert 'media_not_readable' in draft.blockers
    with pytest.raises(ServiceError):
        freeze_pdf(pdf_workspace, draft)
    with pdf_workspace[0][0].session() as db:
        assert db.scalar(text('SELECT count(*) FROM task_executions')) == 0


def test_pdf_annotation_is_retained_as_unread_and_blocks_task(pdf_workspace):
    raw = pdf(['SYNTHETIC displayed contract'], b'<< /Type /Annot /Subtype /Text '
        b'/Rect [72 600 300 650] /Contents (SYNTHETIC added payment) >>')
    uploaded = upload_pdf(pdf_workspace, raw)
    parsed, _ = parse_pdf_attachment(pdf_workspace, uploaded)
    assert parsed.parse.reading_status == 'partial'
    assert 'ANNOTATIONS_NOT_READ:page:1' in parsed.parse.result.quality_issues
    assert parsed.parse.result.anchors[0].quote == 'SYNTHETIC displayed contract'
    draft = collect_pdf(pdf_workspace, uploaded, parsed)
    assert 'media_not_readable' in draft.blockers
    with pytest.raises(ServiceError):
        freeze_pdf(pdf_workspace, draft)


@pytest.mark.parametrize('baseline', ['accepted_view', 'rejected_view', 'confirmed_custom'])
def test_pdf_never_uses_a_docx_revision_baseline(pdf_workspace, baseline):
    uploaded = upload_pdf(pdf_workspace, pdf(['SYNTHETIC original PDF']))
    with pytest.raises(ServiceError) as error:
        parse_pdf_attachment(pdf_workspace, uploaded, baseline=baseline)
    assert error.value.code == 'BASELINE_REQUIRED'
    with pdf_workspace[0][0].session() as db:
        assert db.scalar(text('SELECT count(*) FROM assistant_attachment_parses')) == 0


def test_malformed_pdf_parse_keeps_failed_idempotent_receipt_and_original(pdf_workspace):
    raw = b'%PDF-1.4\nSYNTHETIC deliberately damaged PDF\n%%EOF\n'
    uploaded = upload_pdf(pdf_workspace, raw)
    receipt, request = parse_pdf_attachment(pdf_workspace, uploaded)
    assert receipt.parse.reading_status == 'failed'
    assert receipt.parse.result is receipt.parse.result_sha256 is None
    assert receipt.parse.failure_code == 'PARSE_FAILED'
    workspace, value = pdf_workspace
    database, actors, _, _ = workspace
    assert attachments.read_original(actors['lawyer'], value.scope.conversation_id,
        uploaded.attachment.id, database=database) == raw
    assert attachments.parse_attachment(actors['lawyer'], value.scope.conversation_id,
        uploaded.attachment.id, request, database=database) == receipt


def test_local_pdf_cannot_prepare_as_registered_synthetic_task(pdf_workspace):
    from cn_contract.matters import create_matter
    uploaded = upload_pdf(pdf_workspace, pdf(['SYNTHETIC local policy test']), local=True)
    parsed, _ = parse_pdf_attachment(pdf_workspace, uploaded)
    execution = freeze_pdf(pdf_workspace, collect_pdf(pdf_workspace, uploaded, parsed))
    workspace, _ = pdf_workspace
    database, actors, _, _ = workspace
    with database.session() as db:
        matter = create_matter(d.MatterCreateInput(title='独立合成策略拒绝', contract_type='sales',
            review_mode='pre_sign', position='buyer', objectives=('策略验收',)), actors['lawyer'], db)
        with pytest.raises(ServiceError) as error:
            bridge.prepare_execution(actors['lawyer'], execution.id,
                d.TaskExecutionPrepareInput(request_id=uuid4(), matter_id=matter.id), db=db)
        assert error.value.code == 'DATA_POLICY_UNAPPROVED'
        assert db.scalar(text('SELECT count(*) FROM document_versions')) == 0
        assert service.read_execution(actors['lawyer'], execution.id, db).state == 'prepared'


@pytest.mark.parametrize('raw,issue', [
    (visual_pdf(VISIBLE + b'1 g\n' + SECOND), 'PDF_TEXT_COLOR_REQUIRES_CONFIRMATION:page:1'),
    (visual_pdf(VISIBLE + SECOND + b'1 g 70 675 230 18 re f\n'), 'PDF_TEXT_OCCLUSION_REQUIRES_CONFIRMATION:page:1'),
    (visual_pdf(VISIBLE + SECOND, crop=b'0 700 612 792'), 'PDF_TEXT_OUTSIDE_VISIBLE_PAGE:page:1'),
    (visual_pdf(VISIBLE + SECOND + b'q 40 0 0 40 200 600 cm /Im1 Do Q\n', image=True),
        'VISIBLE_IMAGE_TEXT_NOT_VERIFIED:page:1'),
], ids=['white-text', 'text-occluded', 'cropped-text', 'displayed-image'])
def test_visually_untrusted_pdf_text_cannot_become_a_ready_contract(pdf_workspace, raw, issue):
    uploaded = upload_pdf(pdf_workspace, raw)
    parsed, _ = parse_pdf_attachment(pdf_workspace, uploaded)
    assert parsed.parse.reading_status == 'partial'
    assert issue in parsed.parse.result.quality_issues
    assert parsed.parse.result.anchors
    draft = collect_pdf(pdf_workspace, uploaded, parsed)
    assert 'media_not_readable' in draft.blockers
    with pytest.raises(ServiceError):
        freeze_pdf(pdf_workspace, draft)


def test_pdf_page_cap_is_a_failed_receipt_without_partial_acceptance(pdf_workspace):
    database = pdf_workspace[0][0]
    database.settings = database.settings.model_copy(update={'parse_max_pages_per_file': 1})
    uploaded = upload_pdf(pdf_workspace, pdf(['SYNTHETIC one', 'SYNTHETIC over limit']))
    parsed, _ = parse_pdf_attachment(pdf_workspace, uploaded)
    assert parsed.parse.reading_status == 'failed'
    assert parsed.parse.result is parsed.parse.result_sha256 is None
    assert parsed.parse.failure_code == 'PARSE_FAILED'
    draft = collect_pdf(pdf_workspace, uploaded, parsed)
    assert 'media_not_readable' in draft.blockers
    with pytest.raises(ServiceError):
        freeze_pdf(pdf_workspace, draft)


def _encrypted_pdf():
    """Independent R2/40-bit encryption, with an empty user password and real ciphertext."""
    from pdfminer.arcfour import Arcfour
    padding = bytes.fromhex('28bf4e5e4e758a4164004e56fffa01082e2e00b6d0683e802f0ca9fe6453697a')
    owner = Arcfour(hashlib.md5((b'SYNTHETIC-owner'+padding)[:32]).digest()[:5]).encrypt(padding)
    identifier = b'SYNTHETIC-PDF-ID'
    key = hashlib.md5(padding+owner+struct.pack('<i', -4)+identifier).digest()[:5]
    user = Arcfour(key).encrypt(padding)
    object_key = hashlib.md5(key+b'\x05\x00\x00\x00\x00').digest()[:10]
    content = Arcfour(object_key).encrypt(b'BT /F1 12 Tf 72 720 Td (SYNTHETIC protected text) Tj ET')
    objects = [b'<< /Type /Catalog /Pages 2 0 R >>',
        b'<< /Type /Pages /Kids [4 0 R] /Count 1 >>',
        b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
        b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] '
        b'/Resources << /Font << /F1 3 0 R >> >> /Contents 5 0 R >>',
        b'<< /Length '+str(len(content)).encode()+b' >>\nstream\n'+content+b'\nendstream',
        b'<< /Filter /Standard /V 1 /R 2 /Length 40 /P -4 /O <'+owner.hex().encode()+
        b'> /U <'+user.hex().encode()+b'> >>']
    raw, offsets = bytearray(b'%PDF-1.4\n'), [0]
    for number, obj in enumerate(objects, 1):
        offsets.append(len(raw))
        raw.extend(f'{number} 0 obj\n'.encode()+obj+b'\nendobj\n')
    start = len(raw)
    raw.extend(b'xref\n0 7\n0000000000 65535 f \n')
    for offset in offsets[1:]:
        raw.extend(f'{offset:010d} 00000 n \n'.encode())
    identity = identifier.hex().encode()
    raw.extend(b'trailer\n<< /Size 7 /Root 1 0 R /Encrypt 6 0 R /ID [<'+identity+b'><'+identity+
        b'>] >>\nstartxref\n'+str(start).encode()+b'\n%%EOF\n')
    return bytes(raw)


def test_valid_encrypted_pdf_remains_failed_even_when_empty_password_opens_it(pdf_workspace):
    import pdfplumber
    raw = _encrypted_pdf()
    with pdfplumber.open(BytesIO(raw)) as control:
        assert control.pages[0].extract_text() == 'SYNTHETIC protected text'
        assert control.doc.encryption
    uploaded = upload_pdf(pdf_workspace, raw)
    parsed, _ = parse_pdf_attachment(pdf_workspace, uploaded)
    assert parsed.parse.reading_status == 'failed'
    assert parsed.parse.result is None
    draft = collect_pdf(pdf_workspace, uploaded, parsed)
    assert 'media_not_readable' in draft.blockers
    with pytest.raises(ServiceError):
        freeze_pdf(pdf_workspace, draft)


def test_current_registry_revocation_blocks_frozen_pdf_before_copy(pdf_workspace):
    from cn_contract.matters import create_matter
    uploaded = upload_pdf(pdf_workspace, pdf(['SYNTHETIC revoke me']))
    parsed, _ = parse_pdf_attachment(pdf_workspace, uploaded)
    execution = freeze_pdf(pdf_workspace, collect_pdf(pdf_workspace, uploaded, parsed))
    workspace, _ = pdf_workspace
    database, actors, _, _ = workspace
    database._assistant_synthetic_hashes = frozenset()
    with database.session() as db:
        matter = create_matter(d.MatterCreateInput(title='独立合成PDF来源撤销', contract_type='sales',
            review_mode='pre_sign', position='buyer', objectives=('拒绝未登记原件',)), actors['lawyer'], db)
        with pytest.raises(ServiceError) as error:
            bridge.prepare_execution(actors['lawyer'], execution.id,
                d.TaskExecutionPrepareInput(request_id=uuid4(), matter_id=matter.id), db=db)
        assert error.value.code == 'DATA_POLICY_UNAPPROVED'
        assert db.scalar(text('SELECT count(*) FROM document_versions')) == 0


def test_pdf_parse_requires_current_owner_even_for_saved_request(pdf_workspace):
    uploaded = upload_pdf(pdf_workspace, pdf(['SYNTHETIC private PDF']))
    _, request = parse_pdf_attachment(pdf_workspace, uploaded)
    workspace, value = pdf_workspace
    database, actors, _, _ = workspace
    with pytest.raises(ServiceError) as error:
        attachments.parse_attachment(actors['reviewer'], value.scope.conversation_id,
            uploaded.attachment.id, request, database=database)
    assert error.value.status_code == 403
    with database.session() as db:
        assert db.scalar(text('SELECT count(*) FROM assistant_attachment_parses')) == 1


def test_chinese_pdf_requires_human_facts_then_saves_one_mock_in_assisted_mode(pdf_workspace):
    from cn_contract.acceptance.assisted_registry import load_seed_policy
    from cn_contract.facts.confirm import confirm_facts
    from cn_contract.matters import create_matter
    from cn_contract.persistence import get_fact_snapshot, read_matter, transition_matter
    from cn_contract.review import proposals
    from cn_contract.review.storage import read_run
    raw = (Path(__file__).parents[2] / 'tests/fixtures/task-pdf-v1/native-sales.pdf').read_bytes()
    uploaded = upload_pdf(pdf_workspace, raw)
    parsed, _ = parse_pdf_attachment(pdf_workspace, uploaded)
    execution = freeze_pdf(pdf_workspace, collect_pdf(pdf_workspace, uploaded, parsed))
    workspace, _ = pdf_workspace
    database, actors, _, _ = workspace
    actor = actors['lawyer']
    proposals.configure(database, 'assisted_draft', load_seed_policy())
    with database.session() as db:
        matter = create_matter(d.MatterCreateInput(title='合成PDF人工事实及模拟审查', contract_type='sales',
            review_mode='pre_sign', position='buyer', objectives=('核对虚构金额',)), actor, db)
        prepared = bridge.prepare_execution(actor, execution.id,
            d.TaskExecutionPrepareInput(request_id=uuid4(), matter_id=matter.id), db=db)
        current = read_matter(matter.id, actor, db)
        facts = get_fact_snapshot(matter.id, current.active_fact_version, actor, db)
        assert facts.facts and all(f.confirmation_status == 'unconfirmed' for f in facts.facts)
        assert any(f.field == 'total_price' and str(f.typed_value.value) == '13750' for f in facts.facts)
        value = d.TaskExecutionReviewInput(request_id=uuid4(), review=d.ReviewStartInput(
            fact_version=facts.version, document_hashes=prepared.document_versions))
        with pytest.raises(ServiceError):
            bridge.review_execution(actor, execution.id, value, db=db)
        assert db.scalar(text('SELECT count(*) FROM review_runs')) == 0
        confirmed = confirm_facts(matter.id, facts.version, tuple(d.FactDecision(fact_id=f.id,
            decision='confirmed', confirmed_value=f.typed_value, reason='测试者明确核对独立虚构PDF原文')
            for f in facts.facts), actor, db=db)
        transition_matter(matter.id, 'ready_for_review', actor, db)
        approved = d.TaskExecutionReviewInput(request_id=uuid4(), review=d.ReviewStartInput(
            fact_version=confirmed.version, document_hashes=prepared.document_versions))
        completed = bridge.review_execution(actor, execution.id, approved, db=db)
        assert completed.state == 'completed'
        assert proposals.is_assisted(db)
        assert read_run(matter.id, completed.review_run_id, actor, db=db).manifest.model_provider == 'mock'
        assert bridge.review_execution(actor, execution.id, approved, db=db).review_run_id == completed.review_run_id
        assert db.scalar(text('SELECT count(*) FROM review_runs')) == 1
        assert db.scalar(text('SELECT count(*) FROM assistant_runs')) == 0


@pytest.mark.parametrize('main', ['pdf', 'docx'])
def test_mixed_pdf_docx_task_requires_main_choice_and_preserves_both_sources(pdf_workspace, main):
    from cn_contract.documents.ingest import DOCX_MIME
    from cn_contract.matters import create_matter
    from cn_contract.review.synthetic import select_fixture
    pdf_raw = pdf(['SYNTHETIC PDF appendix'])
    pdf_source = upload_pdf(pdf_workspace, pdf_raw)
    pdf_parsed, _ = parse_pdf_attachment(pdf_workspace, pdf_source)
    draft = collect_pdf(pdf_workspace, pdf_source, pdf_parsed)
    workspace, value = pdf_workspace
    database, actors, _, _ = workspace
    actor, cid = actors['lawyer'], value.scope.conversation_id
    _, _, path, docx_raw = select_fixture('sales')
    database._assistant_synthetic_hashes.add(hashlib.sha256(docx_raw).hexdigest())
    current = attachments.read_materials(actor, cid, database=database)
    docx_source = attachments.ingest_attachment(actor, cid, d.AssistantAttachmentInput(
        request_id=uuid4(), expected_scope=current.scope, original_name=path.name, mime=DOCX_MIME,
        policy=d.AssistantMaterialPolicy(local_processing_accepted=True)), BytesIO(docx_raw), database=database)
    current = attachments.read_materials(actor, cid, database=database)
    docx_parsed = attachments.parse_attachment(actor, cid, docx_source.attachment.id,
        d.AssistantAttachmentParseInput(request_id=uuid4(), expected_scope=current.scope), database=database)
    assert docx_parsed.parse.parser_version == 'qx-docx-attachments-v1'
    with database.session() as db:
        binding = service.create_binding(actor, cid, db)
        received = service.receive_batch(actor, binding.id, d.TaskInboxBatchInput(expected_cursor=1,
            next_cursor=2, events=(d.TaskInboxEventInput(event_id='docx-2', task_id=draft.id,
                media=(d.TaskMediaInput(media_id='docx', name=path.name, mime=DOCX_MIME, status='ready',
                    attachment_id=docx_source.attachment.id, sha256=docx_source.attachment.sha256,
                    parse_revision=docx_parsed.parse.revision),)),)), db)
        draft = received.drafts[0]
        assert 'main_contract_selection_required' in draft.blockers
        main_id = pdf_source.attachment.id if main == 'pdf' else docx_source.attachment.id
        draft = service.update_draft(actor, draft.id, d.TaskDraftUpdateInput(
            expected_revision=draft.revision, main_attachment_id=main_id), db)
        assert draft.blockers == ()
        execution = service.freeze_draft(actor, draft.id, d.TaskFreezeInput(
            expected_revision=draft.revision, manifest_sha256=draft.manifest_sha256), db)
        assert execution.manifest.main_attachment_id == main_id
        matter = create_matter(d.MatterCreateInput(title='合成Word与PDF共同准备', contract_type='sales',
            review_mode='pre_sign', position='buyer', objectives=('保留两份原件',)), actor, db)
        prepared = bridge.prepare_execution(actor, execution.id,
            d.TaskExecutionPrepareInput(request_id=uuid4(), matter_id=matter.id), db=db)
        assert set(prepared.source_versions) == {pdf_source.attachment.id, docx_source.attachment.id}
        assert read_original(matter.id, prepared.source_versions[pdf_source.attachment.id], actor, db) == pdf_raw
        assert read_original(matter.id, prepared.source_versions[docx_source.attachment.id], actor, db) == docx_raw
