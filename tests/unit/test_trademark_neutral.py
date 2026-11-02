"""Versioned neutral source relationships; fixed synthetic values, not legal quality scores."""
from copy import deepcopy
from pathlib import Path
import json
import pytest
from cn_contract import domain as d
from cn_contract.assistant import trademark_triage as method, material_codec as codec
from tests.helpers.trademark_triage import manifest_for,draft_for

def neutral_sample(texts=None):
    manifest=manifest_for(texts=texts or ('虚构甲说明：甲拟授权乙，双方签署状态待核。',
        '虚构乙补充：乙拟授权甲，双方签署状态待核。'))
    manifest=manifest.model_copy(update={'trademark_triage':method.select_method('case',manifest.question,method_id='trademark-triage-v4')})
    raw=draft_for(manifest)
    raw['format_version']='trademark-triage-v2'
    for factor in raw['factors']:
        factor.update(holder=[],respondent=[],neutral=[])
    raw['factors'][0]['neutral']=[{'text':'两份虚构记载的授权方向不同，暂不能选定任何一方角色。','quote_ids':['q1','q2']}]
    return manifest,raw

def test_neutral_sources_do_not_require_inventing_a_favorable_claim():
    manifest,raw=neutral_sample()
    result=method.candidate(raw,manifest)
    assert result.trademark_triage.format_version=='trademark-triage-v2'
    assert result.trademark_triage.factors[0].holder==result.trademark_triage.factors[0].respondent==()
    assert result.trademark_triage.factors[0].neutral[0].quote_ids==('q1','q2')
    assert '待核观察：两份虚构记载的授权方向不同' in result.text
    assert 'neutral' not in result.text
    assert codec.validate_manifest_candidate(d.MainMaterialCandidate.model_validate_json(result.model_dump_json()),manifest)==result
    assert set(result.citations)=={q['source_id'] for q in raw['quotes']}

@pytest.mark.parametrize('damage', ['unknown_quote','empty_ref','duplicate_ref','foreign_source','wrong_text','unused_quote','inline_foreign','missing_neutral','too_many_neutral','old_format'])
def test_neutral_observations_keep_quote_and_version_guards(damage):
    manifest,raw=neutral_sample()
    neutral=raw['factors'][0]['neutral'][0]
    if damage=='unknown_quote':neutral['quote_ids']=['unknown']
    elif damage=='empty_ref':neutral['quote_ids']=[]
    elif damage=='duplicate_ref':neutral['quote_ids']=['q1','q1','q2']
    elif damage=='foreign_source':raw['quotes'][0]['source_id']=manifest.sources[0].source_id
    elif damage=='wrong_text':raw['quotes'][0]['exact_quote']='改写过的原文'
    elif damage=='unused_quote':neutral['quote_ids']=['q1']
    elif damage=='inline_foreign':neutral['text']+=' ['+'f'*64+']'
    elif damage=='missing_neutral':raw['factors'][1].pop('neutral')
    elif damage=='too_many_neutral':raw['factors'][0]['neutral']=[deepcopy(neutral) for _ in range(11)]
    else:raw['format_version']='trademark-triage-v1'
    with pytest.raises(ValueError):method.candidate(raw,manifest)

@pytest.mark.parametrize('old',['trademark-triage-v1','trademark-triage-v2','trademark-triage-v3'])
def test_new_format_cannot_enter_old_method(old):
    manifest,raw=neutral_sample()
    manifest=manifest.model_copy(update={'trademark_triage':method.select_method('case',manifest.question,method_id=old)})
    assert manifest.trademark_triage.method_id==old
    with pytest.raises(ValueError,match='literal_error'):method.candidate(raw,manifest)

@pytest.mark.parametrize('old',['trademark-triage-v1','trademark-triage-v2','trademark-triage-v3'])
def test_neutral_cannot_be_silently_dropped_by_old_format(old):
    manifest,raw=neutral_sample()
    manifest=manifest.model_copy(update={'trademark_triage':method.select_method('case',manifest.question,method_id=old)})
    assert manifest.trademark_triage.method_id==old
    raw['format_version']='trademark-triage-v1'
    with pytest.raises(ValueError,match='extra_forbidden'):method.candidate(raw,manifest)

