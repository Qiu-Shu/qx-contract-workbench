"""QX06 public export/API seams with independent fictional contracts."""
import importlib
from uuid import UUID
import pytest
from cn_contract.security import ServiceError
from tests.helpers.synthetic_exports import setup, suggestion, approved, package
from tests.integration.test_assisted_confirmation import draft, confirm
from tests.integration.test_assisted_review import assisted_api


def revised_draft(assisted_api):
    client, _, _, _ = assisted_api
    matter, run, headers, _, _ = draft(assisted_api)
    finding = run['findings'][0]
    response = client.post(f'/api/matters/{matter}/patches/approve', headers=headers,
        json={'run_id': run['id'], 'run_sha256': run['run_sha256'], 'finding_id': finding['id'],
            'anchor_id': finding['anchor_ids'][0], 'new_text': '虚构价款合计：35000元；应核对分期与附件旧值。',
            'reason': '独立虚构修订测试', 'audiences': ['internal', 'client']})
    assert response.status_code == 201, response.text
    patch = response.json()
    response = client.post(f'/api/matters/{matter}/exports/preview', headers=headers,
        json={'run_id': run['id'], 'run_sha256': run['run_sha256'], 'audience': 'internal', 'patch_ids': [patch['id']]})
    assert response.status_code == 201, response.text
    return matter, run, headers, response.json(), patch


def review_body(snapshot):
    return {'bundle_id': snapshot['bundle_id'], 'effective_text_sha256': snapshot['sha256'],
        **{name: {'status': 'pending', 'reason': '虚构复审：此项尚待核对，不能称已完成'}
            for name in ('legal', 'amounts', 'deadlines', 'attachments', 'definitions_references')}}


def service():
    import importlib.util
    assert importlib.util.find_spec('cn_contract.exports.effective_text'), 'accepted-text review service required'
    return importlib.import_module('cn_contract.exports.effective_text')


def test_effective_snapshot_preserves_unchanged_duplicate_and_binds_actual_export(tmp_path):
    world = setup(tmp_path)
    patch = approved(world, suggestion(world))
    bundle = package(world, patches=[patch])
    database, actor, _, matter, _, parsed, _ = world
    with database.session() as db:
        value = service().read_effective_text(matter.id, bundle.id, actor, db=db)
    assert value.bundle_manifest_sha256 == bundle.manifest_sha256
    assert len(value.documents) == 1
    assert value.documents[0].limitations == (), 'known generated watermark is not an unread contract part'
    paragraphs = value.documents[0].paragraphs
    assert [p.text for p in paragraphs] == [parsed.anchors[0].quote, parsed.anchors[1].quote,
        patch.new_text, parsed.anchors[3].quote, parsed.anchors[4].quote]
    assert paragraphs[2].patch_id == patch.id and paragraphs[3].patch_id is None
    assert paragraphs[2].original_text == patch.old_text
    assert value.documents[0].artifact_id == bundle.artifacts[1].id
    assert value.artifact_hashes[bundle.artifacts[1].id] == bundle.artifacts[1].content_sha256


