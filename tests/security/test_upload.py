"""Hostile synthetic containers and object-level read authorization."""
from io import BytesIO
import stat
import struct
from uuid import uuid4
import zipfile

import pytest

from cn_contract.domain import Role
from cn_contract.security import ServiceError
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'helpers'))
from synthetic_documents import api, docx, pdf, parsed, upload_meta, world


@pytest.mark.parametrize('name', ['../escape.xml', '/absolute.xml', 'C:/drive.xml', '//host/share.xml', 'word\\bad.xml', 'word/a/../b.xml'])
def test_dangerous_zip_paths_rejected(tmp_path, name):
    documents = api()
    *_, database, actor, matter = world(tmp_path)
    with database.session() as db:
        with pytest.raises(ServiceError):
            documents.ingest(BytesIO(docx(extras={name: 'malicious synthetic'})), upload_meta(matter.id), actor, db=db)
        assert db.query(__import__('cn_contract.persistence', fromlist=['DocumentRow']).DocumentRow).count() == 0
    assert list(database.storage_root.rglob('original.bin')) == []


@pytest.mark.parametrize('kind', ['macro', 'symlink', 'duplicate', 'normalized_duplicate', 'bomb', 'dtd', 'central_size', 'local_name', 'crc', 'compression', 'encrypted'])
def test_unsafe_zip_or_xml_rejected(tmp_path, kind):
    documents = api()
    extras = {}
    compression = zipfile.ZIP_STORED
    if kind == 'macro':
        extras['word/vbaProject.bin'] = b'never execute'
    elif kind == 'symlink':
        info = zipfile.ZipInfo('word/link')
        info.create_system = 3
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        extras[info] = b'/outside'
    elif kind == 'normalized_duplicate':
        extras['word//document.xml'] = '<duplicate/>'
    elif kind == 'bomb':
        compression = zipfile.ZIP_DEFLATED
        extras['word/media/bomb.bin'] = b'X' * 1024 * 1024
    elif kind == 'dtd':
        extras['word/document.xml'] = '<!DOCTYPE x [<!ENTITY e "SECRET">]><x>&e;</x>'
    elif kind == 'compression':
        compression = zipfile.ZIP_BZIP2
    data = docx(extras=extras, compression=compression)
    if kind == 'duplicate':
        buf = BytesIO(data)
        with zipfile.ZipFile(buf, 'a') as z:
            with pytest.warns(UserWarning):
                z.writestr('word/document.xml', '<duplicate/>')
        data = buf.getvalue()
    if kind in {'central_size', 'local_name', 'crc', 'encrypted'}:
        buf = bytearray(data)
        central = buf.index(b'PK\x01\x02')
        if kind == 'central_size':
            struct.pack_into('<I', buf, central + 24, 1)
        elif kind == 'local_name':
            buf[30] ^= 1
        elif kind == 'crc':
            buf[central + 16] ^= 1
        else:
            struct.pack_into('<H', buf, central + 8, 1)
        data = bytes(buf)
    *_, database, actor, matter = world(tmp_path)
    with database.session() as db:
        with pytest.raises(ServiceError):
            documents.ingest(BytesIO(data), upload_meta(matter.id), actor, db=db)
    assert list(database.storage_root.rglob('original.bin')) == []


@pytest.mark.parametrize('filename,mime,data', [('x.zip', 'application/zip', b'PK\x03\x04'), ('x.docm', 'application/octet-stream', b'PK\x03\x04'), ('x.docx', 'application/pdf', b'%PDF-1.4'), ('x.pdf', 'application/pdf', b'not-pdf')])
def test_type_extension_magic_agree(tmp_path, filename, mime, data):
    documents = api()
    *_, database, actor, matter = world(tmp_path)
    with database.session() as db:
        with pytest.raises(ServiceError) as error:
            documents.ingest(BytesIO(data), upload_meta(matter.id, original_name=filename, mime=mime), actor, db=db)
        assert error.value.code == 'FILE_UNSUPPORTED'


def test_unauthorized_upload_never_reads_stream(tmp_path):
    documents = api()
    *_, database, actor, matter = world(tmp_path)
    class Unreadable:
        def read(self, size):
            pytest.fail('unauthorized upload read input')
    with database.session() as db:
        with pytest.raises(ServiceError) as error:
            documents.ingest(Unreadable(), upload_meta(uuid4()), actor, db=db)
        assert error.value.code == 'CROSS_MATTER_DENIED'


