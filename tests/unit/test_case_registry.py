"""T11 fixed suite integrity: data selects no code and creates no PASS."""
import importlib,importlib.util
import json,re
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[2]
SUITE=ROOT/'tests/acceptance/cases.json'


def feature(name='load_cases',module='registry'):
    assert importlib.util.find_spec('cn_contract.acceptance') is not None,'T11 requires an actual fixed acceptance service'
    assert importlib.util.find_spec('cn_contract.acceptance.'+module) is not None,'T11 requires '+module
    value=importlib.import_module('cn_contract.acceptance.'+module)
    result=getattr(value,name,None)
    assert callable(result),'T11 requires '+name
    return result


def source_rows():
    source=(ROOT/'sources/specification-v2.0.md').read_text(encoding='utf-8').split('## 14.',1)[1].split('### 14.1',1)[0]
    return [line.strip().split('|')[1:-1] for line in source.splitlines() if re.match(r'\|(V1-[DLQSW]\d{2}|AUD-T\d{2}|NEW-\d{2})\|',line)]


def test_84_unique_ids_and_original_expectations_preserved():
    cases=feature()(SUITE)
    rows=source_rows()
    assert len(cases)==len(rows)==84 and len({c.test_id for c in cases})==84
    assert {c.test_id for c in cases}=={r[0] for r in rows}
    assert [sum(c.test_id.startswith(p) for c in cases) for p in ('V1-','AUD-','NEW-')]==[44,24,16]
    for case,row in zip(cases,rows):
        assert case.input_scene==row[1] and case.expected==(row[2],) and case.source==row[4]
        assert case.owner and case.status=='NOT_RUN'


def test_client_pass_cannot_replace_server_execution():
    from cn_contract.domain import AcceptanceStatus
    cases=feature()(SUITE)
    altered=[cases[0].model_copy(update={'status':AcceptanceStatus.PASS}),*cases[1:]]
    with pytest.raises(ValueError):feature('evaluate_suite','runner')(altered,'offline',execute=False)


def test_entrypoint_is_fixed_key_not_arbitrary_code():
    cases=feature()(SUITE)
    for entry in ('os.system','tests/unit/test_domain.py::test_anything','__import__("os")','powershell -c whoami'):
        altered=[cases[0].model_copy(update={'entrypoint':entry}),*cases[1:]]
        with pytest.raises(ValueError):feature('evaluate_suite','runner')(altered,'offline',execute=False)


def test_expected_scene_and_owner_cannot_be_swapped():
    cases=feature()(SUITE)
    for fields in ({'expected':('全部通过',)},{'input_scene':'另一场景'},{'owner':''},{'fixture':'../real.docx'}):
        changed=[cases[0].model_copy(update=fields),*cases[1:]]
        with pytest.raises(ValueError):feature('evaluate_suite','runner')(changed,'offline',execute=False)


def test_registry_path_is_fixed_and_rejects_other_suite(tmp_path):
    load=feature();shadow=tmp_path/'cases.json';shadow.write_text('[]',encoding='utf-8')
    with pytest.raises(ValueError):load(shadow)


def test_blind_split_and_40_actual_synthetic_hashes():
    data=feature('load_dataset')()
    assert len(data)==40
    assert [sum(s.partition==p for s in data) for p in ('development','blind')]==[24,16]
    assert {k:sum(s.contract_type==k and not s.boundary for s in data) for k in ('sales','service','lease','nda')}=={k:8 for k in ('sales','service','lease','nda')}
    assert sum(s.boundary for s in data)==8
    groups={s.family for s in data}
    assert all(len({s.partition for s in data if s.family==f})==1 for f in groups)
    assert all(s.origin=='project_authored_independent_synthetic' and s.sha256 and s.limitations for s in data)


def test_shared_template_family_may_not_cross_blind_split():
    samples=feature('load_dataset')()
    first=next(s for s in samples if s.partition=='development')
    other=next(s for s in samples if s.partition=='blind')
    corrupted=[s.model_copy(update={'family':first.family,'template_sha256':first.template_sha256}) if s.id==other.id else s for s in samples]
    with pytest.raises(ValueError):feature('validate_dataset')(corrupted)


def test_same_framework_cannot_be_renamed_as_another_family():
    samples=feature('load_dataset')()
    first=next(s for s in samples if s.partition=='development')
    other=next(s for s in samples if s.partition=='blind')
    corrupted=[s.model_copy(update={'template_sha256':first.template_sha256}) if s.id==other.id else s for s in samples]
    with pytest.raises(ValueError):feature('validate_dataset')(corrupted)
