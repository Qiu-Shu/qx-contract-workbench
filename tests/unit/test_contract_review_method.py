"""Synthetic contract routing, quote boundaries and unapproved policy guards."""
import importlib
from uuid import uuid4
import pytest
from cn_contract import domain as d
from cn_contract.assistant.providers.policy import encoded, sha
from tests.unit.test_contract_live_method import sample


def fixture(text='保密信息仅用于评估，不得向第三方披露。知识产权全部转让给接收方。', question='请审查合同'):
    m, _, _ = sample()
    ref = m.sources[0].reference
    anchor = ref.anchor.model_copy(update={'quote':text,'quote_sha256':sha(text),'end':len(text)})
    ref = ref.model_copy(update={'anchor':anchor})
    msg = d.ProfileMessageRef(kind='message',conversation_id=ref.conversation_id,message_id=uuid4(),source_revision=1,
        start=0,end=len(question),quote=question,quote_sha256=sha(question))
    m = m.model_copy(update={'question':question,'sources':(d.MainMaterialSource(source_id=sha(encoded(msg)),reference=msg),
        d.MainMaterialSource(source_id=sha(encoded(ref)),reference=ref))})
    module=importlib.import_module('cn_contract.assistant.contract_review')
    return module,m.model_copy(update={'contract_review':module.select_method('contract',m.materials,m.sources)})


def draft(m):
    s=m.sources[-1];q=s.reference.anchor.quote
    return dict(format_version='contract-review-v1',stance='unknown',stance_quote_ids=[],
        quotes=[dict(id='q1',source_id=s.source_id,start=0,end=len(q),exact_quote=q)],
        reviews=[dict(attachment_id=str(r.attachment_id),method_id=method,summary='独立虚构分析，待律师核对',
            findings=[dict(title='隐藏权利义务待核',quote_ids=['q1'],standard_position='待律师确认',gap='存在知识产权转让',
                legal_risk='high',commercial_friction='low',replacement='建议将保密与权利转让分开约定。',fallback='交律师决定')])
            for r in m.contract_review.routes for method in r.methods],gaps=['法律适用尚未核验'])


def test_nda_hidden_obligation_is_red_draft_with_separate_business_rating():
    mod,m=fixture();value=mod.candidate(draft(m),m)
    assert m.contract_review.routes[0].methods==('nda',)
    assert '红色' in value.text and '商业摩擦：低' in value.text
    assert '未签发' in value.text and '标准' in value.text and value.contract_review is not None


def test_filename_alone_is_not_nda_routing_evidence():
    mod,m=fixture('此文件仅有编号，没有合同正文。')
    files=(m.materials[0].model_copy(update={'name':'NDA 保密协议.docx'}),)
    assert mod.select_method('contract',files,m.sources).routes[0].methods==('general',)


def test_link_in_user_instruction_is_not_treated_as_read_attachment():
    mod,m=fixture(question='请审查合同，附件见 https://example.invalid/nda')
    assert '指令含 URL' in mod.candidate(draft(m),m).text


def test_vendor_saas_dpa_and_url_are_reported_as_uncovered():
    mod,m=fixture('供应商提供云服务订阅SaaS，按月付款验收。数据处理协议DPA位于 https://example.invalid/dpa 。')
    route=m.contract_review.routes[0]
    assert route.methods==('vendor',) and route.uncovered==('saas','dpa')
    value=mod.candidate(draft(m),m)
    assert 'URL' in value.text and 'SaaS' in value.text and 'DPA' in value.text and '未覆盖' in value.text


def test_unread_attachment_has_no_impossible_review_but_remains_visible():
    mod,m=fixture()
    blank=m.materials[0].model_copy(update={'attachment_id':uuid4(),'name':'扫描附件.pdf','reading_status':'partial'})
    files=(*m.materials,blank)
    snapshot=mod.select_method('contract',files,m.sources)
    assert snapshot.routes[-1].methods==()
    m=m.model_copy(update={'materials':files,'contract_review':snapshot})
    result=mod.candidate(draft(m),m)
    assert '无可读正文' in result.text and '扫描附件.pdf' in result.text


@pytest.mark.parametrize('mutation', ['quote','source','missing','duplicate','green','approval','wrong_file','inline'])
def test_invalid_or_unapproved_contract_reply_is_rejected(mutation):
    mod,m=fixture();v=draft(m)
    if mutation=='quote':v['quotes'][0]['exact_quote']='改写原文'
    if mutation=='source':v['quotes'][0]['source_id']='f'*64
    if mutation=='missing':v['reviews']=[]
    if mutation=='duplicate':v['reviews']*=2
    if mutation=='green':v['reviews'][0]['findings'][0]['legal_risk']='green'
    if mutation=='approval':v['approved']=True
    if mutation=='wrong_file':v['reviews'][0]['attachment_id']=str(uuid4())
    if mutation=='inline':v['reviews'][0]['findings'][0]['gap']='伪依据['+'f'*64+']'
    with pytest.raises(ValueError):mod.candidate(v,m)


def test_supplier_stance_requires_current_user_quote_and_never_defaults_to_customer():
    mod,m=fixture('供应方交付后采购方付款并验收。','我们是供应方，请审查合同。');v=draft(m)
    msg=m.sources[0];q=msg.reference.quote
    v['quotes'].append(dict(id='s',source_id=msg.source_id,start=0,end=len(q),exact_quote=q))
    v.update(stance='supplier',stance_quote_ids=['s'])
    assert '我方角色：供应方' in mod.candidate(v,m).text
    v['stance']='customer'
    with pytest.raises(ValueError):mod.candidate(v,m)


def test_stance_negation_and_ambiguous_question_stay_unknown():
    for question in ['我们不是供应方，请审查合同。','我们是供应方，我们是采购方，请审查合同。',
            '对方律师代表供应方，请中立审查。','如果我们是供应方，应如何修改？','对方说我们是供应方，请中立审查。',
            '对方说：“我们是供应方。”请中立审查。']:
        mod,m=fixture(question=question);v=draft(m);msg=m.sources[0];q=msg.reference.quote
        v['quotes'].append(dict(id='s',source_id=msg.source_id,start=0,end=len(q),exact_quote=q))
        v.update(stance='supplier',stance_quote_ids=['s'])
        with pytest.raises(ValueError):mod.candidate(v,m)
