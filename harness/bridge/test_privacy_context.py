"""Public upload/review checks using only independent fictional text."""
import json
from pathlib import Path
import re

import pytest
import privacy

GOLD=json.loads((Path(__file__).resolve().parents[1]/'experiments/candidate-admission/privacy-docling-fixtures.json').read_text(encoding='utf-8'))['privacy']


def upload(tmp_path, text, **options):
    source=tmp_path/'fictional.txt'
    source.write_text(text,encoding='utf-8',newline='')
    original=source.read_bytes()
    result=privacy.prepare_upload(str(source),str(tmp_path/'vault'),review=True,**options)
    assert result['status']=='ready',result
    review=json.loads(Path(result['review_path']).read_text(encoding='utf-8'))
    safe=Path(result['safe_path']).read_text(encoding='utf-8')
    inverse={item['token']:item['original'] for item in review['replacements']}
    restored=re.sub(r'【脱敏-[^】]+】',lambda match:inverse[match.group()],safe)
    assert restored==text
    assert source.read_bytes()==original
    assert review['original_text']==text
    return result,review,safe


@pytest.mark.parametrize('mode',['standard','deep'])
def test_explicit_receipt_and_transfer_contexts_hide_people_not_roles_or_facts(tmp_path,mode):
    text=('完全虚构：周景澄已签收材料，签收日期2026年12月1日，数量12份。\n'
          '完全虚构：沈沐言将8000元转交给许清禾，双方于2026年12月2日签字。\n'
          '客户已签收材料。工作人员将8000元转交给收款人。周三已签收材料。\n'
          '原告应承担举证责任，被告应在15日内答辩，法院应依法审理。\n'
          '本合同约定向东运输，平安送达，费用1000元，付款比例20%。')
    result,review,safe=upload(tmp_path,text,privacy_mode=mode)
    for name in ('周景澄','沈沐言','许清禾'):
        assert name not in safe
        assert name not in json.dumps(result,ensure_ascii=False)
    assert {item['original'] for item in review['replacements']}=={'周景澄','沈沐言','许清禾'}
    for fact in ('8000元','2026年12月1日','12份','2026年12月2日','客户已签收材料',
                 '工作人员将8000元转交给收款人','周三已签收材料','原告','被告','法院','15日','向东','平安','1000元','20%'):
        assert fact in safe


@pytest.mark.parametrize('mode',['standard','deep'])
def test_ocr_name_whitespace_and_company_suffix_restore_the_exact_original_span(tmp_path,mode):
    text=('完全虚构：姓名：林晓\n岚。联系人：许 清 禾。周 景 澄先生已签收。\n'
          '甲方：青屿合成设备有限\n公司。乙方：映川合成技术有限 公司。\n'
          '姓名：林晓\n金额：900元。姓名：\n地址：测试路。\n'
          '日期：2026-12-03，比例3.5%。普通学校；技术服务\n学校。')
    _,review,safe=upload(tmp_path,text,privacy_mode=mode)
    expected={'林晓\n岚','许 清 禾','周 景 澄','青屿合成设备有限\n公司','映川合成技术有限 公司','林晓','测试路'}
    assert {item['original'] for item in review['replacements']}==expected
    assert '岚' not in safe and '清' not in safe and '澄' not in safe and '有限' not in safe
    for fact in ('先生已签收','金额：900元','姓名：\n地址：','2026-12-03','3.5%','普通学校','技术服务\n学校'):
        assert fact in safe


def test_shared_dictionary_recognizes_ocr_variants_without_losing_their_exact_spacing(tmp_path):
    _,first,first_safe=upload(tmp_path,'姓名：林晓\n岚。甲方：青屿合成设备有限\n公司。',context_id='fictional-case',privacy_mode='deep')
    _,second,second_safe=upload(tmp_path,'林晓岚已到场。青屿合成设备有限公司付款8000元。',context_id='fictional-case')
    assert '林晓岚' not in second_safe and '青屿合成设备有限公司' not in second_safe
    _,third,third_safe=upload(tmp_path,'林 晓 岚已到场。林晓\n岚已到场。',context_id='fictional-case')
    assert '林' not in third_safe and '岚' not in third_safe
    tokens=lambda review:{entry['original']:entry['token'] for entry in review['replacements']}
    assert tokens(first)['林晓\n岚']==tokens(third)['林晓\n岚']
    assert tokens(first)['林晓\n岚']!=tokens(second)['林晓岚']
    assert tokens(third)['林 晓 岚']!=tokens(second)['林晓岚']
    assert '8000元' in second_safe
    # Reusing another case is opt-in; no name context means no inference in a different dictionary.
    _,_,isolated=upload(tmp_path,'林晓岚已到场。',context_id='another-case')
    assert isolated=='林晓岚已到场。'
    final=privacy.finalize_review(str(tmp_path/'vault'),third['document_id'],third['review_token'],third_safe)
    assert final['status']=='ready'
    assert Path(final['safe_path']).read_text(encoding='utf-8')==third_safe


