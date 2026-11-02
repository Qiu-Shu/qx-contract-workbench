"""Synthetic v2 routing and presentation changes preserve frozen v1 evidence."""
from copy import deepcopy
from unittest.mock import patch
from uuid import UUID

import pytest

from cn_contract.assistant import contract_review as method
from cn_contract.assistant.providers.policy import sha
from tests.unit.test_contract_review_method import fixture as current_fixture, draft


def fixture(*args, **kwargs):
    module, manifest = current_fixture(*args, **kwargs)
    snapshot = method.select_method('contract', manifest.materials, manifest.sources, method_id=method.V2_METHOD_ID)
    return module, manifest.model_copy(update={'contract_review': snapshot})


NDA_BACKGROUND = '双方为评估设备服务项目披露保密信息，接收方不得另作使用。违反保密义务应支付30万元赔偿。'
MIXED = '供应方交付设备后由采购方验收并支付货款。双方披露的保密信息仅用于履约，接收方不得向第三人披露。'


@pytest.mark.parametrize('text', [
    NDA_BACKGROUND,
    '双方为洽谈服务项目披露保密信息。接收方泄密时应支付违约金30万元。',
    'The parties disclose confidential information to evaluate equipment services. The recipient must make payment of damages for a confidentiality breach.',
    'Confidential information is disclosed to evaluate supplier services. The recipient shall pay a penalty and deliver or return all confidential documents on termination.',
    '双方为评估设备服务项目披露保密信息。接收方收到要求后应交付全部保密资料。',
    '双方为评估采购项目披露保密信息。本协议不约定设备交付或验收，供货另行签约。',
])
def test_v2_nda_background_and_breach_remedies_do_not_select_vendor(text):
    _, manifest = fixture(text)
    assert manifest.contract_review.method_id == 'contract-review-v2'
    assert manifest.contract_review.routes[0].methods == ('nda',)


@pytest.mark.parametrize('text, expected', [
    ('供应商提供云服务订阅SaaS，按月付款验收。数据处理协议DPA另附。', ('vendor',)),
    ('供应方交付后采购方付款并验收。', ('vendor',)),
    ('甲方采购设备，乙方应交付十台设备，甲方验收后付款。', ('vendor',)),
    ('甲方采购软件服务，服务费为每月人民币一万元，由甲方支付。', ('vendor',)),
    ('The supplier shall deliver equipment and the customer shall pay the purchase price after acceptance.', ('vendor',)),
    ('The service fee is payable monthly by the customer.', ('vendor',)),
    (MIXED, ('nda', 'vendor')),
    ('The supplier shall deliver equipment and receive payment of the purchase price. Confidential information is disclosed only for performance; the recipient must keep it confidential.', ('nda', 'vendor')),
    ('编号记录，不含合同约定。', ('general',)),
])
def test_v2_keeps_actual_performance_and_mixed_contract_routes(text, expected):
    _, manifest = fixture(text)
    assert manifest.contract_review.routes[0].methods == expected


def test_v2_retains_unsupported_specialty_and_ignores_filename():
    _, manifest = fixture('双方披露保密信息用于评估 SaaS 服务，DPA 数据处理协议另行讨论。泄密应支付赔偿。')
    files = (manifest.materials[0].model_copy(update={'name': '主服务供应合同.docx'}),)
    snapshot = method.select_method('contract', files, manifest.sources)
    assert snapshot.routes[0].methods == ('nda',)
    assert snapshot.routes[0].uncovered == ('saas', 'dpa')


def test_explicit_v1_keeps_original_routes_prompt_sources_and_render_bytes():
    with patch('tests.unit.test_contract_live_method.uuid4', return_value=UUID(int=7)), patch(
            'tests.unit.test_contract_review_method.uuid4', return_value=UUID(int=7)):
        _, manifest = fixture(NDA_BACKGROUND)
    snapshot = method.select_method('contract', manifest.materials, manifest.sources, method_id='contract-review-v1')
    manifest = manifest.model_copy(update={'contract_review': snapshot})
    assert snapshot.routes[0].methods == ('nda', 'vendor')
    assert sha(method.SYSTEM) == '21ccdf2ff379172b2ecaff0020411c52707083c0dc994c56088452d3f3447c0f'
    assert snapshot.method_sha256 == '6a1372087ce18e2a35ec78b1b2aafc34a7764c01d9780104e4643642b2241bbb'
    assert tuple(source.method_sha256 for source in snapshot.method_sources) == (
        'ed0cb57e23aaa63f4cbf2d54c66499938295edaf9bcab37bb30fcdf503ad3e9c',
        '3a377abcb718a327e627f81ae92d5ee85ec239c256d3a5350ab908761c3f8e46')
    assert sha(method.candidate(draft(manifest), manifest).text) == '242406fd5122a55863836c9dd9d2ba34880c12bb578572cbd4e1fd974e080c01'


def test_v2_system_is_bound_to_revision_while_output_schema_remains_v1():
    _, manifest = fixture(MIXED)
    snapshot = manifest.contract_review
    assert snapshot.method_id == method.V2_METHOD_ID
    assert '版本contract-review-v2' in method.method_system(snapshot)
    assert 'format_version固定contract-review-v1' in method.method_system(snapshot)
    for update in ({'method_id': 'contract-review-v1'}, {'method_sha256': 'f' * 64}):
        with pytest.raises(ValueError, match='CONTRACT_METHOD_INVALID'):
            method.method_system(snapshot.model_copy(update=update))
    with pytest.raises(ValueError, match='CONTRACT_METHOD_INVALID'):
        method.select_method('contract', manifest.materials, manifest.sources, method_id='unregistered')


