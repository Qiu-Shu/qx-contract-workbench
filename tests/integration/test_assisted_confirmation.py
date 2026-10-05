"""Specific offline working-draft confirmation, independent of formal signoff."""
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select

from cn_contract import domain as d
from cn_contract.persistence import ApprovalRow, MatterRow, UserRow
from cn_contract.exports.storage import ExportRecordRow
from tests.integration.test_assisted_review import assisted_api, submit_proposal, docx_text
from tests.integration.test_api import api, sign_in, create_case


def test_working_draft_confirmation_has_separate_domain_input():
    assert hasattr(d, 'WorkingDraftConfirmationInput'), 'a specific draft confirmation cannot use formal Approval'
    assert hasattr(d, 'WorkingDraftConfirmation'), 'draft receipt must retain actual version and actor'


def draft(assisted_api, choices=('accept', 'accept')):
    client, database, ids, module = assisted_api
    matter, _, _, _, _, headers, _, run = submit_proposal(assisted_api)
    for finding, decision in zip(run['findings'], choices):
        if decision is None:
            continue
        response = client.post(f'/api/matters/{matter}/findings/{finding["id"]}/decision', headers=headers,
            json={'run_id': run['id'], 'run_sha256': run['run_sha256'], 'decision': decision,
                'reason': '本机独立虚构候选逐条核对'})
        assert response.status_code == 201, response.text
    run = client.get(f'/api/matters/{matter}/reviews/{run["id"]}').json()
    response = client.post(f'/api/matters/{matter}/exports/preview', headers=headers,
        json={'run_id': run['id'], 'run_sha256': run['run_sha256'], 'audience': 'client', 'patch_ids': []})
    assert response.status_code == 201, response.text
    bundle = response.json()
    unresolved = [f['id'] for f in run['decision_snapshot']['resolved_findings']
        if f.get('human_decision') and f['human_decision']['decision'] in ('request_info', 'refer')]
    body = {'bundle_id': bundle['id'], 'bundle_manifest_sha256': bundle['manifest_sha256'],
        'decision_snapshot_sha256': run['decision_snapshot']['sha256'], 'audience': bundle['audience'],
        'acknowledged_unresolved_finding_ids': unresolved, 'reason': '已核对此版文件；列明待核依据及未完成范围'}
    return matter, run, headers, bundle, body


def confirm(client, matter, headers, body, key='draft-confirm-1'):
    return client.post(f'/api/matters/{matter}/working-draft-confirmations',
        headers={**headers, 'Idempotency-Key': key}, json=body)


def confirmation_count(database):
    with database.session() as db:
        return db.scalar(select(func.count()).select_from(ExportRecordRow)
            .where(ExportRecordRow.kind == 'working_draft_confirmation'))


def test_working_draft_confirmation_is_not_formal_signoff(assisted_api):
    client, database, ids, _ = assisted_api
    matter, run, headers, bundle, body = draft(assisted_api)
    response = confirm(client, matter, headers, body)
    assert response.status_code == 201, response.text
    receipt = response.json()
    assert receipt['purpose'] == 'working_draft' and receipt['formal_signoff'] is False
    assert receipt['actor_id'] == str(ids['lawyer'])
    assert receipt['bundle_manifest_sha256'] == body['bundle_manifest_sha256']
    assert receipt['decision_snapshot_sha256'] == body['decision_snapshot_sha256']
    assert receipt['artifact_hashes'] == {a['id']: a['content_sha256'] for a in bundle['artifacts']}
    same = confirm(client, matter, headers, body)
    assert same.status_code == 201 and same.json() == receipt
    read = client.get(f'/api/matters/{matter}/working-draft-confirmations/{receipt["id"]}')
    assert read.status_code == 200 and read.json() == receipt
    assert confirmation_count(database) == 1
    with database.session() as db:
        assert db.scalar(select(func.count()).select_from(ApprovalRow)) == 0
        assert db.get(MatterRow, matter).status == 'awaiting_lawyer'
    text = docx_text(client.get(f'/api/matters/{matter}/exports/{bundle["artifacts"][0]["id"]}/download').content)
    assert '待核' in text and '独立虚构依据-待核第7条' in text
    from cn_contract.persistence import MembershipRow
    with database.session() as db:
        db.get(MembershipRow, (matter, str(ids['reviewer']))).can_sign = True
    reviewer_headers = sign_in(client, 'reviewer')
    formal = client.post(f'/api/matters/{matter}/approvals', headers=reviewer_headers,
        json={'bundle_id': bundle['id'], 'artifact_manifest_hash': bundle['manifest_sha256'],
            'review_snapshot_hash': run['run_sha256'], 'scope': bundle['audience']})
    assert formal.status_code == 403 and formal.json()['code'] == 'BLOCKED_LIVE'