@pytest.mark.parametrize('sample',GOLD,ids=lambda sample:sample['id'])
@pytest.mark.parametrize('mode',['standard','deep'])
def test_unchanged_frozen_gold_entities_and_facts_through_upload(tmp_path,sample,mode):
    _,review,safe=upload(tmp_path,sample['text'],privacy_mode=mode)
    assert {item['original'] for item in review['replacements']}==set(sample['entities'])
    assert review['replacement_count']==len(sample['entities'])
    for value in sample['preserve']:
        assert value in safe


@pytest.mark.parametrize('mode',['standard','deep'])
def test_contexts_do_not_promote_common_words_dates_or_roles_to_people(tmp_path,mode):
    text=('申请已签收材料。费用已签收材料。陈述已签收材料。许多企业将8000元转交给甲方。\n'
          '许多人已签收材料。王经理已签收材料。周末已签收材料。\n'
          '周一将8000元转交给王主管。工作人员已签收材料。收款人已签收材料。\n'
          '总价1234567890123456元，比例20%，2026-11-12至2027-11-12。')
    _,review,safe=upload(tmp_path,text,privacy_mode=mode)
    assert safe==text
    assert review['replacement_count']==0


def test_explicit_names_and_their_existing_dictionary_are_not_revoked_by_context_exclusions(tmp_path):
    _,first,_=upload(tmp_path,'姓名：向东。联系人：平安。姓名：周一。',context_id='confirmed-names')
    assert {item['original'] for item in first['replacements']}=={'向东','平安','周一'}
    _,later,safe=upload(tmp_path,'向东、平安、周一已到场。',context_id='confirmed-names')
    assert later['replacements']==first['replacements']
    for name in ('向东','平安','周一'):
        assert name not in safe


def test_ocr_line_breaks_do_not_join_new_fields_or_ordinary_next_line_text(tmp_path):
    text='姓名：林晓\n年龄：18岁。姓名：林晓\n付款。姓名：林晓\n签收。姓名：林晓\n岚。'
    _,review,safe=upload(tmp_path,text)
    assert {item['original'] for item in review['replacements']}=={'林晓','林晓\n岚'}
    for fact in ('年龄：18岁','\n付款。','\n签收。'):
        assert fact in safe


def test_title_name_limit_does_not_absorb_thanks_or_meeting_verbs(tmp_path):
    text='感谢周景澄先生，会见林晓岚女士。'
    _,_,safe=upload(tmp_path,text)
    assert safe==text
    upload(tmp_path,'姓名：周景澄。姓名：林晓岚。',context_id='known-titles')
    _,review,safe=upload(tmp_path,text,context_id='known-titles')
    assert {item['original'] for item in review['replacements']}=={'周景澄','林晓岚'}
    assert '感谢' in safe and '会见' in safe and '先生' in safe and '女士' in safe


def test_ocr_name_crossing_the_reader_chunk_boundary_remains_complete_and_reversible(tmp_path):
    text='普通说明，'*799+'姓名：林晓\n岚。金额900元，2026年12月3日。'
    _,review,safe=upload(tmp_path,text)
    assert {item['original'] for item in review['replacements']}=={'林晓\n岚'}
    assert safe.count('普通说明，')==799
    assert '金额900元，2026年12月3日。' in safe


@pytest.mark.parametrize('numbering',['一、','二.','三)','四）','五．','（六）','a.'])
def test_ocr_name_does_not_absorb_the_next_numbered_paragraph(tmp_path,numbering):
    text=f'姓名：朱宁\n{numbering}付款安排：12000元。'
    _,review,safe=upload(tmp_path,text)
    assert {item['original'] for item in review['replacements']}=={'朱宁'}
    assert f'\n{numbering}付款安排：12000元。' in safe


@pytest.mark.parametrize('comma',['，',','])
def test_ocr_name_final_character_before_a_comma_is_still_part_of_the_name(tmp_path,comma):
    text=f'姓名：朱宁\n一{comma}付款金额12000元。'
    _,review,safe=upload(tmp_path,text)
    assert {item['original'] for item in review['replacements']}=={'朱宁\n一'}
    assert f'{comma}付款金额12000元。' in safe


def test_existing_name_dictionary_does_not_absorb_numbered_paragraphs(tmp_path):
    upload(tmp_path,'姓名：朱宁一。',context_id='numbered-paragraphs')
    text='姓名：朱宁\n一、付款安排：12000元。'
    _,review,safe=upload(tmp_path,text,context_id='numbered-paragraphs')
    assert {item['original'] for item in review['replacements']}=={'朱宁'}
    assert '\n一、付款安排：12000元。' in safe
