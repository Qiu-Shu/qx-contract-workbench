"""T03 independent synthetic OOXML/PDF; no client material or template reuse."""
import importlib
from io import BytesIO
import struct
from uuid import uuid4
import zipfile

import pytest

from cn_contract.config import load_settings
from cn_contract.domain import UploadMeta
from cn_contract.security import ServiceError
from cn_contract.domain import Matter, Role

def world(tmp_path, settings=None):
    import cn_contract.persistence as p
    import cn_contract.security as s
    import cn_contract.audit as a
    database = p.Database(f'sqlite:///{tmp_path / "test.db"}', tmp_path / 'originals', settings or load_settings())
    with database.session() as db:
        user_id = s.provision_user('synthetic-lawyer', 'local-test-password', {Role.HANDLING_LAWYER}, db)
        token, _ = s.login('synthetic-lawyer', 'local-test-password', db)
        actor = s.authenticate(token, db)
        matter = Matter(id=uuid4(), client_ref='SYNTHETIC', title='Synthetic T03 matter', jurisdiction='CN-mainland',
                        contract_type='sales', review_mode='pre_sign', position='buyer', objectives=(),
                        member_ids={user_id}, status='intake', active_fact_version=None,
                        active_policy_version=None, gate_issues=())
        p.provision_matter(matter, db)
    return p, s, a, database, actor, matter

W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
DOCX_MIME = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'


def api():
    try:
        result = importlib.import_module('cn_contract.documents')
    except ModuleNotFoundError as exc:
        assert exc.name != 'cn_contract.documents', 'T03 secure ingestion and exact parsing must exist'
        raise
    assert all(callable(getattr(result, name, None)) for name in ('ingest', 'parse_document', 'resolve_anchor'))
    return result


def docx(body=None, extras=None, compression=zipfile.ZIP_STORED):
    if body is None:
        body = '<w:p><w:r><w:t>虚构付款</w:t></w:r><w:r><w:t>金额100元</w:t></w:r></w:p>'
    parts = {
        '[Content_Types].xml': '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>',
        '_rels/.rels': '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>',
        'word/document.xml': f'<w:document xmlns:w="{W}"><w:body>{body}<w:sectPr/></w:body></w:document>',
    }
    parts.update(extras or {})
    result = BytesIO()
    with zipfile.ZipFile(result, 'w', compression=compression) as z:
        for name, content in parts.items():
            if isinstance(name, zipfile.ZipInfo):
                z.writestr(name, content)
            else:
                z.writestr(name, content.encode() if isinstance(content, str) else content)
    return result.getvalue()


def pdf(pages, annotation=None):
    """Handwritten legal PDF objects; strings ASCII for builtin Helvetica."""
    objects = [b'<< /Type /Catalog /Pages 2 0 R >>', b'', b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>']
    kids = []
    for text in pages:
        page_id, content_id = len(objects) + 1, len(objects) + 2
        kids.append(f'{page_id} 0 R')
        annots = f'/Annots [{3 + 2 * len(pages) + 1} 0 R]' if annotation is not None else ''
        objects.append(f'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 3 0 R >> >> /Contents {content_id} 0 R {annots} >>'.encode())
        content = text if isinstance(text, bytes) else b'' if text is None else f'BT /F1 12 Tf 72 720 Td ({text}) Tj ET'.encode()
        objects.append(f'<< /Length {len(content)} >>\nstream\n'.encode() + content + b'\nendstream')
    if annotation is not None:
        objects.append(annotation)
    objects[1] = f'<< /Type /Pages /Kids [{" ".join(kids)}] /Count {len(kids)} >>'.encode()
    output = bytearray(b'%PDF-1.4\n')
    offsets = [0]
    for number, obj in enumerate(objects, 1):
        offsets.append(len(output))
        output.extend(f'{number} 0 obj\n'.encode() + obj + b'\nendobj\n')
    start = len(output)
    output.extend(f'xref\n0 {len(offsets)}\n0000000000 65535 f \n'.encode())
    for offset in offsets[1:]:
        output.extend(f'{offset:010d} 00000 n \n'.encode())
    output.extend(f'trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{start}\n%%EOF\n'.encode())
    return bytes(output)


def upload_meta(matter_id, **changes):
    values = dict(matter_id=matter_id, original_name='虚构合同.docx', mime=DOCX_MIME,
                  baseline_view=None, supersedes_id=None)
    values.update(changes)
    return UploadMeta(**values)


def parsed(tmp_path, data=None, meta_changes=None, settings=None):
    documents = api()
    p, s, a, database, actor, matter = world(tmp_path, settings)
    with database.session() as db:
        version = documents.ingest(BytesIO(data or docx()), upload_meta(matter.id, **(meta_changes or {})), actor, db=db)
        result = documents.parse_document(version, database.settings, actor=actor, db=db)
    return documents, p, database, actor, matter, version, result
