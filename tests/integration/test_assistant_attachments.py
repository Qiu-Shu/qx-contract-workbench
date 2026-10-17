"""Synthetic DOCX receipts without a contract case or external processing."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
from io import BytesIO
from threading import Event
from uuid import uuid4

from docx import Document
import pytest
from sqlalchemy import text

from cn_contract import domain as d
from cn_contract.security import ServiceError
from test_assistant_storage import workspace, conversation


def sample(text_value='独立虚构材料：客户自述已支付 35000 元，尚未核对。'):
    doc = Document()
    doc.add_paragraph(text_value)
    stream = BytesIO()
    doc.save(stream)
    return stream.getvalue()


@pytest.fixture
def material_workspace(workspace):
    from cn_contract.assistant.attachment_schema import initialize_storage
    database, actors, _, _ = workspace
    initialize_storage(database)
    raw = sample()
    database._assistant_synthetic_hashes = frozenset({hashlib.sha256(raw).hexdigest()})
    value = conversation(workspace)
    request = d.AssistantAttachmentInput(request_id=uuid4(), expected_scope=value.scope,
        original_name='合成咨询材料.docx', mime='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        policy=d.AssistantMaterialPolicy(local_processing_accepted=True))
    return database, actors, value, request, raw


def test_receipt_source_reparse_selection_and_unchanged_draft(material_workspace):
    from cn_contract.assistant import attachments as a, service
    database, actors, value, request, raw = material_workspace
    actor, cid = actors['lawyer'], value.scope.conversation_id
    with database.session() as db:
        service.save_draft(actor, cid, d.AssistantDraftInput(expected_scope=value.scope,
            expected_composer_revision=0, content='我正在编辑的原话'), db)
    receipt = a.ingest_attachment(actor, cid, request, BytesIO(raw), database=database)
    assert receipt.materials_revision == 1
    assert a.read_original(actor, cid, receipt.attachment.id, database=database) == raw
    current = a.read_materials(actor, cid, database=database)
    parsed = a.parse_attachment(actor, cid, receipt.attachment.id,
        d.AssistantAttachmentParseInput(request_id=uuid4(), expected_scope=current.scope), database=database)
    assert parsed.parse.reading_status == 'readable'
    anchor = parsed.parse.result.anchors[0]
    found = a.read_excerpt(actor, cid, receipt.attachment.id, 1, anchor.id, anchor.quote_sha256, database=database)
    assert found.anchor == anchor and found.review_status == 'unverified'
    current = a.read_materials(actor, cid, database=database)
    assert current.items[0].parse_revision == 1
    parsed2 = a.parse_attachment(actor, cid, receipt.attachment.id,
        d.AssistantAttachmentParseInput(request_id=uuid4(), expected_scope=current.scope), database=database)
    assert parsed2.parse.revision == 2 and parsed2.materials_revision == 3
    current = a.read_materials(actor, cid, database=database)
    a.select_materials(actor, cid, d.AssistantMaterialSelectionInput(request_id=uuid4(),
        expected_scope=current.scope, items=()), database=database)
    assert a.read_materials(actor, cid, database=database).items == ()
    assert a.read_excerpt(actor, cid, receipt.attachment.id, 1, anchor.id, anchor.quote_sha256,
                          database=database).anchor == anchor
    with database.session() as db:
        assert service.read_conversation(actor, cid, db).draft_input == '我正在编辑的原话'
        assert db.scalar(text('SELECT COUNT(*) FROM matters')) == 0
        assert db.scalar(text('SELECT COUNT(*) FROM intake_cases')) == 0


def test_replay_precedes_versions_and_quota_and_different_content_conflicts(material_workspace):
    from cn_contract.assistant import attachments as a
    database, actors, value, request, raw = material_workspace
    database.settings = database.settings.model_copy(update={'upload_max_matter_files':1})
    cid, actor = value.scope.conversation_id, actors['lawyer']
    original = a.ingest_attachment(actor, cid, request, BytesIO(raw), database=database)
    assert a.ingest_attachment(actor, cid, request, BytesIO(raw), database=database) == original
    assert a.find_attachment_request(actor, cid, request.request_id, database=database) == original
    with pytest.raises(ServiceError) as error:
        a.ingest_attachment(actor, cid, request, BytesIO(sample('另一份独立虚构材料')), database=database)
    assert error.value.code == 'VERSION_CONFLICT'
    fresh = request.model_copy(update={'request_id':uuid4(), 'expected_scope':a.read_materials(actor,cid,database=database).scope})
    with pytest.raises(ServiceError) as error:
        a.ingest_attachment(actor, cid, fresh, BytesIO(raw), database=database)
    assert error.value.code == 'FILE_LIMIT'
    assert len(list(database.storage_root.rglob('original.bin'))) == 1


def test_bad_stream_and_wrong_type_never_commit(material_workspace):
    from cn_contract.assistant import attachments as a
    database, actors, value, request, raw = material_workspace
    for malformed in (b'%PDF-1.0', b'PK\x03\x04truncated'):
        with pytest.raises(ServiceError):
            a.ingest_attachment(actors['lawyer'], value.scope.conversation_id, request, BytesIO(malformed), database=database)
    assert a.read_materials(actors['lawyer'],value.scope.conversation_id,database=database).scope.materials_revision == 0
    assert not list(database.storage_root.rglob('original.bin'))


def test_slow_upload_releases_transaction_and_rechecks_revocation(material_workspace):
    from cn_contract.assistant import attachments as a, service
    from cn_contract.persistence import SessionRow
    database, actors, value, request, raw = material_workspace
    entered, resume = Event(), Event()
    class Slow(BytesIO):
        def read(self, size=-1):
            if not entered.is_set():
                entered.set()
                assert resume.wait(8)
            return super().read(size)
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(a.ingest_attachment, actors['lawyer'],value.scope.conversation_id,request,Slow(raw),database=database)
        assert entered.wait(8)
        try:
            with database.session() as db:
                service.save_draft(actors['lawyer'],value.scope.conversation_id,d.AssistantDraftInput(
                    expected_scope=value.scope,expected_composer_revision=0,content='读取期间仍可保存'),db)
                db.get(SessionRow,str(actors['lawyer'].session_id)).revoked=True
        finally:
            resume.set()
        with pytest.raises(ServiceError) as error:
            future.result(timeout=10)
        assert error.value.code == 'AUTHORIZATION_REQUIRED'
    assert not list(database.storage_root.rglob('original.bin'))


def test_owner_scope_and_hash_integrity(material_workspace, workspace):
    from cn_contract.assistant import attachments as a
    database, actors, value, request, raw = material_workspace
    receipt = a.ingest_attachment(actors['lawyer'], value.scope.conversation_id, request, BytesIO(raw), database=database)
    for actor, cid in ((actors['reviewer'], value.scope.conversation_id),
                       (actors['lawyer'], conversation(workspace).scope.conversation_id)):
        with pytest.raises(ServiceError) as error:
            a.read_original(actor,cid,receipt.attachment.id,database=database)
        assert error.value.status_code == 403
    path = next(database.storage_root.rglob('original.bin'))
    import stat
    path.chmod(stat.S_IREAD | stat.S_IWRITE)
    path.write_bytes(raw+b'changed')
    with pytest.raises(ServiceError) as error:
        a.read_original(actors['lawyer'],value.scope.conversation_id,receipt.attachment.id,database=database)
    assert error.value.code == 'VERSION_CONFLICT'


def test_database_failure_cleans_only_own_original(material_workspace):
    from cn_contract.assistant import attachments as a
    database, actors, value, request, raw = material_workspace
    with database.session() as db:
        db.execute(text("CREATE TRIGGER synthetic_snapshot_failure BEFORE INSERT ON assistant_material_snapshots BEGIN SELECT RAISE(ABORT,'synthetic failure'); END"))
    with pytest.raises(Exception, match='synthetic failure'):
        a.ingest_attachment(actors['lawyer'],value.scope.conversation_id,request,BytesIO(raw),database=database)
    assert not list(database.storage_root.rglob('original.bin'))
    with database.session() as db:
        assert db.scalar(text('SELECT COUNT(*) FROM assistant_attachments')) == 0
        assert db.scalar(text('SELECT materials_revision FROM assistant_conversations')) == 0


def test_concurrent_replay_creates_one_receipt(material_workspace):
    from cn_contract.assistant import attachments as a
    database, actors, value, request, raw = material_workspace
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(a.ingest_attachment,actors['lawyer'],value.scope.conversation_id,
                                   request,BytesIO(raw),database=database) for _ in range(2)]
        values = [future.result(timeout=10) for future in futures]
    assert values[0] == values[1]
    assert len(list(database.storage_root.rglob('original.bin'))) == 1


def test_parse_failure_keeps_original_and_replay_does_not_parse_twice(material_workspace,monkeypatch):
    from cn_contract.assistant import attachments as a
    database, actors, value, request, raw = material_workspace
    actor,cid = actors['lawyer'],value.scope.conversation_id
    receipt = a.ingest_attachment(actor,cid,request,BytesIO(raw),database=database)
    current = a.read_materials(actor,cid,database=database)
    parse_request = d.AssistantAttachmentParseInput(request_id=uuid4(),expected_scope=current.scope)
    calls=[]
    def fail(*args):
        calls.append(1)
        raise RuntimeError('must not expose parser internals')
    monkeypatch.setattr(a,'parse_docx',fail)
    result=a.parse_attachment(actor,cid,receipt.attachment.id,parse_request,database=database)
    assert result.parse.reading_status=='failed' and result.parse.result is None
    assert result.parse.failure_code=='PARSE_FAILED'
    assert a.parse_attachment(actor,cid,receipt.attachment.id,parse_request,database=database)==result
    assert calls==[1]
    assert a.read_original(actor,cid,receipt.attachment.id,database=database)==raw


def test_parse_outside_transaction_and_revocation_before_commit(material_workspace,monkeypatch):
    from cn_contract.assistant import attachments as a, service
    from cn_contract.persistence import SessionRow
    database, actors, value, request, raw = material_workspace
    actor,cid = actors['lawyer'],value.scope.conversation_id
    receipt=a.ingest_attachment(actor,cid,request,BytesIO(raw),database=database)
    current=a.read_materials(actor,cid,database=database)
    parser=a.parse_docx
    def interleave(*args):
        with database.session() as db:
            service.save_draft(actor,cid,d.AssistantDraftInput(expected_scope=current.scope,
                expected_composer_revision=0,content='解析期间可保存'),db)
            db.get(SessionRow,str(actor.session_id)).revoked=True
        return parser(*args)
    monkeypatch.setattr(a,'parse_docx',interleave)
    with pytest.raises(ServiceError) as error:
        a.parse_attachment(actor,cid,receipt.attachment.id,d.AssistantAttachmentParseInput(
            request_id=uuid4(),expected_scope=current.scope),database=database)
    assert error.value.status_code==401
    with database.session() as db:
        assert db.scalar(text('SELECT COUNT(*) FROM assistant_attachment_parses'))==0
        assert db.scalar(text('SELECT materials_revision FROM assistant_conversations'))==1


def test_tracked_changes_require_explicit_baseline(material_workspace):
    from cn_contract.assistant import attachments as a
    from test_docx_office_parts import edited, W
    from xml.etree import ElementTree as ET
    database, actors, value, request, raw = material_workspace
    def revision(root):
        paragraph=root.find('.//{'+W+'}p')
        addition=ET.SubElement(paragraph,'{'+W+'}ins')
        run=ET.SubElement(addition,'{'+W+'}r')
        ET.SubElement(run,'{'+W+'}t').text='（修订新增，未确认）'
    raw=edited(raw,{'word/document.xml':revision})
    database._assistant_synthetic_hashes=frozenset({hashlib.sha256(raw).hexdigest()})
    actor,cid=actors['lawyer'],value.scope.conversation_id
    receipt=a.ingest_attachment(actor,cid,request,BytesIO(raw),database=database)
    current=a.read_materials(actor,cid,database=database)
    result=a.parse_attachment(actor,cid,receipt.attachment.id,d.AssistantAttachmentParseInput(
        request_id=uuid4(),expected_scope=current.scope),database=database)
    assert result.parse.reading_status=='needs_baseline' and result.parse.result is None
    current=a.read_materials(actor,cid,database=database)
    selected=a.parse_attachment(actor,cid,receipt.attachment.id,d.AssistantAttachmentParseInput(
        request_id=uuid4(),expected_scope=current.scope,baseline_view=d.BaselineView.ACCEPTED_VIEW),database=database)
    assert selected.parse.reading_status=='partial'
    assert '修订新增' in selected.parse.result.anchors[0].quote
    assert selected.parse.review_status=='unverified'


def test_policy_and_restore_fence_before_replay(material_workspace):
    from cn_contract.assistant import attachments as a
    from cn_contract.ops.storage import RestoreFenceRow
    database, actors, value, request, raw = material_workspace
    actor,cid=actors['lawyer'],value.scope.conversation_id
    local=request.model_copy(update={'policy':d.AssistantMaterialPolicy(material_mode='local',local_processing_accepted=True)})
    with pytest.raises(ServiceError) as error:
        a.ingest_attachment(actor,cid,local,BytesIO(raw),database=database)
    assert error.value.code=='DATA_POLICY_UNAPPROVED'
    receipt=a.ingest_attachment(actor,cid,request,BytesIO(raw),database=database)
    with database.session() as db:
        db.add(RestoreFenceRow(ref=str(uuid4()),archive_sha256='a'*64,manifest_sha256='b'*64,payload='{}'))
    assert a.find_attachment_request(actor,cid,request.request_id,database=database)==receipt
    with pytest.raises(ServiceError) as error:
        a.ingest_attachment(actor,cid,request,BytesIO(raw),database=database)
    assert error.value.code=='BLOCKED_LIVE'


@pytest.mark.parametrize('failure', ['serialization', 'result_limit'])
def test_unusable_parse_result_is_failed_receipt_with_original_retained(material_workspace, monkeypatch, failure):
    from cn_contract.assistant import attachments as a
    database, actors, value, request, raw = material_workspace
    actor, cid = actors['lawyer'], value.scope.conversation_id
    receipt = a.ingest_attachment(actor, cid, request, BytesIO(raw), database=database)
    current = a.read_materials(actor, cid, database=database)
    if failure == 'serialization':
        def fail(_):
            raise ValueError('synthetic serialization failure')
        monkeypatch.setattr(a, 'canonical_json', fail)
    else:
        monkeypatch.setattr(a, 'MAX_PARSE_JSON_BYTES', 1)
    result = a.parse_attachment(actor, cid, receipt.attachment.id,
        d.AssistantAttachmentParseInput(request_id=uuid4(), expected_scope=current.scope), database=database)
    assert result.parse.reading_status == 'failed'
    assert result.parse.result is None and result.parse.result_sha256 is None
    assert result.parse.failure_code == ('PARSE_FAILED' if failure == 'serialization' else 'PARSE_RESULT_LIMIT')
    assert a.read_original(actor, cid, receipt.attachment.id, database=database) == raw


def test_parse_storage_quota_and_replay_check_original_integrity(material_workspace, monkeypatch):
    from cn_contract.assistant import attachments as a
    database, actors, value, request, raw = material_workspace
    actor, cid = actors['lawyer'], value.scope.conversation_id
    receipt = a.ingest_attachment(actor, cid, request, BytesIO(raw), database=database)
    current = a.read_materials(actor, cid, database=database)
    parse_request = d.AssistantAttachmentParseInput(request_id=uuid4(), expected_scope=current.scope)
    result = a.parse_attachment(actor, cid, receipt.attachment.id, parse_request, database=database)
    monkeypatch.setattr(a, 'MAX_CONVERSATION_PARSE_JSON_BYTES', 1)
    assert a.parse_attachment(actor, cid, receipt.attachment.id, parse_request, database=database) == result
    current = a.read_materials(actor, cid, database=database)
    with pytest.raises(ServiceError) as error:
        a.parse_attachment(actor, cid, receipt.attachment.id,
            d.AssistantAttachmentParseInput(request_id=uuid4(), expected_scope=current.scope), database=database)
    assert error.value.code == 'FILE_LIMIT'
    assert a.read_materials(actor, cid, database=database).scope == current.scope
    path = next(database.storage_root.rglob('original.bin'))
    path.chmod(0o600)
    path.write_bytes(raw+b'synthetic tamper')
    for call in (lambda: a.parse_attachment(actor, cid, receipt.attachment.id, parse_request, database=database),
                 lambda: a.find_parse_request(actor, cid, receipt.attachment.id, parse_request.request_id, database=database)):
        with pytest.raises(ServiceError) as error:
            call()
        assert error.value.code == 'VERSION_CONFLICT'
