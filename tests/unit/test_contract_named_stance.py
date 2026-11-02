"""Named-party continuation requires explicit, source-bound user declarations."""
from uuid import uuid4

import pytest

from cn_contract import domain as d
from cn_contract.assistant.providers.policy import encoded, sha
from tests.unit.test_contract_review_method import fixture, draft
from tests.unit.test_contract_stance_followup import with_stance


COMPANY = '恒岳仓储设备工程有限公司'
FIRST_QUESTION = ('我代表乙方恒岳仓储设备工程有限公司（供应方）。桌上两份草稿——仓储设备维护主服务协议、'
    '保密协议——都还没签署，双方也尚未开始履行。请从乙方立场审查，指出对我方不利或值得争取的条款，'
    '每处引用原文并说明所在文件与段落，不要给出签署结论。')
FOLLOWUP_QUESTION = ('继续上一个任务，立场不变，仍代表乙方恒岳仓储设备工程有限公司。现在多了一份尚未签署的'
    '补充协议草稿，双方仍在谈。请对照主服务协议与保密协议，说明哪些问题只是有条件改善、哪些完全没变、'
    '哪些属于新出现的问题，并说明在对方要求我方按新条款安排履约时应当如何表述。')


def named_stance(question, *, witness=None, history=(), stance='supplier', method_id=None,
        cite_witness=True, validate=True):
    method, manifest, value = with_stance(question, stance)
    messages = []
    for index, (user, assistant) in enumerate(history):
        for role, content in (('user', user), ('assistant', assistant)):
            messages.append(d.ConversationHistoryMessage(message_id=uuid4(), role=role,
                source_revision=2 * index + 1, content=content))
    current_revision = max(3 if witness else 1, 2 * len(history) + 1)
    reference = manifest.sources[0].reference.model_copy(update={'source_revision': current_revision})
    current = d.MainMaterialSource(source_id=sha(encoded(reference)), reference=reference)
    sources = [current, *manifest.sources[1:]]
    value['quotes'][-1]['source_id'] = current.source_id
    if witness is not None:
        prior_id = next((item.message_id for item in messages if item.role == 'user' and item.content == witness), uuid4())
        reference = d.ProfileMessageRef(kind='message', conversation_id=current.reference.conversation_id,
            message_id=prior_id, source_revision=1, start=0, end=len(witness), quote=witness, quote_sha256=sha(witness))
        prior = d.MainMaterialSource(source_id=sha(encoded(reference)), reference=reference)
        sources.append(prior)
        if cite_witness:
            value['quotes'].append(dict(id='prior_stance', source_id=prior.source_id,
                start=0, end=len(witness), exact_quote=witness))
            value['stance_quote_ids'].append('prior_stance')
    snapshot = manifest.contract_review if method_id is None else method.select_method(
        'contract', manifest.materials, tuple(sources), method_id=method_id)
    manifest = manifest.model_copy(update={'sources': tuple(sources), 'conversation_history': tuple(messages),
        'contract_review': snapshot})
    if validate:
        manifest = d.MainMaterialManifest.model_validate(manifest.model_dump(mode='python'))
    return method, manifest, value


def quote_fragment(value, quote_id, fragment):
    quote = next(item for item in value['quotes'] if item['id'] == quote_id)
    start = quote['exact_quote'].index(fragment)
    quote.update(start=start, end=start + len(fragment), exact_quote=fragment)


@pytest.mark.parametrize('question', [FIRST_QUESTION, '我是供应方，请审查独立虚构草稿。'],
    ids=['named_first_question', 'first_person_supplier'])
def test_explicit_first_person_named_supplier_is_accepted(question):
    method, manifest, value = named_stance(question)
    assert method.candidate(value, manifest).contract_review.stance == 'supplier'