@pytest.mark.parametrize('choices', [(None, 'accept'), ('edit', 'accept')])
def test_unreviewed_or_unfinished_edit_cannot_confirm(assisted_api, choices):
    client, database, _, _ = assisted_api
    matter, _, headers, _, body = draft(assisted_api, choices)
    response = confirm(client, matter, headers, body)
    assert response.status_code == 409 and response.json()['code'] == 'STATE_CONFLICT'
    assert confirmation_count(database) == 0


def test_pending_scope_must_be_acknowledged_exactly(assisted_api):
    client, database, _, _ = assisted_api
    matter, _, headers, _, body = draft(assisted_api, ('request_info', 'refer'))
    assert len(body['acknowledged_unresolved_finding_ids']) == 2
    for wrong in ([], body['acknowledged_unresolved_finding_ids'][:1], [str(uuid4())]):
        response = confirm(client, matter, headers, {**body, 'acknowledged_unresolved_finding_ids': wrong}, str(uuid4()))
        assert response.status_code == 409 and response.json()['code'] == 'STATE_CONFLICT'
    assert confirmation_count(database) == 0
    response = confirm(client, matter, headers, body)
    assert response.status_code == 201, response.text
    assert response.json()['acknowledged_unresolved_finding_ids'] == body['acknowledged_unresolved_finding_ids']


@pytest.mark.parametrize('field,value', [('bundle_manifest_sha256', '0' * 64),
    ('decision_snapshot_sha256', '0' * 64), ('audience', 'counterparty')])
def test_confirmation_exact_version_and_audience(assisted_api, field, value):
    client, database, _, _ = assisted_api
    matter, _, headers, _, body = draft(assisted_api)
    response = confirm(client, matter, headers, {**body, field: value})
    assert response.status_code == 409 and response.json()['code'] == 'VERSION_CONFLICT'
    assert confirmation_count(database) == 0


@pytest.mark.parametrize('extra', [{'actor_id': str(uuid4())}, {'formal_signoff': True},
    {'require_authority': False}, {'source_verified': True}])
def test_client_cannot_turn_draft_into_approval(assisted_api, extra):
    client, database, _, _ = assisted_api
    matter, _, headers, _, body = draft(assisted_api)
    response = confirm(client, matter, headers, {**body, **extra})
    assert response.status_code == 422
    assert confirmation_count(database) == 0


def test_new_decision_stales_previous_confirmation_and_replay(assisted_api):
    client, database, _, _ = assisted_api
    matter, run, headers, _, body = draft(assisted_api)
    response = confirm(client, matter, headers, body)
    assert response.status_code == 201, response.text
    receipt = response.json()
    changed = client.post(f'/api/matters/{matter}/findings/{run["findings"][0]["id"]}/decision', headers=headers,
        json={'run_id': run['id'], 'run_sha256': run['run_sha256'], 'decision': 'reject', 'reason': '此版意见另行核对后驳回'})
    assert changed.status_code == 201
    for response in (client.get(f'/api/matters/{matter}/working-draft-confirmations/{receipt["id"]}'),
        confirm(client, matter, headers, body)):
        assert response.status_code == 409 and response.json()['code'] == 'APPROVAL_STALE'
    assert confirmation_count(database) == 1


