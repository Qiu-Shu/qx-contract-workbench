"""T03 service snapshots, byte integrity and multi-page native PDF parsing."""
from io import BytesIO
import stat

import pytest

from cn_contract.security import ServiceError
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'helpers'))
from synthetic_documents import api, docx, pdf, parsed, upload_meta, world


def test_all_pdf_native_pages_and_exact_resolution(tmp_path):
    documents, p, database, actor, matter, version, result = parsed(tmp_path, pdf(['SYNTHETIC page one', 'Tail guarantee 200']), {'original_name': 'synthetic.pdf', 'mime': 'application/pdf'})
    assert result.pages == (1, 2)
    assert result.unsupported_parts == ()
    assert [a.quote for a in result.anchors] == ['SYNTHETIC page one', 'Tail guarantee 200']
    with database.session() as db:
        assert documents.resolve_anchor(result.anchors[1], version, actor=actor, db=db).page == 2


def test_pdf_table_native_cells_keep_exact_coordinates(tmp_path):
    stream = b'72 620 m 272 620 l 272 720 l 72 720 l h S 172 620 m 172 720 l S 72 670 m 272 670 l S BT /F1 12 Tf 80 690 Td (Pay 100) Tj 100 0 Td (Guarantee) Tj -100 -50 Td (Tail 200) Tj 100 0 Td (No fee) Tj ET'
    documents, p, database, actor, matter, version, result = parsed(tmp_path, pdf([stream]), {'original_name': 'synthetic.pdf', 'mime': 'application/pdf'})
    cells = [anchor for anchor in result.anchors if '/table[' in anchor.element_id]
    assert {anchor.quote for anchor in cells} == {'Pay 100', 'Guarantee', 'Tail 200', 'No fee'}
    assert len(cells) == 4
    with database.session() as db:
        assert documents.resolve_anchor(cells[0], version, actor=actor, db=db).bbox == cells[0].bbox


def test_parse_appends_without_overwriting_original(tmp_path):
    documents, p, database, actor, matter, version, result = parsed(tmp_path)
    with database.session() as db:
        again = documents.parse_document(version, database.settings, actor=actor, db=db)
        assert again == result
        assert db.query(p.ParseRow).count() == 2
        assert p.read_original(matter.id, version.id, actor, db) == docx()
        assert p.read_version(matter.id, version.id, actor, db).parse_status == 'pending'


@pytest.mark.parametrize('operation', ['parse', 'resolve'])
def test_original_tampering_or_missing_blocks_every_operation(tmp_path, operation):
    documents, p, database, actor, matter, version, result = parsed(tmp_path)
    path = database.storage_root / version.storage_ref
    path.chmod(stat.S_IREAD | stat.S_IWRITE)
    path.write_bytes(b'tampered synthetic')
    with database.session() as db:
        with pytest.raises(ServiceError) as error:
            if operation == 'parse':
                documents.parse_document(version, database.settings, actor=actor, db=db)
            else:
                documents.resolve_anchor(result.anchors[0], version, actor=actor, db=db)
        assert error.value.code == 'VERSION_CONFLICT'


def test_new_version_rejects_previous_version_anchor(tmp_path):
    documents, p, database, actor, matter, version, result = parsed(tmp_path)
    with database.session() as db:
        new = documents.ingest(BytesIO(docx()), upload_meta(matter.id, supersedes_id=version.id), actor, db=db)
        with pytest.raises(ServiceError) as error:
            documents.resolve_anchor(result.anchors[0], new, actor=actor, db=db)
        assert error.value.code == 'VERSION_CONFLICT'