def test_revised_draft_requires_bound_rereview_and_keeps_pending_status(assisted_api):
    client, _, _, _ = assisted_api
    matter, run, headers, bundle, _ = revised_draft(assisted_api)
    body = {'bundle_id': bundle['id'], 'bundle_manifest_sha256': bundle['manifest_sha256'],
        'decision_snapshot_sha256': run['decision_snapshot']['sha256'], 'audience': 'internal',
        'acknowledged_unresolved_finding_ids': [], 'reason': '核对实际文件；保留全文复审待办'}
    blocked = confirm(client, matter, headers, body)
    assert blocked.status_code == 409, 'revised-text confirmation must require an explicit re-review'
    response = client.get(f'/api/matters/{matter}/bundles/{bundle["id"]}/effective-text')
    assert response.status_code == 200, response.text
    snapshot = response.json()
    saved = client.post(f'/api/matters/{matter}/effective-text-reviews', headers={**headers, 'Idempotency-Key': 'review-1'},
        json=review_body(snapshot))
    assert saved.status_code == 201, saved.text
    record = saved.json()
    assert record['status'] == 'pending' and record['formal_signoff'] is False
    body['effective_text_review_id'] = record['id']
    acknowledged = confirm(client, matter, headers, body, 'confirmed-after-review')
    assert acknowledged.status_code == 201, acknowledged.text
    assert acknowledged.json()['effective_text_review_status'] == 'pending'
    assert client.get(f'/api/matters/{matter}/effective-text-reviews/{record["id"]}').json() == record
    again = client.post(f'/api/matters/{matter}/effective-text-reviews', headers={**headers, 'Idempotency-Key': 'review-1'}, json=review_body(snapshot))
    assert again.json() == record
    later = client.post(f'/api/matters/{matter}/effective-text-reviews', headers=headers, json=review_body(snapshot))
    assert later.status_code == 201 and later.json()['id'] != record['id']
    assert client.get(f'/api/matters/{matter}/effective-text-reviews/{record["id"]}').status_code == 409
    assert client.get(f'/api/matters/{matter}/working-draft-confirmations/{acknowledged.json()["id"]}').status_code == 409
    replay = client.post(f'/api/matters/{matter}/effective-text-reviews', headers={**headers, 'Idempotency-Key': 'review-1'}, json=review_body(snapshot))
    assert replay.status_code == 409


def test_api_rereview_blocks_forged_hash_legal_completion_and_cross_case(assisted_api):
    from tests.integration.test_api import create_case, sign_in
    client, database, ids, _ = assisted_api
    matter, _, headers, bundle, _ = revised_draft(assisted_api)
    url = f'/api/matters/{matter}/effective-text-reviews'
    snapshot = client.get(f'/api/matters/{matter}/bundles/{bundle["id"]}/effective-text').json()
    body = review_body(snapshot)
    assert client.post(url, headers=headers, json={**body, 'effective_text_sha256': '0'*64}).status_code == 409
    response = client.post(url, headers=headers, json={**body, 'legal': {'status': 'reviewed', 'reason': '伪称已核验'}})
    assert response.status_code == 409 and response.json()['code'] == 'RULE_UNAPPROVED'
    assert client.post(url, json=body).status_code == 403
    other = create_case(client, headers)
    assert client.get(f'/api/matters/{other}/bundles/{bundle["id"]}/effective-text').status_code == 403
    assistant = sign_in(client, 'assistant')
    assert client.get(f'/api/matters/{matter}/bundles/{bundle["id"]}/effective-text').status_code == 403
    from cn_contract.security import set_membership
    with database.session() as db:
        set_membership(UUID(matter), ids['assistant'], db, can_sign=False)
    # Membership edits stale the run manifest; acquiring membership is not a way
    # to inherit a previously frozen full-text view.
    assert client.get(f'/api/matters/{matter}/bundles/{bundle["id"]}/effective-text').status_code == 409
    assert client.post(url, headers=assistant, json=body).status_code == 403


def test_revoked_reviewer_and_patch_invalidate_current_rereview(assisted_api):
    from cn_contract.persistence import UserRow
    from cn_contract.exports.approvals import revoke_patch
    from cn_contract.security import authenticate
    client, database, ids, _ = assisted_api
    matter, _, headers, bundle, patch = revised_draft(assisted_api)
    snapshot = client.get(f'/api/matters/{matter}/bundles/{bundle["id"]}/effective-text').json()
    from tests.integration.test_api import sign_in
    reviewer_headers = sign_in(client, 'reviewer')
    saved = client.post(f'/api/matters/{matter}/effective-text-reviews', headers=reviewer_headers, json=review_body(snapshot))
    assert saved.status_code == 201
    with database.session() as db:
        db.get(UserRow, str(ids['reviewer'])).disabled = True
    sign_in(client)
    assert client.get(f'/api/matters/{matter}/effective-text-reviews/{saved.json()["id"]}').status_code == 409
    with database.session() as db:
        actor = authenticate(client.cookies.get('qx_session'), db)
        revoke_patch(UUID(matter), UUID(patch['id']), actor, db=db)
    assert client.get(f'/api/matters/{matter}/bundles/{bundle["id"]}/effective-text').status_code == 409