def test_assistant_cannot_select_existing_revision_baseline(tmp_path):
    documents = api()
    p, s, _, database, actor, matter = world(tmp_path)
    with database.session() as db:
        identifier = s.provision_user('synthetic-assistant', 'local-test-password', {Role.ASSISTANT}, db)
        token, _ = s.login('synthetic-assistant', 'local-test-password', db)
        assistant = s.authenticate(token, db)
        s.set_membership(matter.id, identifier, db)
    body = '<w:p><w:ins><w:r><w:t>新增</w:t></w:r></w:ins></w:p>'
    with database.session() as db:
        with pytest.raises(ServiceError) as error:
            documents.ingest(BytesIO(docx(body)), upload_meta(matter.id, baseline_view='original'), assistant, db=db)
        assert error.value.code == 'CROSS_MATTER_DENIED'


def test_revoked_access_checks_before_original_or_cache(tmp_path):
    documents, p, database, actor, matter, version, result = parsed(tmp_path)
    import cn_contract.security as s
    with database.session() as db:
        s.remove_membership(matter.id, actor.user_id, db)
    path = database.storage_root / version.storage_ref
    path.chmod(stat.S_IREAD | stat.S_IWRITE)
    path.unlink()
    with database.session() as db:
        for action in (lambda: documents.parse_document(version, database.settings, actor=actor, db=db),
                       lambda: documents.resolve_anchor(result.anchors[0], version, actor=actor, db=db)):
            with pytest.raises(ServiceError) as error:
                action()
            assert error.value.code == 'CROSS_MATTER_DENIED'


def test_caller_storage_ref_and_mime_cannot_redirect_parser(tmp_path):
    documents, p, database, actor, matter, version, result = parsed(tmp_path)
    forged = version.model_copy(update={'storage_ref': '../outside', 'mime': 'application/pdf', 'sha256': '0' * 64})
    with database.session() as db:
        output = documents.parse_document(forged, database.settings, actor=actor, db=db)
        assert output.anchors[0].quote == '虚构付款金额100元'


def test_quota_blocks_before_stream_read(tmp_path):
    documents = api()
    p, s, _, database, actor, matter = world(tmp_path)
    with database.session() as db:
        db.get(p.MatterRow, str(matter.id)).file_count = 20
    class Unreadable:
        def read(self, size):
            pytest.fail('exhausted quota read input')
    with database.session() as db:
        with pytest.raises(ServiceError) as error:
            documents.ingest(Unreadable(), upload_meta(matter.id), actor, db=db)
        assert error.value.code == 'FILE_LIMIT'


def test_file_and_case_byte_limits_are_bounded_while_reading(tmp_path):
    documents = api()
    from cn_contract.config import load_settings
    settings = load_settings().model_copy(update={'upload_max_file_mib': 1})
    p, s, _, database, actor, matter = world(tmp_path, settings)
    class Oversize:
        def read(self, size):
            return b'X' * size
    with database.session() as db:
        with pytest.raises(ServiceError) as error:
            documents.ingest(Oversize(), upload_meta(matter.id), actor, db=db)
        assert error.value.code == 'FILE_LIMIT'
    with database.session() as db:
        db.get(p.MatterRow, str(matter.id)).total_bytes = 200 * 1024 * 1024 - 10
    with database.session() as db:
        with pytest.raises(ServiceError) as error:
            documents.ingest(BytesIO(docx()), upload_meta(matter.id), actor, db=db)
        assert error.value.code == 'FILE_LIMIT'
    assert list(database.storage_root.rglob('original.bin')) == []


def test_forged_uncompressed_sizes_do_not_hide_actual_inflation(tmp_path):
    documents = api()
    data = bytearray(docx(compression=zipfile.ZIP_DEFLATED))
    central = data.index(b'PK\x01\x02')
    struct.pack_into('<I', data, central + 24, 1)
    struct.pack_into('<I', data, 22, 1)
    *_, database, actor, matter = world(tmp_path)
    with database.session() as db:
        with pytest.raises(ServiceError) as error:
            documents.ingest(BytesIO(data), upload_meta(matter.id), actor, db=db)
        assert error.value.code == 'FILE_UNSUPPORTED'
    assert list(database.storage_root.rglob('original.bin')) == []
