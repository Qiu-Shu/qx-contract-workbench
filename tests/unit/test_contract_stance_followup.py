"""Explicit party labels in current instructions, never inferred from documents."""
import pytest
from tests.unit.test_contract_review_method import fixture, draft


def with_stance(question, stance='supplier'):
    method, manifest = fixture(question=question)
    value = draft(manifest)
    source = manifest.sources[0]
    value['quotes'].append(dict(id='stance',source_id=source.source_id,start=0,end=len(question),exact_quote=question))
    value.update(stance=stance,stance_quote_ids=['stance'])
    return method, manifest, value


@pytest.mark.parametrize('question,stance', [
    ('请站在乙方供应方立场，审查两份草稿。','supplier'),
    ('仍代表乙方供应方。在同一任务补入拟议稿。','supplier'),
    ('我们是乙方供应方，请审查。','supplier'),
    ('请代理甲方采购方审查合同。','customer'),
    ('仍代表采购方，请更新意见。','customer'),
])
def test_explicit_current_party_label_and_continuation_are_accepted(question,stance):
    method,manifest,value = with_stance(question,stance)
    assert method.candidate(value,manifest).contract_review.stance==stance


@pytest.mark.parametrize('question', [
    '不再代表乙方供应方，请中立核对。',
    '如果仍代表乙方供应方，应如何处理？',
    '是否仍代表乙方供应方？',
    '对方仍代表乙方供应方，请中立核对。',
    '对方说：“仍代表乙方供应方。”请中立核对。',
    '请站在乙方供应方立场，请代表甲方采购方审查。',
    '乙方为供应方，请中立审查。',
])
def test_party_labels_do_not_override_negation_hypothesis_or_conflict(question):
    method,manifest,value = with_stance(question)
    with pytest.raises(ValueError,match='CONTRACT_STANCE_INVALID'):
        method.candidate(value,manifest)
