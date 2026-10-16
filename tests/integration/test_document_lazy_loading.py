"""Core and DOCX paths must work without initializing the optional PDF parser."""
from pathlib import Path
import subprocess
import sys
import textwrap

import pytest


ROOT = Path(__file__).resolve().parents[2]
PRELUDE = '''
import sys
from pathlib import Path
sys.path[:0] = [str(Path(sys.argv[1]) / 'src'), str(Path(sys.argv[1]) / 'tests/helpers')]
def pdf_modules():
    return sorted(name for name in sys.modules
                  if name.split('.')[0] in {'pdfplumber', 'pdfminer'}
                  or name == 'cn_contract.documents.pdf_adapter')
'''


def isolated(code, tmp_path):
    result = subprocess.run(
        [sys.executable, '-I', '-X', 'utf8', '-c', PRELUDE + textwrap.dedent(code),
         str(ROOT), str(tmp_path)],
        cwd=ROOT, capture_output=True, text=True, encoding='utf-8', timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize('module', ['cn_contract.documents', 'cn_contract.web.app'])
def test_core_import_does_not_initialize_pdf_parser(module, tmp_path):
    isolated(f'''
        import importlib
        importlib.import_module({module!r})
        assert not pdf_modules(), pdf_modules()
    ''', tmp_path)


def test_docx_ingest_parse_and_anchor_resolution_leave_pdf_unloaded(tmp_path):
    isolated('''
        from synthetic_documents import docx, parsed
        raw = docx('<w:p><w:r><w:t>SYNTHETIC DOCX 100</w:t></w:r></w:p>')
        documents, persistence, database, actor, matter, version, result = parsed(Path(sys.argv[2]), raw)
        assert [anchor.quote for anchor in result.anchors] == ['SYNTHETIC DOCX 100']
        with database.session() as db:
            assert persistence.read_original(matter.id, version.id, actor, db) == raw
            resolved = documents.resolve_anchor(result.anchors[0], version, actor=actor, db=db)
            assert resolved.model_dump(mode='python') == result.anchors[0].model_dump(mode='python')
        assert not pdf_modules(), pdf_modules()
    ''', tmp_path)


def test_first_pdf_use_keeps_validation_before_persistence(tmp_path):
    isolated('''
        from io import BytesIO
        from synthetic_documents import api, pdf, upload_meta, world
        from cn_contract.config import load_settings
        from cn_contract.persistence import MatterRow
        from cn_contract.security import ServiceError
        documents = api()
        settings = load_settings().model_copy(update={'parse_max_pages_per_file': 1})
        persistence, _, _, database, actor, matter = world(Path(sys.argv[2]), settings)
        assert not pdf_modules(), pdf_modules()
        raw = pdf(['SYNTHETIC PDF 100'])
        meta = upload_meta(matter.id, original_name='synthetic.pdf', mime='application/pdf')
        with database.session() as db:
            version = documents.ingest(BytesIO(raw), meta, actor, db=db)
            assert 'pdfplumber' in sys.modules and 'pdfminer' in sys.modules
            result = documents.parse_document(version, settings, actor=actor, db=db)
            assert result.pages == (1,)
            assert [anchor.quote for anchor in result.anchors] == ['SYNTHETIC PDF 100']
            assert persistence.read_original(matter.id, version.id, actor, db) == raw
            for bad, expected in [(b'%PDF-SYNTHETIC invalid', 'FILE_UNSUPPORTED'),
                                  (pdf(['SYNTHETIC first', 'SYNTHETIC second']), 'FILE_LIMIT')]:
                try:
                    documents.ingest(BytesIO(bad), meta, actor, db=db)
                except ServiceError as error:
                    assert error.code == expected, error.code
                else:
                    raise AssertionError('Invalid PDF was admitted')
            assert db.get(MatterRow, str(matter.id), populate_existing=True).file_count == 1
    ''', tmp_path)