def test_multi_document_old_values_and_table_text_are_visible_with_manual_patch_limit(tmp_path):
    from tests.helpers.synthetic_exports import BODY
    body = BODY + '<w:tbl><w:tr><w:tc><w:p><w:r><w:t>附件仍写价款101元，付款30日，参照第99条及“旧服务”。</w:t></w:r></w:p></w:tc></w:tr></w:tbl>'
    world = setup(tmp_path, body=body, second_document=True)
    automatic = suggestion(world).model_copy(update={'new_text': '供应商另行提供履约保证，价款202元。'})
    # Two different supported/unsupported paragraphs in the same output document.
    automatic = approved(world, automatic)
    manual = approved(world, suggestion(world, anchor_index=3, old='履约保证'))
    bundle = package(world, patches=[automatic, manual])
    with world[0].session() as db:
        snapshot = service().read_effective_text(world[3].id, bundle.id, world[1], db=db)
    assert len(snapshot.documents) == 2
    assert len(snapshot.documents[0].paragraphs) == 6
    assert snapshot.documents[0].paragraphs[-1].kind == 'table_cell'
    assert snapshot.documents[0].paragraphs[2].patch_id == automatic.id
    assert snapshot.documents[0].paragraphs[3].patch_id is None
    assert snapshot.limitations and '人工修改' in snapshot.limitations[0]
    assert any(s.kind == 'reference' and s.quote == '第99条' for s in snapshot.signals)
    assert any(s.kind == 'number' and s.quote == '101元' for s in snapshot.signals)
    assert any(s.kind == 'deadline' and s.quote == '30日' for s in snapshot.signals)


def test_changed_old_value_surviving_elsewhere_is_a_pending_lead(tmp_path):
    from tests.helpers.synthetic_exports import BODY, QUOTE
    body = BODY.replace(QUOTE, QUOTE+'价款101元。')
    world = setup(tmp_path, body=body)
    value = approved(world, suggestion(world, anchor_index=3).model_copy(update={'new_text': '供应商另行提供履约保证，价款202元。'}))
    bundle = package(world, patches=[value])
    with world[0].session() as db:
        snapshot = service().read_effective_text(world[3].id, bundle.id, world[1], db=db)
    assert any(s.kind == 'old_value_remaining' and s.quote == '101元' for s in snapshot.signals)


def test_external_manual_report_has_no_full_original_projection(tmp_path):
    world = setup(tmp_path)
    bundle = package(world, 'client', [approved(world, suggestion(world))])
    with world[0].session() as db, pytest.raises(ServiceError) as error:
        service().read_effective_text(world[3].id, bundle.id, world[1], db=db)
    assert error.value.code == 'NOT_SUPPORTED'


def test_effective_snapshot_checks_current_artifact_rows_and_bytes(tmp_path):
    from cn_contract.persistence import ExportRow
    world = setup(tmp_path, reader=True)
    bundle = package(world, patches=[approved(world, suggestion(world))])
    with world[0].session() as db:
        reader = world[0]._synthetic_t09_reader
        assert service().read_effective_text(world[3].id, bundle.id, reader, db=db).bundle_id == bundle.id
        db.get(ExportRow, str(bundle.artifacts[1].id)).superseded = True
    with world[0].session() as db, pytest.raises(ServiceError) as error:
        service().read_effective_text(world[3].id, bundle.id, world[1], db=db)
    assert error.value.code == 'APPROVAL_STALE'