def test_confirmation_author_is_checked_without_changing_history(assisted_api):
    client, database, ids, _ = assisted_api
    matter, _, _, _, body = draft(assisted_api)
    reviewer_headers = sign_in(client, 'reviewer')
    response = confirm(client, matter, reviewer_headers, body)
    assert response.status_code == 201, response.text
    receipt = response.json()
    with database.session() as db:
        db.get(UserRow, str(ids['reviewer'])).roles = '["assistant"]'
    sign_in(client, 'lawyer')
    response = client.get(f'/api/matters/{matter}/working-draft-confirmations/{receipt["id"]}')
    assert response.status_code == 409 and response.json()['code'] == 'APPROVAL_STALE'
    assert confirmation_count(database) == 1


def test_assistant_and_cross_case_cannot_confirm(assisted_api):
    client, database, ids, _ = assisted_api
    matter, _, _, _, body = draft(assisted_api)
    from cn_contract.persistence import MembershipRow
    with database.session() as db:
        db.add(MembershipRow(matter_id=matter, user_id=str(ids['assistant']), can_sign=False))
    headers = sign_in(client, 'assistant')
    assert confirm(client, matter, headers, body).status_code == 403
    headers = sign_in(client)
    assert confirm(client, str(uuid4()), headers, body).status_code == 403
    assert confirmation_count(database) == 0


@pytest.mark.parametrize('change', ['superseded', 'altered_row'])
def test_artifact_row_must_still_be_the_current_downloadable_draft(assisted_api, change):
    client, database, _, _ = assisted_api
    matter, _, headers, bundle, body = draft(assisted_api)
    from cn_contract.persistence import ExportRow
    import json
    with database.session() as db:
        row = db.get(ExportRow, bundle['artifacts'][0]['id'])
        if change == 'superseded':
            row.superseded = True
        else:
            payload = json.loads(row.payload)
            payload['audience'] = 'counterparty'
            row.payload = json.dumps(payload)
    response = confirm(client, matter, headers, body)
    assert response.status_code == 409 and response.json()['code'] == 'APPROVAL_STALE'
    assert confirmation_count(database) == 0


def test_outer_rollback_leaves_no_confirmation_or_audit(assisted_api):
    client, database, _, _ = assisted_api
    matter, _, _, _, body = draft(assisted_api)
    from cn_contract.security import authenticate
    from cn_contract.persistence import AuditRow
    from cn_contract.exports.draft_confirmation import confirm_working_draft
    with database.session() as db:
        before = db.scalar(select(func.count()).select_from(AuditRow))
    with pytest.raises(RuntimeError, match='independent rollback'):
        with database.session() as db:
            actor = authenticate(client.cookies.get('qx_session'), db)
            receipt = confirm_working_draft(UUID(matter), d.WorkingDraftConfirmationInput.model_validate(body), actor, db=db)
            assert receipt.formal_signoff is False
            raise RuntimeError('independent rollback')
    assert confirmation_count(database) == 0
    with database.session() as db:
        assert db.scalar(select(func.count()).select_from(AuditRow)) == before


def test_mocked_default_cannot_create_working_draft_confirmation(api):
    client, database, _, _ = api
    headers = sign_in(client)
    matter = create_case(client, headers)
    from cn_contract.security import authenticate, ServiceError
    from cn_contract.exports.draft_confirmation import confirm_working_draft
    with database.session() as db:
        actor = authenticate(client.cookies.get('qx_session'), db)
        value = d.WorkingDraftConfirmationInput(bundle_id=uuid4(), bundle_manifest_sha256='0' * 64,
            decision_snapshot_sha256='0' * 64, audience='internal',
            acknowledged_unresolved_finding_ids=(), reason='仅测试默认模拟隔离')
        with pytest.raises(ServiceError) as error:
            confirm_working_draft(UUID(matter), value, actor, db=db)
        assert error.value.code == 'DATA_POLICY_UNAPPROVED'
    assert confirmation_count(database) == 0
