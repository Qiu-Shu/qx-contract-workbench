"""Do not count a correct-number substring inside a wrong OCR number."""
import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('ocr_acceptance', Path(__file__).resolve().parents[2]/'scripts/ocr_synthetic_acceptance.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


@pytest.mark.parametrize('recognized,correct', [
    ('价款28473元不得自动验收2026-10-15', True),
    ('价款 28473 元 不得自动验收 2026-10-15', True),
    ('价款28473元不得自动验收22026-10-15', False),
    ('价款28473元不得自动验收2026-10-150', False),
    ('价款128473元不得自动验收2026-10-15', False),
    ('价款284730元不得自动验收2026-10-15', False),
    ('价款28473.9元不得自动验收2026-10-15', False),
    ('价款0.28473元不得自动验收2026-10-15', False),
    ('价款-28473元不得自动验收2026-10-15', False),
    ('价款28473元不得自动验收2026-10-15-9', False),
    ('价款28473元不得动验收2026-10-15', False),
    ('', False),
])
def test_field_observation_requires_complete_numeric_values(recognized, correct):
    assert module.critical_fields_match(recognized, ['28473', '不得自动验收', '2026-10-15']) is correct


def test_separate_ocr_blocks_do_not_merge_page_number_with_amount():
    assert module.critical_fields_match(['虚构材料43', '29019', '价款元', '不得自动验收2026-10-15'], ['29019', '不得自动验收', '2026-10-15'])


def test_fragmented_digits_are_not_assembled_into_an_expected_amount():
    assert not module.critical_fields_match(['价款2', '8473元', '不得自动验收2026-10-15'], ['28473', '不得自动验收', '2026-10-15'])
