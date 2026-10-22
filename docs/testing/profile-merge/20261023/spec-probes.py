"""Independent synthetic Spec counterexamples at the public merge seam."""
from uuid import UUID

import pytest

from cn_contract import domain as d
from cn_contract.assistant.profiles import merge_profile
from tests.unit.test_assistant_profiles import source, patch, change, ref, document_source


def test_model_cannot_invent_contact_not_present_in_source():
    s = source('只说明一项借款争议；没有联系信息。')
    proposal = change(s, 'contact', {'kind': 'text', 'value': '合成联系人，电话 00000000000'})
    proposal['origin'] = 'model_inference'
    with pytest.raises(ValueError):
        merge_profile(None, patch(s, [proposal]), s, project_intake=True)


def test_inconsistent_previous_verification_is_not_returned_as_unknown_or_clear():
    s = source()
    first = merge_profile(None, patch(s, [change(s)]), s, project_intake=True)
    forged = first.profile.model_copy(update={'fields': (
        first.profile.fields[0].model_copy(update={'verification': 'unknown'}),)})
    try:
        result = merge_profile(forged, patch(s, [], 1), s, project_intake=True)
    except ValueError:
        return
    field = result.profile.fields[0]
    assert field.verification == 'unverified'
    assert result.projection.consultation == first.projection.consultation


def test_manual_empty_fields_survive_full_legacy_projection_and_model_suggestions():
    s = source()
    old = d.IntakeDraft(title='人工旧接待', consultation='', contact='', questions=(),
                        materials=(), follow_up_at=None, follow_up_note='',
                        client_reply='', internal_notes='', status='waiting')
    p = [change(s, 'consultation', {'kind': 'text', 'value': '模型新增摘要'}),
         change(s, 'questions', {'kind': 'list', 'value': ['模型问题']})]
    initial = merge_profile(None, patch(s, p), s, intake_current=old, project_intake=True)
    assert initial.projection == old
    assert all(f.protected_value is not None for f in initial.profile.fields)
    again = merge_profile(initial.profile, patch(s, p, initial.profile.revision), s,
                          intake_current=old, intake_baseline=old, project_intake=True)
    assert again.projection == old and not again.changed


def test_canonical_patch_permutation_and_manual_null_beat_conflicting_proposals():
    s = source()
    a = change(s, value={'kind': 'text', 'value': '摘要甲'})
    b = change(s, value={'kind': 'text', 'value': '摘要乙'})
    edit = d.ProfileEdit(field='consultation', value={'kind': 'null', 'value': None})
    left = merge_profile(None, patch(s, [a, b]), s, manual_edits=(edit,), project_intake=True)
    right = merge_profile(None, patch(s, [b, a]), s, manual_edits=(edit,), project_intake=True)
    assert left == right
    assert left.profile.fields[0].verification == 'conflicted'
    assert left.projection.consultation == ''


def test_same_quote_at_wrong_offsets_and_other_workspace_are_rejected():
    s = source('前缀原话。原话。')
    bad = ref(s, 2, 5)
    bad.update(start=0, end=3)
    with pytest.raises(ValueError):
        merge_profile(None, patch(s, [change(s, refs=[bad])]), s)
    first = merge_profile(None, patch(s, [change(s)]), s)
    wrong = s.model_copy(update={'scope': s.scope.model_copy(update={'workspace_id': UUID(int=999)})})
    with pytest.raises(ValueError):
        merge_profile(first.profile, patch(wrong, [], first.profile.revision), wrong)


def test_stale_parse_anchor_cannot_impersonate_current_selected_document():
    s, exact = document_source()
    other = {**exact, 'parse_revision': 2}
    p = {**change(s, refs=[other]), 'origin': 'document_statement'}
    with pytest.raises(ValueError):
        merge_profile(None, patch(s, [p]), s)
    correct = {**change(s, refs=[exact]), 'origin': 'document_statement'}
    result = merge_profile(None, patch(s, [correct]), s)
    assert result.profile.fields[0].verification == 'unverified'
    assert result.profile.fields[0].candidates[0].source_refs[0].anchor == s.documents[0].result.anchors[0]
