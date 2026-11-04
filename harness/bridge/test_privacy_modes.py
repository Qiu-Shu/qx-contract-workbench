"""Fictional examples for local privacy modes; never read real client material."""
import hashlib
import json
from pathlib import Path
import re
import sqlite3

import privacy


def upload(tmp_path, text, **options):
    source = tmp_path / 'fictional.txt'
    source.write_text(text, encoding='utf-8')
    result = privacy.prepare_upload(str(source), str(tmp_path / 'vault'), **options)
    assert result['status'] == 'ready', result
    assert source.read_text(encoding='utf-8') == text
    return result, Path(result['safe_path']).read_text(encoding='utf-8')


def test_standard_keeps_generic_organizations_and_business_facts(tmp_path):
    text = ('累计服务1200余所中小学校；服务中小学校；中小学校；公办学校。\n'
            '具有国家级高新技术企业资质。合同约定服务80所学校，交付24套设备，期限36个月。')
    _, safe = upload(tmp_path, text)
    assert safe == text


def test_standard_redacts_explicit_named_brands_models_aliases_and_competitions(tmp_path):
    text = ('乙方：示例青枫科技有限公司（品牌：远岸成长），以下简称“青枫科技”。\n'
            '自主研发的星穹学习大模型已完成生成式人工智能服务备案'
            '（备案编号：Beijing-Fiction-202601010001，备案时间2026年4月3日）。\n'
            'AI备案编号：京智备-2026-ZX037号。\n'
            '乙方承办的教育部白名单赛事"全国青少年虚构知识与实践创新大赛"。\n'
            '另承办《青穗杯少年创客挑战赛》。参加校园编程比赛。\n'
            '乙方的心理测评体系、9R训练体系、青枫驿站品牌及相关资料等。\n'
            '产品名称：星海课堂。产品体系“远岸课程”。通用能力包括AI测评引擎、数字人引擎。\n'
            '合同采用“先验收后付款”，交付24套设备。')
    result, safe = upload(tmp_path, text)
    for name in ('示例青枫科技有限公司', '远岸成长', '青枫科技', '星穹学习大模型',
                 'Beijing-Fiction-202601010001', '京智备-2026-ZX037号',
                 '全国青少年虚构知识与实践创新大赛', '青穗杯少年创客挑战赛',
                 '9R训练体系', '青枫驿站', '星海课堂', '远岸课程'):
        assert name not in safe, name
        assert name not in json.dumps(result, ensure_ascii=False)
    for fact in ('备案时间2026年4月3日', '心理测评体系', 'AI测评引擎', '数字人引擎',
                 '校园编程比赛', '先验收后付款', '交付24套设备', '）'):
        assert fact in safe, fact


def test_standard_does_not_treat_all_quotes_or_generic_product_types_as_names(tmp_path):
    text = ('采用“AI测评引擎”和“数字人引擎”，产品包括心理测评体系。\n'
            '活动类型：《青少年编程比赛》。约定“提供技术服务”。品牌建设应当遵守合同。')
    _, safe = upload(tmp_path, text)
    assert safe == text


def test_deep_hides_profile_qualifications_coverage_and_honors_but_keeps_contract_numbers(tmp_path):
    text = ('乙方：示例青枫科技有限公司。企业资质：国家级高新技术企业、专精特新小巨人企业。\n'
            '累计服务1200余所中小学校，现已覆盖850家教育机构。曾获省级教学成果一等奖。\n'
            '2026年4月3日签署合同，金额125000.50元，履行期限36个月。\n'
            '本合同约定服务80所学校，交付24套设备；按本合同已服务60所学校。')
    standard_result, standard = upload(tmp_path, text)
    deep_result, deep = upload(tmp_path, text, privacy_mode='deep')
    assert standard_result['privacy_mode'] == 'standard'
    assert deep_result['privacy_mode'] == 'deep'
    assert standard_result['display_name'].startswith('脱敏文字-')
    assert deep_result['display_name'].startswith('深度脱敏文字-')
    for value in ('国家级高新技术企业', '专精特新小巨人企业', '1200余所中小学校',
                  '850家教育机构', '省级教学成果一等奖'):
        assert value in standard
        assert value not in deep
    for value in ('2026年4月3日', '125000.50元', '36个月', '80所学校', '24套设备', '60所学校'):
        assert value in standard and value in deep
    assert any('资质' in warning and '规模' in warning for warning in deep_result['warnings'])
    manifests = [json.loads(p.read_text(encoding='utf-8')) for p in (tmp_path / 'vault/documents').glob('*/manifest.json')]
    assert {item['privacy_mode'] for item in manifests} == {'standard', 'deep'}