def test_empty_neutral_has_no_placeholder_and_does_not_change_original_quotes():
    manifest,_=neutral_sample()
    raw=draft_for(manifest)
    result=method.candidate(raw,manifest)
    assert all(not factor.neutral for factor in result.trademark_triage.factors)
    assert '待核观察：' not in result.text
    assert all(q['exact_quote'] in result.text for q in raw['quotes'])

def test_saved_v4_does_not_change_when_current_default_moves(monkeypatch):
    manifest,raw=neutral_sample()
    system=method.method_system(manifest.trademark_triage)
    candidate=method.candidate(raw,manifest)
    monkeypatch.setattr(method,'CURRENT_METHOD_ID','trademark-triage-v6')
    assert method.method_system(manifest.trademark_triage)==system
    assert method.candidate(raw,manifest)==candidate

@pytest.mark.parametrize('field',['gaps','unresolved','neutral','holder','respondent'])
@pytest.mark.parametrize('style',['lower','mixed'])
def test_v4_schema_instructions_are_presented_without_field_names(field,style):
    original='原件记录Neutral留空和neutral留空，仅为待核文字。'
    manifest,raw=neutral_sample((original,'另一份独立虚构原文。'))
    text=('勿写neutral留空、holder留空或respondent留空。' if style=='lower'
        else '勿写Neutral留空、Holder留空或Respondent留空。')
    if field=='gaps':raw['gaps']=[text]
    elif field=='unresolved':raw['factors'][0]['unresolved']=[text]
    else:raw['factors'][0][field]=[dict(text=text,quote_ids=['q1','q2'])]
    result=method.candidate(raw,manifest)
    generated=[line.lower() for line in result.text.splitlines() if line.startswith(
        ('待核观察：','权利方有利线索：','被主张方有利线索：','待核：'))]
    assert all(word not in line for word in ('neutral','holder','respondent') for line in generated)
    assert original in result.text
    assert all(q['exact_quote'] in result.text for q in raw['quotes'])

def test_neutral_inline_marker_must_belong_to_this_observation():
    manifest,raw=neutral_sample()
    q1,q2=raw['quotes']
    first=raw['factors'][0]['neutral'][0]
    first['quote_ids']=['q1']
    raw['factors'][1]['neutral']=[dict(text='另一份虚构记载待核。',quote_ids=['q2'])]
    first['text']+=' ['+q1['source_id']+']'
    assert method.candidate(raw,manifest).trademark_triage is not None
    first['text']+=' ['+q2['source_id']+']'
    with pytest.raises(ValueError,match='TRADEMARK_REFERENCE_INVALID'):
        method.candidate(raw,manifest)

def test_v4_presentation_leaves_schema_words_in_original_quotes_untouched():
    original='原件记录：勿写neutral留空，仍待核。'
    manifest=manifest_for(texts=(original,'另一份独立虚构记载。'))
    manifest=manifest.model_copy(update={'trademark_triage':method.select_method('case',manifest.question,method_id='trademark-triage-v4')})
    raw=draft_for(manifest)
    raw['gaps']=['勿写neutral留空。']
    result=method.candidate(raw,manifest)
    assert original in result.text and result.text.count('neutral留空')==1
    assert result.trademark_triage.quotes[0].exact_quote==original

@pytest.mark.parametrize('row',json.loads((Path(__file__).parents[1]/'fixtures/trademark-method-legacy-v123.json').read_bytes())+
    [json.loads((Path(__file__).parents[1]/'fixtures/trademark-method-v4.json').read_bytes())],ids=lambda x:x['method_id'])
def test_old_wire_basis_candidate_and_serialization_are_exact(row):
    manifest=d.MainMaterialManifest.model_validate(row['manifest'])
    config=d.MainModelConfig.model_validate(row['config'])
    basis=d.MainMaterialSendBasis.model_validate(row['basis'])
    assert codec.build_manifest_request(manifest,config)==row['wire']
    assert codec.rebuild_basis(basis,config).model_dump(mode='json')==row['basis']
    result=method.candidate(row['raw'],manifest)
    assert result.model_dump(mode='json')==row['candidate']
    assert codec.validate_manifest_candidate(d.MainMaterialCandidate.model_validate(row['candidate']),manifest)==result