@pytest.mark.parametrize('with_history', [False, True], ids=['no_successful_reply_needed', 'history_is_background'])
def test_named_continuation_requires_current_and_prior_source_quotes(with_history):
    history = [(FIRST_QUESTION, f'我代表乙方{COMPANY}（采购方）。')] if with_history else ()
    method, manifest, value = named_stance(FOLLOWUP_QUESTION, witness=FIRST_QUESTION, history=history)
    candidate = method.candidate(value, manifest)
    assert candidate.contract_review.stance == 'supplier'
    assert candidate.contract_review.stance_quote_ids == ('stance', 'prior_stance')
    assert manifest.sources[0].source_id in candidate.citations
    assert manifest.sources[-1].source_id in candidate.citations


@pytest.mark.parametrize('history', [
    pytest.param([(FIRST_QUESTION, '历史答复。')], id='user_history_without_witness'),
    pytest.param([('请整理独立虚构草稿。', FIRST_QUESTION)], id='assistant_claim_only'),
])
def test_conversation_history_alone_never_supplies_a_stance_witness(history):
    method, manifest, value = named_stance(FOLLOWUP_QUESTION, history=history)
    with pytest.raises(ValueError, match='CONTRACT_STANCE_INVALID'):
        method.candidate(value, manifest)


@pytest.mark.parametrize('witness', [
    pytest.param(f'我代表乙方{COMPANY}，请审查草稿。', id='no_role'),
    pytest.param('我们是供应方，请审查。', id='no_company'),
    pytest.param(f'乙方{COMPANY}是供应方，请中立核对。', id='describes_other_party'),
    pytest.param(f'对方说：“我代表乙方{COMPANY}（供应方）。”请中立核对。', id='quotes_other_speaker'),
    pytest.param(f'如果我代表乙方{COMPANY}（供应方），应注意什么？', id='hypothetical'),
    pytest.param('我代表乙方云峰测试设备有限公司（供应方）。', id='different_company'),
    pytest.param(f'我代表甲方{COMPANY}（供应方）。', id='different_party_label'),
])
def test_prior_source_must_explicitly_establish_the_same_named_party_and_role(witness):
    method, manifest, value = named_stance(FOLLOWUP_QUESTION, witness=witness)
    with pytest.raises(ValueError, match='CONTRACT_STANCE_INVALID'):
        method.candidate(value, manifest)


@pytest.mark.parametrize('question', [
    pytest.param(f'不再代表乙方{COMPANY}，请中立核对。', id='negation'),
    pytest.param(f'如果仍代表乙方{COMPANY}，应该注意什么？', id='hypothesis'),
    pytest.param(f'是否仍代表乙方{COMPANY}？', id='question'),
    pytest.param(f'对方仍代表乙方{COMPANY}，请中立核对。', id='other_speaker'),
    pytest.param(f'对方说：“仍代表乙方{COMPANY}。”请中立核对。', id='quoted_other_speaker'),
    pytest.param('立场不变，仍代表乙方云峰测试设备有限公司。', id='different_current_company'),
    pytest.param(f'立场不变，仍代表甲方{COMPANY}。', id='different_current_label'),
    pytest.param(f'立场不变，仍代表乙方{COMPANY}，我们是采购方。', id='different_current_role'),
    pytest.param(f'我代表乙方{COMPANY}（供应方），我们是采购方。', id='conflicting_roles'),
    pytest.param(f'我代表乙方{COMPANY}（供应方），不再代表供应方。', id='current_role_withdrawn'),
])
def test_prior_witness_does_not_override_current_negation_hypothesis_question_or_conflict(question):
    method, manifest, value = named_stance(question, witness=FIRST_QUESTION)
    with pytest.raises(ValueError, match='CONTRACT_STANCE_INVALID'):
        method.candidate(value, manifest)


def test_explicit_current_role_takes_priority_over_conversation_history():
    method, manifest, value = named_stance(f'我代表乙方{COMPANY}（采购方）。',
        history=[(FIRST_QUESTION, '历史待核答复。')], stance='customer')
    assert method.candidate(value, manifest).contract_review.stance == 'customer'


