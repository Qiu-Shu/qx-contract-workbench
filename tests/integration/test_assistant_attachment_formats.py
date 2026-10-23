"""Assistant materials accept Word/PDF/sheet/image originals with byte-level sniffing."""
import hashlib
from io import BytesIO
import zipfile
from uuid import uuid4

from docx import Document
from pydantic import ValidationError
import pytest

from cn_contract import domain as d
from cn_contract.security import ServiceError
from test_assistant_storage import workspace, conversation

DOCX = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
XLSX = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'


def sample_docx():
    document = Document()
    document.add_paragraph('独立虚构材料：格式切片验收。')
    stream = BytesIO()
    document.save(stream)
    return stream.getvalue()


def sample_xlsx():
    stream = BytesIO()
    with zipfile.ZipFile(stream, 'w') as package:
        package.writestr('[Content_Types].xml', '<?xml version="1.0"?><Types/>')
        package.writestr('xl/workbook.xml', '<?xml version="1.0"?><workbook/>')
    return stream.getvalue()


SAMPLES = {
    ('合成材料.docx', DOCX): sample_docx(),
    ('合成合同扫描.pdf', 'application/pdf'): b'%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n',
    ('合成照片.png', 'image/png'): b'\x89PNG\r\n\x1a\n' + bytes(64),
    ('合成照片.jpg', 'image/jpeg'): b'\xff\xd8\xff\xe0' + bytes(64) + b'\xff\xd9',
    ('合成清单.xlsx', XLSX): sample_xlsx(),
    ('合成台账.csv', 'text/csv'): '虚构序号,虚构金额\n1,100\n'.encode('utf-8'),
}


@pytest.fixture
def format_workspace(workspace):
    from cn_contract.assistant.attachment_schema import initialize_storage
    database, actors, _, _ = workspace
    initialize_storage(database)
    database._assistant_synthetic_hashes = frozenset(
        hashlib.sha256(raw).hexdigest() for raw in SAMPLES.values())
    value = conversation(workspace)
    return database, actors, value


def input_for(value, name, mime):
    return d.AssistantAttachmentInput(request_id=uuid4(), expected_scope=value.scope,
        original_name=name, mime=mime,
        policy=d.AssistantMaterialPolicy(policy_id='assistant-local-files-v2', local_processing_accepted=True))


def test_all_supported_formats_roundtrip_bytes(format_workspace):
    from cn_contract.assistant import attachments as a
    database, actors, value = format_workspace
    actor, cid = actors['lawyer'], value.scope.conversation_id
    for (name, mime), raw in SAMPLES.items():
        scope = a.read_materials(actor, cid, database=database).scope
        receipt = a.ingest_attachment(actor, cid,
            d.AssistantAttachmentInput(request_id=uuid4(), expected_scope=scope,
                original_name=name, mime=mime,
                policy=d.AssistantMaterialPolicy(policy_id='assistant-local-files-v2', local_processing_accepted=True)),
            BytesIO(raw), database=database)
        assert receipt.attachment.mime == mime
        assert a.read_original(actor, cid, receipt.attachment.id, database=database) == raw
    materials = a.read_materials(actor, cid, database=database)
    assert len(materials.attachments) == len(SAMPLES)


def test_content_sniffing_rejects_mismatch_and_fake_bytes(format_workspace):
    from cn_contract.assistant import attachments as a
    database, actors, value = format_workspace
    actor, cid = actors['lawyer'], value.scope.conversation_id
    raw = SAMPLES[('合成材料.docx', DOCX)]
    # Extension/mime mismatch is rejected at DTO validation.
    with pytest.raises(ValidationError):
        input_for(value, '伪装.pdf', DOCX)
    # Declared PDF with DOCX bytes fails the magic-byte check.
    with pytest.raises(ServiceError) as caught:
        a.ingest_attachment(actor, cid, input_for(value, '伪装.pdf', 'application/pdf'), BytesIO(raw), database=database)
    assert caught.value.code == 'FILE_UNSUPPORTED'
    # A truncated fake xlsx (PK header but no readable zip directory) is refused.
    with pytest.raises(ServiceError):
        a.ingest_attachment(actor, cid, input_for(value, '坏表.xlsx', XLSX), BytesIO(b'PK\x03\x04broken'), database=database)
    # Empty csv text is refused.
    with pytest.raises(ServiceError):
        a.ingest_attachment(actor, cid, input_for(value, '空表.csv', 'text/csv'), BytesIO(b'  \n'), database=database)


def test_parse_stays_docx_only(format_workspace):
    from cn_contract.assistant import attachments as a
    database, actors, value = format_workspace
    actor, cid = actors['lawyer'], value.scope.conversation_id
    name, mime = ('合成合同扫描.pdf', 'application/pdf')
    receipt = a.ingest_attachment(actor, cid, input_for(value, name, mime),
                                  BytesIO(SAMPLES[(name, mime)]), database=database)
    current = a.read_materials(actor, cid, database=database)
    with pytest.raises(ServiceError) as caught:
        a.parse_attachment(actor, cid, receipt.attachment.id,
            d.AssistantAttachmentParseInput(request_id=uuid4(), expected_scope=current.scope), database=database)
    assert caught.value.code == 'FILE_UNSUPPORTED'


def test_docx_parse_still_reads_after_widening(format_workspace):
    from cn_contract.assistant import attachments as a
    database, actors, value = format_workspace
    actor, cid = actors['lawyer'], value.scope.conversation_id
    name, mime = ('合成材料.docx', DOCX)
    receipt = a.ingest_attachment(actor, cid, input_for(value, name, mime),
                                  BytesIO(SAMPLES[(name, mime)]), database=database)
    current = a.read_materials(actor, cid, database=database)
    parsed = a.parse_attachment(actor, cid, receipt.attachment.id,
        d.AssistantAttachmentParseInput(request_id=uuid4(), expected_scope=current.scope), database=database)
    assert parsed.parse.reading_status == 'readable'
    assert any('格式切片验收' in anchor.quote for anchor in parsed.parse.result.anchors)


def test_old_policy_id_remains_valid_for_stored_rows(format_workspace):
    from cn_contract.assistant import attachments as a
    database, actors, value = format_workspace
    actor, cid = actors['lawyer'], value.scope.conversation_id
    name, mime = ('合成材料.docx', DOCX)
    request = d.AssistantAttachmentInput(request_id=uuid4(), expected_scope=value.scope,
        original_name=name, mime=mime,
        policy=d.AssistantMaterialPolicy(local_processing_accepted=True))
    receipt = a.ingest_attachment(actor, cid, request, BytesIO(SAMPLES[(name, mime)]), database=database)
    assert receipt.attachment.policy.policy_id == 'assistant-local-docx-v1'