def test_new_decision_stales_effective_text_and_review(assisted_api):
    client, _, _, _ = assisted_api
    matter, run, headers, bundle, _ = revised_draft(assisted_api)
    snapshot = client.get(f'/api/matters/{matter}/bundles/{bundle["id"]}/effective-text').json()
    saved = client.post(f'/api/matters/{matter}/effective-text-reviews', headers=headers, json=review_body(snapshot))
    assert saved.status_code == 201
    decision = client.post(f'/api/matters/{matter}/findings/{run["findings"][0]["id"]}/decision', headers=headers,
        json={'run_id': run['id'], 'run_sha256': run['run_sha256'], 'decision': 'request_info', 'reason': '数值复审后发现附件待补'})
    assert decision.status_code == 201
    assert client.get(f'/api/matters/{matter}/bundles/{bundle["id"]}/effective-text').status_code == 409
    assert client.get(f'/api/matters/{matter}/effective-text-reviews/{saved.json()["id"]}').status_code == 409


@pytest.mark.parametrize('content,expected', [
    ('<w:r><w:t>通知</w:t><w:tab/><w:t>生效</w:t><w:br/><w:t>次日</w:t></w:r>', '通知\t生效\n次日'),
    ('<w:r><w:t>第一行</w:t><w:br/><w:t>第二行</w:t></w:r>', '第一行\n第二行'),
])
def test_unmodified_formatting_does_not_block_other_plain_patch(tmp_path, content, expected):
    from tests.helpers.synthetic_exports import BODY
    world = setup(tmp_path, body=BODY+'<w:p>'+content+'</w:p>')
    bundle = package(world, patches=[approved(world, suggestion(world))])
    with world[0].session() as db:
        snapshot = service().read_effective_text(world[3].id, bundle.id, world[1], db=db)
    assert snapshot.documents[0].paragraphs[-1].text == expected


@pytest.mark.parametrize('baseline', ['accepted_view', 'rejected_view'])
def test_preexisting_revisions_use_actual_accepted_export_and_keep_limits(tmp_path, baseline, monkeypatch):
    from cn_contract import domain as d
    from tests.helpers.synthetic_exports import BODY
    from tests.helpers import synthetic_review
    # The fixture imports UploadMeta locally; change only its default selection.
    original = d.UploadMeta
    def metadata(**values):
        return original(**{**values, 'baseline_view': baseline})
    monkeypatch.setattr(synthetic_review, 'UploadMeta', metadata)
    revisions = '<w:p><w:del w:id="800"><w:r><w:delText>旧通知</w:delText></w:r></w:del><w:ins w:id="801"><w:r><w:t>新通知</w:t></w:r></w:ins></w:p>'
    world = setup(tmp_path, body=BODY+revisions)
    monkeypatch.setattr(synthetic_review, 'UploadMeta', original)
    bundle = package(world, patches=[approved(world, suggestion(world))])
    with world[0].session() as db:
        snapshot = service().read_effective_text(world[3].id, bundle.id, world[1], db=db)
    assert snapshot.documents[0].paragraphs[-1].text == '新通知'
    assert snapshot.documents[0].limitations


def test_original_relationship_limit_survives_generated_watermark(tmp_path):
    extras = {'word/_rels/document.xml.rels': '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="external1" Type="https://example.invalid/relationship" Target="https://example.invalid/unread" TargetMode="External"/></Relationships>'}
    world = setup(tmp_path, extras=extras)
    bundle = package(world, patches=[approved(world, suggestion(world))])
    with world[0].session() as db:
        snapshot = service().read_effective_text(world[3].id, bundle.id, world[1], db=db)
    limits = snapshot.documents[0].limitations
    assert 'word/_rels/document.xml.rels' in limits
    assert 'word/_rels/document.xml.rels:external_relationship:external1' in limits