def test_v2_candidate_rejects_routes_from_other_revision():
    _, manifest = fixture(NDA_BACKGROUND)
    old = method.select_method('contract', manifest.materials, manifest.sources, method_id='contract-review-v1')
    wrong = manifest.model_copy(update={'contract_review': manifest.contract_review.model_copy(update={'routes': old.routes})})
    with pytest.raises(ValueError, match='CONTRACT_METHOD_INVALID'):
        method.candidate(draft(wrong), wrong)


def test_v2_merges_only_exact_same_attachment_findings_for_display_and_keeps_data():
    _, manifest = fixture(MIXED)
    value = draft(manifest)
    result = method.candidate(value, manifest)
    assert len(result.contract_review.reviews) == 2
    assert result.text.count('建议替换草稿：') == 1
    assert '相同发现见本附件前述' in result.text
    different = deepcopy(value)
    different['reviews'][1]['findings'][0]['fallback'] = '请补核供应商责任例外后另行决定'
    assert method.candidate(different, manifest).text.count('建议替换草稿：') == 2


def test_v2_keeps_identical_text_with_different_source_positions():
    _, manifest = fixture(MIXED)
    value = draft(manifest)
    second = deepcopy(value['quotes'][0])
    second.update(id='q2', end=len('供应方交付设备'), exact_quote='供应方交付设备')
    value['quotes'].append(second)
    value['reviews'][1]['findings'][0]['quote_ids'] = ['q2']
    result = method.candidate(value, manifest)
    assert len(result.contract_review.quotes) == 2
    assert result.text.count('建议替换草稿：') == 2


def test_v2_does_not_merge_identical_findings_across_attachments():
    from cn_contract import domain as d
    from cn_contract.assistant.providers.policy import encoded

    _, manifest = fixture(MIXED)
    second_file = manifest.materials[0].model_copy(update={'attachment_id': UUID(int=99), 'name': '第二份材料.docx'})
    first_source = manifest.sources[-1]
    second_ref = first_source.reference.model_copy(update={'attachment_id': second_file.attachment_id,
        'anchor': first_source.reference.anchor.model_copy(update={'document_version_id': second_file.attachment_id})})
    source = d.MainMaterialSource(source_id=sha(encoded(second_ref)), reference=second_ref)
    manifest = manifest.model_copy(update={'materials': (*manifest.materials, second_file), 'sources': (*manifest.sources, source)})
    snapshot = method.select_method('contract', manifest.materials, manifest.sources)
    manifest = manifest.model_copy(update={'contract_review': snapshot})
    value = draft(manifest)
    first_quote = deepcopy(value['quotes'][0])
    first_quote.update(id='q_first', source_id=first_source.source_id)
    value['quotes'].append(first_quote)
    for review in value['reviews'][:2]:
        review['findings'][0]['quote_ids'] = ['q_first']
    result = method.candidate(value, manifest)
    assert len(result.contract_review.reviews) == 4
    assert result.text.count('建议替换草稿：') == 2


@pytest.mark.parametrize('text, expected', [
    ('供应商不承担运输风险但应按期交付设备。双方披露的保密信息仅用于履约。', ('nda', 'vendor')),
    ('供应商不承担运输风险并应按期交付设备。双方披露的保密信息仅用于履约。', ('nda', 'vendor')),
    ('供应方提供项目服务，采购方应按月支付服务费并承担逾期付款的违约赔偿。双方披露的保密信息仅用于履约。', ('nda', 'vendor')),
    ('乙方向甲方提供咨询服务，服务费每月1万元，甲方每月支付。双方披露保密信息仅用于履约，接收方不得向第三人披露。', ('nda', 'vendor')),
    ('The supplier does not bear shipping risk but shall deliver equipment. The parties disclose confidential information only for performance.', ('nda', 'vendor')),
    ('The supplier provides services, the service fee is 1000 per month, the customer makes payment monthly and pays damages for late payment. The recipient receives confidential information for performance.', ('nda', 'vendor')),
    ('双方为评估设备采购项目披露保密信息，接收方应交付或返还全部设备技术资料。', ('nda',)),
    ('The parties disclose confidential information to evaluate supplier services. The recipient shall deliver or return all equipment technical documents.', ('nda',)),
    ('双方为评估设备服务项目披露保密信息，接收方应交付全部保密材料。', ('nda',)),
    ('The parties disclose confidential information to evaluate supplier services. The recipient shall deliver all confidential technical data.', ('nda',)),
    ('双方评估服务项目并披露保密信息，泄密方应支付相当于服务费三倍的违约金。', ('nda',)),
    ('双方评估采购项目并披露保密信息，服务费另行约定，甲方不承担付款义务。', ('nda',)),
    ('供应商应交付设备及设备技术资料，采购方负责验收。双方披露的保密信息仅用于履约。', ('nda', 'vendor')),
    ('供应方应按期交付咨询服务成果报告。双方披露的保密信息仅用于履约。', ('nda', 'vendor')),
])
def test_v2_routes_local_performance_instead_of_entire_clause_exclusions(text, expected):
    _, manifest = fixture(text)
    assert manifest.contract_review.routes[0].methods == expected