@pytest.mark.parametrize('missing', ['current', 'prior'])
def test_both_current_affirmation_and_prior_declaration_must_be_cited(missing):
    method, manifest, value = named_stance(FOLLOWUP_QUESTION, witness=FIRST_QUESTION)
    identifier = 'stance' if missing == 'current' else 'prior_stance'
    value['quotes'] = [item for item in value['quotes'] if item['id'] != identifier]
    value['stance_quote_ids'].remove(identifier)
    with pytest.raises(ValueError, match='CONTRACT_STANCE_INVALID'):
        method.candidate(value, manifest)


@pytest.mark.parametrize('fragment', [COMPANY, '供应方'], ids=['company_only', 'role_only'])
def test_prior_quote_must_include_the_named_party_role_declaration(fragment):
    method, manifest, value = named_stance(FOLLOWUP_QUESTION, witness=FIRST_QUESTION)
    quote_fragment(value, 'prior_stance', fragment)
    with pytest.raises(ValueError, match='CONTRACT_STANCE_INVALID'):
        method.candidate(value, manifest)


@pytest.mark.parametrize('fragment', [COMPANY, '立场不变'], ids=['company_only', 'affirmation_only'])
def test_current_stance_quote_requires_both_named_party_and_affirmation(fragment):
    method, manifest, value = named_stance(FOLLOWUP_QUESTION, witness=FIRST_QUESTION)
    quote_fragment(value, 'stance', fragment)
    with pytest.raises(ValueError, match='CONTRACT_STANCE_INVALID'):
        method.candidate(value, manifest)


def test_contract_manifest_rejects_multiple_prior_stance_sources():
    _, manifest, _ = named_stance(FOLLOWUP_QUESTION, witness=FIRST_QUESTION)
    reference = manifest.sources[-1].reference.model_copy(update={'message_id': uuid4(), 'source_revision': 2})
    extra = d.MainMaterialSource(source_id=sha(encoded(reference)), reference=reference)
    with pytest.raises(ValueError):
        d.MainMaterialManifest.model_validate(manifest.model_dump(mode='python') | {'sources': (*manifest.sources, extra)})


@pytest.mark.parametrize('method_id', ['contract-review-v1', 'contract-review-v2'])
def test_legacy_contract_methods_cannot_enable_stance_continuation(method_id):
    # Intentionally invalid legacy context still must not enable the new candidate path.
    method, manifest, value = named_stance(FOLLOWUP_QUESTION, witness=FIRST_QUESTION,
        method_id=method_id, validate=False)
    with pytest.raises(ValueError, match='CONTRACT_STANCE_INVALID'):
        method.candidate(value, manifest)


@pytest.mark.parametrize('method_id', ['contract-review-v1', 'contract-review-v2', None], ids=['v1', 'v2', 'current'])
def test_unknown_stance_without_stance_quotes_remains_readable(method_id):
    method, manifest, value = named_stance(FIRST_QUESTION, method_id=method_id)
    value.update(stance='unknown', stance_quote_ids=[])
    value['quotes'] = [item for item in value['quotes'] if item['id'] == 'q1']
    assert method.candidate(value, manifest).contract_review.stance == 'unknown'


def test_named_party_role_in_document_does_not_establish_user_stance():
    method, manifest = fixture(text=f'独立虚构身份记录：乙方{COMPANY}为供应方。', question=FOLLOWUP_QUESTION)
    manifest = d.MainMaterialManifest.model_validate(manifest.model_dump(mode='python'))
    value = draft(manifest)
    source = manifest.sources[0]
    value['quotes'].append(dict(id='stance', source_id=source.source_id, start=0,
        end=len(FOLLOWUP_QUESTION), exact_quote=FOLLOWUP_QUESTION))
    value.update(stance='supplier', stance_quote_ids=['stance'])
    with pytest.raises(ValueError, match='CONTRACT_STANCE_INVALID'):
        method.candidate(value, manifest)