def test_context_tokens_stay_stable_when_deep_switches_back_to_standard(tmp_path):
    text = '甲方：示例青枫科技有限公司。具有国家级高新技术企业资质，累计服务1200所学校。'
    _, deep = upload(tmp_path, text, context_id='mode-switch', privacy_mode='deep')
    _, standard = upload(tmp_path, text, context_id='mode-switch', privacy_mode='standard')
    assert '国家级高新技术企业' not in deep and '1200所学校' not in deep
    assert '国家级高新技术企业' in standard and '1200所学校' in standard
    company_token = re.search(r'甲方：(【[^】]+】)', deep).group(1)
    assert company_token in standard


def test_old_generic_and_removed_custom_mappings_do_not_keep_redacting(tmp_path):
    context = 'old-mapping'
    upload(tmp_path, '电话13800138000', context_id=context)
    mapping = tmp_path / 'vault/contexts' / hashlib.sha256(context.encode()).hexdigest() / 'mapping.sqlite'
    with sqlite3.connect(mapping) as db:
        for number, (value, kind) in enumerate([('服务中小学校', '组织'), ('中小学校', '组织'),
                                               ('技术服务', '自定义'), ('合同', '自定义')], 100):
            db.execute('INSERT INTO replacements VALUES(?,?,?)', (value, kind, f'【old-{number}】'))
    text = '服务中小学校，面向中小学校提供技术服务；合同履行期限30日。'
    _, safe = upload(tmp_path, text, context_id=context)
    assert safe == text


def test_named_entity_tokens_are_reused_in_later_files_without_repeating_the_declaration(tmp_path):
    _, first = upload(tmp_path, '品牌：远岸成长。自研“星穹”大模型。', context_id='same-case')
    _, second = upload(tmp_path, '远岸成长使用星穹提供服务。', context_id='same-case')
    assert '远岸成长' not in second and '星穹' not in second
    assert set(re.findall(r'【[^】]+】', first)) == set(re.findall(r'【[^】]+】', second))


def test_explicit_current_custom_terms_can_still_redact_generic_words(tmp_path):
    _, safe = upload(tmp_path, '提供技术服务，合同期限30日。', custom_terms=['技术服务', '合同'])
    assert '技术服务' not in safe and '合同' not in safe and '30日' in safe


def test_contract_role_aliases_and_generic_product_phrases_are_not_identities(tmp_path):
    text = ('以下简称“甲方”，以下简称“乙方”，以下简称“本公司”，以下简称“本协议”。\n'
            '保护自主品牌，维持原有产品体系，采用通用大模型。')
    _, safe = upload(tmp_path, text)
    assert safe == text


def test_deep_profile_scale_supports_regions_and_postfixed_counts(tmp_path):
    text = ('业务已覆盖全国二十余个省区市、服务中小学校逾万所。\n'
            '合同总价18000元，2026年4月3日签订，服务期限五年。')
    _, standard = upload(tmp_path, text)
    _, deep = upload(tmp_path, text, privacy_mode='deep')
    assert standard == text
    for value in ['二十余个省区市', '逾万所']:
        assert value not in deep
    for value in ['服务中小学校', '18000元', '2026年4月3日', '五年']:
        assert value in deep


def test_profile_quantity_must_not_replace_the_same_contract_performance_quantity(tmp_path):
    text = '企业累计服务1200所学校。按本合同约定，已服务1200所学校。30日内交付20所学校。'
    _, deep = upload(tmp_path, text, privacy_mode='deep')
    assert '企业累计服务1200所学校' not in deep
    assert '按本合同约定，已服务1200所学校' in deep
    assert '30日内交付20所学校' in deep
    _, standard = upload(tmp_path, text)
    assert standard == text


def test_deep_hides_named_association_appointment_without_changing_role_terms(tmp_path):
    text = ('乙方是中国示例教育协会课程培训项目全国实施运营单位。\n'
            '本合同由双方签署，乙方负责技术实施运营。')
    _, standard = upload(tmp_path, text)
    _, deep = upload(tmp_path, text, privacy_mode='deep')
    assert standard == text
    assert '中国示例教育协会' not in deep
    assert '乙方负责技术实施运营' in deep
