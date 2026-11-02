import hashlib
import json
from pathlib import Path
import pytest
from cn_contract import domain as d
from cn_contract.integrations.skill_registry import SkillRegistry
from cn_contract.security import ServiceError
from tests.helpers.capability_knowledge import knowledge_config,ROOT


def test_reuses_reception_search_and_keeps_nine_original_aliases(tmp_path):
    config=knowledge_config(tmp_path)
    registry=SkillRegistry(d.LocalSkillRegistryConfig.model_validate(config))
    packet=registry.retrieve('sales','客户咨询借款纠纷，需要什么材料？')
    assert packet.passages and all(p.origin=='reception' for p in packet.passages)
    assert packet.searches[0].original_documents==9 and packet.searches[0].source_count==8
    assert all(hashlib.sha256(p.text.encode()).hexdigest()==p.quote_sha256 for p in packet.passages)
    assert all(p.review_state=='user_unverified' for p in packet.passages)


def test_family_file_and_locator_are_kept_with_content_digest(tmp_path):
    config=knowledge_config(tmp_path)
    registry=SkillRegistry(d.LocalSkillRegistryConfig.model_validate(config))
    packet=registry.retrieve('case','请整理借款争议。')
    assert packet.passages and all(p.origin=='family' for p in packet.passages)
    assert all('合成办案.txt' in p.source_name and '段落' in p.locator for p in packet.passages)
    assert packet.searches[0].source_count==5


def test_actual_public_corpus_adapter_preserves_unverified_mirror(tmp_path):
    if not (ROOT/'.local/integrations/chiheng-legal-workbench/shared_corpus.py').is_file():
        pytest.skip('pinned external corpus adapter required')
    registry=SkillRegistry(d.LocalSkillRegistryConfig.model_validate(knowledge_config(tmp_path,public=True)))
    packet=registry.retrieve('case','请整理借款争议。')
    public=[p for p in packet.passages if p.origin=='public_law']
    assert public and public[0].review_state=='unverified_mirror'
    assert public[0].source_urls==('https://example.invalid/synthetic-law',)
    assert public[0].upstream_status=='待核' and public[0].applicability_verified is False


def test_no_match_is_recorded_not_presented_as_read_all(tmp_path):
    registry=SkillRegistry(d.LocalSkillRegistryConfig.model_validate(knowledge_config(tmp_path)))
    result=registry.retrieve('sales','ZXQUNMATCHED987')
    assert result.passages==() and result.searches[0].state=='no_match'


def test_reference_page_breaks_preserve_exact_quote_offsets_and_whitespace(tmp_path):
    config=knowledge_config(tmp_path)
    pin=config['knowledge']['family_files'][0]
    path=Path(config['skills'][1]['root'])/pin['path']
    original='\nEXACTPAGEA\f\nEXACTPAGEB\r\n'
    path.write_bytes(original.encode('utf-8'));pin['sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
    registry=SkillRegistry(d.LocalSkillRegistryConfig.model_validate(config))
    result=registry.retrieve('case','EXACTPAGEA EXACTPAGEB')
    found=[p for p in result.passages if p.source_sha256==pin['sha256']]
    assert found
    for item in found:
        start,end=map(int,item.locator.rsplit(' ',1)[1].split(':'))
        assert item.text==original[start:end] and '\f' not in item.text


def test_reception_search_uses_the_exact_approved_catalog_bytes(tmp_path,monkeypatch):
    from cn_contract.integrations import knowledge
    config=knowledge_config(tmp_path)
    registry=SkillRegistry(d.LocalSkillRegistryConfig.model_validate(config))
    original=knowledge.pinned
    def replace_after_pin(path,expected,limit):
        raw=original(path,expected,limit)
        if Path(path).name=='manifest.json':
            changed=json.loads(raw);changed['sources'][0]['title']='未经批准的替换来源'
            Path(path).write_text(json.dumps(changed,ensure_ascii=False),encoding='utf-8')
        return raw
    monkeypatch.setattr(knowledge,'pinned',replace_after_pin)
    result=registry.retrieve('sales','借款咨询')
    assert result.passages and all(p.source_name!='未经批准的替换来源' for p in result.passages)


@pytest.mark.parametrize('change',['family','reception','approval'])
def test_changed_or_unapproved_knowledge_blocks(tmp_path,change):
    config=knowledge_config(tmp_path)
    workflow='case' if change=='family' else 'sales'
    if change=='family':
        path=Path(config['skills'][1]['root'])/config['knowledge']['family_files'][0]['path']
        path.write_text('改动后的资料',encoding='utf-8')
    elif change=='reception':
        path=Path(config['knowledge']['reception_root'])/'manifest.json'
        path.write_text('{}',encoding='utf-8')
    else:
        config['knowledge']['local_use_approved']=False
    registry=SkillRegistry(d.LocalSkillRegistryConfig.model_validate(config))
    with pytest.raises(ServiceError):registry.retrieve(workflow,'借款')
