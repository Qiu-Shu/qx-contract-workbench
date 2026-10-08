"""Ordinary tests never import OCR packages or download assets."""
import importlib,importlib.util
from uuid import uuid4
import pytest
from cn_contract.security import ServiceError


def api():
    assert importlib.util.find_spec('cn_contract.documents.ocr_process'), 'bounded OCR process missing'
    return importlib.import_module('cn_contract.documents.ocr_process')


def test_missing_runtime_does_not_run_ordinary_subprocess(monkeypatch):
    m=api()
    def blocked():raise ServiceError('OCR_ASSETS_INVALID',503)
    monkeypatch.setattr(m,'require_ocr_runtime',blocked)
    with pytest.raises(ServiceError) as caught:m.run_ocr_page(b'not image',{})
    assert caught.value.code=='OCR_ASSETS_INVALID'


@pytest.mark.parametrize('value',[{}, {'page':0}, {'document_sha256':'wrong'}])
def test_invalid_source_fails_before_native_launch(monkeypatch,value):
    m=api();monkeypatch.setattr(m,'require_ocr_runtime',lambda:True)
    with pytest.raises((ValueError,ServiceError)):m.run_ocr_page(b'fictional',value)


@pytest.mark.parametrize('raw',[b'[]',b'{',b'{"status":"ok"}',b'{"status":"ok","blocks":[{"confidence":NaN}]}',b'{"status":"ok","blocks":null}'])
def test_malformed_worker_output_is_explicitly_blocked(raw):
    m=api()
    from cn_contract.domain import OCRPageSource
    source=OCRPageSource(document_version_id=uuid4(),document_sha256='0'*64,page=1,
        page_width_points=50,page_height_points=50,bitmap_width=100,bitmap_height=100,
        bitmap_sha256='1'*64,coordinate_space='rendered_page_top_left')
    with pytest.raises(ServiceError) as error:m.decode_output(raw,source)
    assert error.value.code=='OCR_OUTPUT_INVALID'


def test_empty_recognized_region_is_preserved_as_unverified_candidate():
    from cn_contract.domain import OCRBlock
    block=OCRBlock(raw_text='',confidence=0,polygon=((1,1),(20,1),(20,20),(1,20)))
    assert block.raw_text=='' and block.verification_state=='unverified'
