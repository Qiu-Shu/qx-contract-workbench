"""F03: actual SQLite/API decisions must control immutable draft delivery."""
from io import BytesIO
import json
from uuid import UUID, uuid4
from zipfile import ZipFile

import pytest
from sqlalchemy import select, func

from cn_contract.domain import FindingDecisionInput, HumanDecision
from cn_contract.exports import approvals, storage as export_storage
from cn_contract.persistence import ExportRow, ApprovalRow, AuditRow
from cn_contract.security import ServiceError
from cn_contract.web import services, storage as web_storage
from tests.helpers.synthetic_exports import setup, suggestion, approved, package, BODY
from tests.integration.test_api import api, reviewed_case, sign_in, create_case

EDIT_A = '律师明确改写的分析：保证事项须书面确认。'
EDIT_R = '律师明确改写的建议：核对双方签署的保证附件。'
EDIT_P = '双方按另行签署的书面附件确认履约保证。'
PRIVATE = 'PRIVATE_DECISION_REASON_F03_7bc'


def all_parts(raw):
    with ZipFile(BytesIO(raw)) as archive:
        return '\n'.join(archive.read(n).decode('utf-8', errors='replace') for n in archive.namelist())


def world_with_history(tmp_path, **kwargs):
    world = setup(tmp_path, **kwargs)
    web_storage.initialize_storage(world[0])
    export_storage.initialize_storage(world[0])
    return world


def decide(world, kind, finding=None, **fields):
    database, actor, _, matter, _, _, run = world
    finding = finding or run.findings[0]
    payload = dict(run_id=run.id, run_sha256=web_storage.sha(run.model_dump(mode='json')),
                   decision=kind, reason=PRIVATE, **fields)
    value = FindingDecisionInput.model_validate(payload)
    with database.session() as db:
        return services.save_decision(matter.id, finding.id, value, actor, db)


def report(world, audience='client', patches=()):
    bundle = package(world, audience, patches)
    with world[0].session() as db:
        raw = approvals.download_artifact(bundle.artifacts[0].id, world[1], db=db).getvalue()
        row = export_storage.latest('bundle', bundle.id, db)
        metadata = json.loads(row.payload)['metadata']
    return bundle, all_parts(raw), metadata


def test_reject_removes_client_advice_keeps_internal_original_and_history(tmp_path):
    world = world_with_history(tmp_path); run = world[6]; finding = run.findings[0]
    decide(world, 'accept', finding)
    decide(world, 'reject', finding)
    _, outward, _ = report(world)
    assert finding.recommendation not in outward
    _, internal, _ = report(world, 'internal')
    assert finding.recommendation in internal and '已驳回' in internal and PRIVATE in internal
    with world[0].session() as db:
        from cn_contract.review.storage import read_run
        assert read_run(world[3].id, run.id, world[1], db=db) == run
        assert len(services.decisions(world[3].id, run.id, world[1], db)) == 2
    assert len(run.coverage) == 18 and finding.human_decision is None


def test_explicit_edit_changes_report_without_using_reason_or_overwriting_run(api):
    client, database, _, _ = api; matter, run, headers, _ = reviewed_case(api)
    finding = run['findings'][0]
    response = client.post(f'/api/matters/{matter}/findings/{finding["id"]}/decision', headers=headers,
        json={'run_id': run['id'], 'run_sha256': run['run_sha256'], 'decision': 'edit', 'reason': PRIVATE,
              'edited_analysis': EDIT_A, 'edited_recommendation': EDIT_R, 'edited_replacement_text': EDIT_P})
    assert response.status_code == 201, response.text
    current = client.get(f'/api/matters/{matter}/reviews/{run["id"]}').json()
    assert current['findings'] == run['findings']
    assert current['decision_snapshot']['resolved_findings'][0]['analysis'] == EDIT_A
    preview = client.post(f'/api/matters/{matter}/exports/preview', headers=headers,
        json={'run_id': run['id'], 'run_sha256': run['run_sha256'], 'audience': 'client', 'patch_ids': []})
    assert preview.status_code == 201, preview.text
    raw = client.get(f'/api/matters/{matter}/exports/{preview.json()["artifacts"][0]["id"]}/download').content
    text = all_parts(raw)
    assert EDIT_A in text and EDIT_R in text and EDIT_P in text and PRIVATE not in text
    assert finding['analysis'] not in text
    # Mock findings can share the same recommendation. Only the edited finding
    # is replaced; unrelated findings still retain their observations.
    assert text.count(finding['recommendation']) == sum(f['recommendation'] == finding['recommendation'] for f in run['findings'][1:])
    with database.session() as db:
        assert db.scalar(select(func.count()).select_from(ApprovalRow)) == 0


@pytest.mark.parametrize('kind,label', [('edit','待完成编辑'), ('request_info','待补资料'), ('refer','待专项复核')])
def test_pending_dispositions_are_tasks_not_original_client_recommendations(tmp_path, kind, label):
    world = world_with_history(tmp_path); finding = world[6].findings[0]
    decide(world, kind, finding)
    _, text, _ = report(world)
    assert label in text and finding.recommendation not in text and PRIVATE not in text


@pytest.mark.parametrize('kind', ['accept','edit','reject','request_info','refer'])
def test_any_new_decision_stales_old_bundle_download_and_marks_artifacts(tmp_path, kind):
    world = world_with_history(tmp_path); bundle = package(world)
    decide(world, kind)
    with world[0].session() as db:
        with pytest.raises(ServiceError) as error:
            approvals.read_bundle(bundle.id, world[1], db=db)
        assert error.value.code == 'APPROVAL_STALE'
        with pytest.raises(ServiceError) as error:
            approvals.download_artifact(bundle.artifacts[0].id, world[1], db=db)
        assert error.value.code == 'APPROVAL_STALE'
        assert all(db.get(ExportRow, str(a.id)).superseded for a in bundle.artifacts)
        assert all(__import__('pathlib').Path(a.storage_ref).exists() for a in bundle.artifacts)


def test_accept_snapshot_hash_is_stable_for_other_member_and_changes_for_history(tmp_path):
    world = world_with_history(tmp_path)
    decide(world, 'accept')
    bundle, text, metadata = report(world)
    assert 'decision_snapshot_sha256' in metadata
    assert world[6].findings[0].recommendation in text
    with world[0].session() as db:
        assert approvals.read_bundle(bundle.id, world[2], db=db) == bundle
        snap = export_storage.latest('decision_snapshot', bundle.id, db)
        assert snap is not None
        value = json.loads(snap.payload)
        assert value['sha256'] == metadata['decision_snapshot_sha256']
        assert value['version'] > 0 and value['actor_id'] == str(world[1].user_id)
    decide(world, 'accept')
    _, _, newer = report(world)
    assert newer['decision_snapshot_sha256'] != metadata['decision_snapshot_sha256']


@pytest.mark.parametrize('kind', ['reject','edit','request_info','refer','accept'])
def test_existing_approved_patch_cannot_survive_its_finding_disposition(tmp_path, kind):
    world = world_with_history(tmp_path); value = suggestion(world); patch = approved(world, value)
    finding = next(f for f in world[6].findings if f.id == patch.finding_id)
    decide(world, kind, finding)
    with world[0].session() as db, pytest.raises(ServiceError) as error:
        export_storage.load_patch(world[3].id, patch, world[1], db, audience='counterparty')
    assert error.value.code == 'APPROVAL_STALE'


def test_export_mid_build_decision_change_rolls_back_records_and_derived_files(tmp_path, monkeypatch):
    world = world_with_history(tmp_path); database, actor, _, matter, _, _, run = world
    actual = approvals.build
    with database.session() as db:
        count = db.scalar(select(func.count()).select_from(export_storage.ExportRecordRow))
        def changed(projection):
            value = FindingDecisionInput(run_id=run.id, run_sha256=web_storage.sha(run.model_dump(mode='json')),
                decision='reject', reason='故障注入中的真实后端处置')
            services.save_decision(matter.id, run.findings[0].id, value, actor, db)
            return actual(projection)
        monkeypatch.setattr(approvals, 'build', changed)
        with pytest.raises(ServiceError) as error:
            approvals.prepare_exports(run, 'client', [], actor, db=db)
        assert error.value.code == 'APPROVAL_STALE'
        assert db.scalar(select(func.count()).select_from(export_storage.ExportRecordRow)) == count
        assert db.scalar(select(func.count()).select_from(ExportRow)) == 0
        assert db.scalar(select(func.count()).select_from(web_storage.FindingDecisionRow)) == 0
    assert not list((database.storage_root / 'derived_exports').glob('*'))


def test_preview_idempotent_replay_and_download_recheck_decisions(api):
    client, _, _, _ = api; matter, run, headers, _ = reviewed_case(api)
    h = {**headers, 'Idempotency-Key': 'f03-preview'}
    body = {'run_id': run['id'], 'run_sha256': run['run_sha256'], 'audience': 'client', 'patch_ids': []}
    preview = client.post(f'/api/matters/{matter}/exports/preview', headers=h, json=body)
    assert preview.status_code == 201, preview.text
    decision = client.post(f'/api/matters/{matter}/findings/{run["findings"][0]["id"]}/decision', headers=headers,
        json={'run_id': run['id'], 'run_sha256': run['run_sha256'], 'decision': 'reject', 'reason': PRIVATE})
    assert decision.status_code == 201, decision.text
    replay = client.post(f'/api/matters/{matter}/exports/preview', headers=h, json=body)
    assert replay.status_code == 409 and replay.json()['code'] == 'APPROVAL_STALE'
    artifact = preview.json()['artifacts'][0]['id']
    download = client.get(f'/api/matters/{matter}/exports/{artifact}/download')
    assert download.status_code == 409 and download.json()['code'] == 'APPROVAL_STALE'


def test_original_human_decision_cannot_be_ignored_by_pure_projection(tmp_path):
    from cn_contract.exports.audience_filter import project
    from datetime import datetime, timezone
    world = setup(tmp_path); run = world[6]; finding = run.findings[0]
    decision = HumanDecision(decision='reject', reason=PRIVATE, actor_id=world[1].user_id, decided_at=datetime.now(timezone.utc))
    findings = (finding.model_copy(update={'human_decision': decision}), *run.findings[1:])
    derived = run.model_copy(update={'findings': findings})
    client = project(derived, 'client', [], [])
    assert finding.recommendation not in json.dumps(client, ensure_ascii=False)
    outward = project(derived, 'counterparty', [], [])
    assert PRIVATE not in json.dumps(outward)
    if finding.fallback: assert finding.fallback not in json.dumps(outward)


def test_edit_history_latest_body_and_exact_patch_require_new_approval(tmp_path):
    world = world_with_history(tmp_path); value = suggestion(world)
    finding = next(f for f in world[6].findings if f.id == value.finding_id)
    decide(world, 'edit', finding, edited_analysis=EDIT_A, edited_recommendation=EDIT_R, edited_replacement_text=EDIT_P)
    wrong = value.model_copy(update={'new_text': '与律师编辑不一致的旧文'})
    with world[0].session() as db, pytest.raises(ServiceError) as error:
        approvals.approve_patch(world[3].id, world[6].id, wrong, world[2], db=db, audiences=('counterparty',))
    assert error.value.code == 'APPROVAL_STALE'
    fresh = approved(world, value.model_copy(update={'new_text': EDIT_P}))
    _, outward, _ = report(world, 'counterparty', [fresh])
    assert EDIT_P in outward and EDIT_A not in outward and PRIVATE not in outward
    if finding.fallback: assert finding.fallback not in outward
    decide(world, 'edit', finding, edited_analysis=EDIT_A+'最新分析', edited_recommendation=EDIT_R+'最新建议',
        edited_replacement_text=EDIT_P+'最新替换')
    _, client, _ = report(world)
    assert EDIT_A+'最新分析' in client and EDIT_R+'最新建议' in client
    _, internal, _ = report(world, 'internal')
    assert EDIT_P in internal and EDIT_P+'最新替换' in internal and PRIVATE in internal
    with world[0].session() as db, pytest.raises(ServiceError):
        export_storage.load_patch(world[3].id, fresh, world[1], db, audience='counterparty')


def test_unrelated_finding_change_does_not_revoke_other_exact_patch(tmp_path):
    body = BODY + '<w:p><w:r><w:t>付款比例：60%。</w:t></w:r></w:p><w:p><w:r><w:t>付款比例：50%。</w:t></w:r></w:p>'
    world = world_with_history(tmp_path, body=body); patch = approved(world, suggestion(world))
    unrelated = next(f for f in world[6].findings if f.id != patch.finding_id)
    decide(world, 'reject', unrelated)
    with world[0].session() as db:
        assert export_storage.load_patch(world[3].id, patch, world[1], db, audience='counterparty')[0] == patch


@pytest.mark.parametrize('kind', ['reject','edit','request_info','refer'])
def test_cannot_approve_patch_under_unresolved_disposition(tmp_path, kind):
    world = world_with_history(tmp_path); value = suggestion(world)
    finding = next(f for f in world[6].findings if f.id == value.finding_id)
    decide(world, kind, finding)
    with world[0].session() as db, pytest.raises(ServiceError) as error:
        approvals.approve_patch(world[3].id, world[6].id, value, world[2], db=db, audiences=('counterparty',))
    assert error.value.code == 'APPROVAL_STALE'


def test_pure_counterparty_projection_refuses_rejected_patch(tmp_path):
    from cn_contract.exports.audience_filter import project
    from datetime import datetime, timezone
    world = setup(tmp_path); run = world[6]; patch = suggestion(world)
    decision = HumanDecision(decision='reject', reason=PRIVATE, actor_id=world[1].user_id,
        decided_at=datetime.now(timezone.utc))
    derived = run.model_copy(update={'findings': tuple(f.model_copy(update={'human_decision':decision})
        if f.id == patch.finding_id else f for f in run.findings)})
    with pytest.raises(ServiceError) as error: project(derived, 'counterparty', [patch], [])
    assert error.value.code == 'APPROVAL_STALE'


def test_decision_audit_failure_rolls_back_append_and_invalidation(tmp_path, monkeypatch):
    world = world_with_history(tmp_path); bundle = package(world)
    database, actor, _, matter, _, _, run = world
    with database.session() as db:
        before = db.scalar(select(func.count()).select_from(AuditRow))
        original = export_storage.audit
        def failing(*args, **kwargs):
            original(*args, **kwargs)
            raise RuntimeError('synthetic failure after audit flush')
        monkeypatch.setattr(export_storage, 'audit', failing)
        value = FindingDecisionInput(run_id=run.id, run_sha256=web_storage.sha(run.model_dump(mode='json')),
            decision='reject', reason=PRIVATE)
        with pytest.raises(RuntimeError): services.save_decision(matter.id, run.findings[0].id, value, actor, db)
        assert db.scalar(select(func.count()).select_from(web_storage.FindingDecisionRow)) == 0
        assert db.scalar(select(func.count()).select_from(AuditRow)) == before
        assert not db.get(ExportRow, str(bundle.artifacts[0].id)).superseded
    with database.session() as db: assert approvals.read_bundle(bundle.id, actor, db=db) == bundle


def test_decision_audit_contains_hashes_only_and_no_mock_formal_success(tmp_path):
    world = world_with_history(tmp_path); decide(world, 'accept')
    bundle = package(world)
    with world[0].session() as db:
        row = db.scalar(select(AuditRow).where(AuditRow.action == 'finding_decided'))
        assert row is not None and PRIVATE not in row.payload
        assert len(json.loads(row.payload)['after_hash']) == 64
        with pytest.raises(ServiceError) as error:
            approvals.approve_bundle(bundle.id, bundle.manifest_sha256, world[2], db=db)
        assert error.value.code == 'BLOCKED_LIVE'
        assert db.scalar(select(func.count()).select_from(ApprovalRow)) == 0


@pytest.mark.parametrize('revocation', ['membership','session'])
def test_snapshot_download_rechecks_current_caller_after_revocation(tmp_path, revocation):
    from cn_contract.persistence import MembershipRow
    from cn_contract.security import revoke_session
    world = world_with_history(tmp_path); decide(world, 'accept'); bundle = package(world)
    with world[0].session() as db:
        if revocation == 'membership': db.delete(db.get(MembershipRow, (str(world[3].id), str(world[2].user_id))))
        else: revoke_session(world[2].session_id, db)
    with world[0].session() as db, pytest.raises(ServiceError):
        approvals.download_artifact(bundle.artifacts[0].id, world[2], db=db)


def test_snapshot_does_not_allow_cross_matter_run_or_finding_write(api):
    client, _, _, _ = api; matter, run, headers, _ = reviewed_case(api)
    other = create_case(client, headers, title='另一个独立虚构案件')
    payload = {'run_id':run['id'], 'run_sha256':run['run_sha256'], 'decision':'reject', 'reason':PRIVATE}
    cross = client.post(f'/api/matters/{other}/findings/{run["findings"][0]["id"]}/decision', headers=headers, json=payload)
    assert cross.status_code == 403 and cross.json()['code'] == 'CROSS_MATTER_DENIED'
    unrelated = client.post(f'/api/matters/{matter}/findings/{uuid4()}/decision', headers=headers, json=payload)
    assert unrelated.status_code == 409
    assert client.get(f'/api/matters/{other}/reviews/{run["id"]}').status_code == 403


def test_canonical_review_history_is_consumed_without_web_initialization(tmp_path):
    world = setup(tmp_path); export_storage.initialize_storage(world[0])
    assert not getattr(world[0], '_web_storage_initialized', False)
    decide(world, 'reject')
    _, text, _ = report(world)
    assert world[6].findings[0].recommendation not in text


@pytest.mark.parametrize('revocation', ['role','disabled'])
def test_superseded_historical_author_revocation_does_not_block_new_effective_decision(tmp_path, revocation):
    from cn_contract.persistence import UserRow
    world = world_with_history(tmp_path); decide(world, 'reject')
    database, actor, reviewer, matter, _, _, run = world
    value = FindingDecisionInput(run_id=run.id, run_sha256=web_storage.sha(run.model_dump(mode='json')),
        decision='accept', reason='当前复核律师已再次确认')
    with database.session() as db: services.save_decision(matter.id, run.findings[0].id, value, reviewer, db)
    with database.session() as db:
        user = db.get(UserRow, str(actor.user_id))
        if revocation == 'role': user.roles = json.dumps(['assistant'])
        else: user.disabled = True
    with database.session() as db:
        bundle = approvals.prepare_exports(run, 'client', [], reviewer, db=db)
        assert approvals.download_artifact(bundle.artifacts[0].id, reviewer, db=db).getvalue().startswith(b'PK')
        assert len(services.decisions(matter.id, run.id, reviewer, db)) == 2


def test_generated_review_schema_matches_extended_explicit_edit_dto():
    from pathlib import Path
    from cn_contract.domain import ReviewRun
    stored = json.loads((Path(__file__).resolve().parents[2] / 'schemas/review-report.v2.schema.json').read_text(encoding='utf-8'))
    assert stored == ReviewRun.model_json_schema()


@pytest.mark.parametrize('bad', [
    {'decision':'accept','edited_analysis':EDIT_A,'edited_recommendation':EDIT_R},
    {'decision':'edit','edited_analysis':EDIT_A},
    {'decision':'edit','edited_recommendation':EDIT_R},
    {'decision':'edit','edited_analysis':' ','edited_recommendation':EDIT_R},
])
def test_api_rejects_ambiguous_or_non_edit_replacement_inputs(api, bad):
    client, _, _, _ = api; matter, run, headers, _ = reviewed_case(api)
    payload = {'run_id':run['id'],'run_sha256':run['run_sha256'],'reason':PRIVATE,**bad}
    response = client.post(f'/api/matters/{matter}/findings/{run["findings"][0]["id"]}/decision', headers=headers, json=payload)
    assert response.status_code == 422


@pytest.mark.parametrize('binding', ['hash','finding','actor'])
def test_corrupt_history_is_blocked_even_if_later_decision_would_override_it(tmp_path, binding):
    from cn_contract.review.decisions import read_snapshot
    from datetime import datetime, timezone
    world = world_with_history(tmp_path); database, actor, reviewer, matter, _, _, run = world
    decision = HumanDecision(decision='reject', reason=PRIVATE, actor_id=actor.user_id, decided_at=datetime.now(timezone.utc))
    with database.session() as db:
        db.add(web_storage.FindingDecisionRow(id=str(uuid4()), matter_id=str(matter.id), run_id=str(run.id),
            finding_id=str(uuid4()) if binding == 'finding' else str(run.findings[0].id),
            run_sha256='9'*64 if binding == 'hash' else web_storage.sha(run.model_dump(mode='json')),
            actor_id=str(reviewer.user_id) if binding == 'actor' else str(actor.user_id), payload=decision.model_dump_json()))
    with database.session() as db, pytest.raises(ServiceError) as error:
        read_snapshot(matter.id, run.id, reviewer, db=db)
    assert error.value.code == 'APPROVAL_STALE'


@pytest.mark.parametrize('first', ['export','decision'])
def test_concurrent_sessions_serialize_decision_and_export_without_mixed_snapshot(tmp_path, first):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    world = world_with_history(tmp_path); database, actor, _, matter, _, _, run = world
    held, second_started, release = Event(), Event(), Event()
    result = {}
    value = FindingDecisionInput(run_id=run.id, run_sha256=web_storage.sha(run.model_dump(mode='json')),
        decision='reject', reason=PRIVATE)
    def operation(kind, wait):
        if not wait: second_started.set()
        with database.session() as db:
            # Establish this connection's real BEGIN IMMEDIATE writer lock.
            db.scalar(select(func.count()).select_from(web_storage.FindingDecisionRow))
            if wait:
                held.set()
                assert release.wait(10)
            if kind == 'decision': services.save_decision(matter.id, run.findings[0].id, value, actor, db)
            else: result['bundle'] = approvals.prepare_exports(run, 'client', [], actor, db=db)
    with ThreadPoolExecutor(max_workers=2) as pool:
        leader = pool.submit(operation, first, True)
        assert held.wait(10)
        follower = pool.submit(operation, 'decision' if first == 'export' else 'export', False)
        assert second_started.wait(10)
        release.set(); leader.result(timeout=15); follower.result(timeout=15)
    with database.session() as db:
        if first == 'export':
            with pytest.raises(ServiceError) as error: approvals.read_bundle(result['bundle'].id, actor, db=db)
            assert error.value.code == 'APPROVAL_STALE'
        else:
            raw = approvals.download_artifact(result['bundle'].artifacts[0].id, actor, db=db).getvalue()
            assert run.findings[0].recommendation not in all_parts(raw)
        assert db.scalar(select(func.count()).select_from(web_storage.FindingDecisionRow)) == 1


def test_legacy_bundle_missing_decision_binding_only_current_before_first_decision(tmp_path):
    world = world_with_history(tmp_path); original = package(world)
    with world[0].session() as db:
        row = export_storage.latest('bundle', original.id, db)
        value = json.loads(row.payload)
        metadata = {k:v for k,v in value['metadata'].items() if k not in
            {'decision_snapshot_sha256','decision_snapshot_version','projection_version'}}
        legacy = original.model_copy(update={'id':uuid4()})
        digest = export_storage.sha({'bundle':legacy.model_dump(mode='json',exclude={'manifest_sha256'}),'metadata':metadata})
        legacy = legacy.model_copy(update={'manifest_sha256':digest})
        export_storage.append('bundle', legacy.id, {'bundle':legacy.model_dump(mode='json'),'metadata':metadata},
            world[1], world[3].id, db)
        assert approvals.read_bundle(legacy.id, world[2], db=db) == legacy
    decide(world, 'accept')
    with world[0].session() as db, pytest.raises(ServiceError) as error:
        approvals.read_bundle(legacy.id, world[2], db=db)
    assert error.value.code == 'APPROVAL_STALE'


def test_legacy_patch_missing_fingerprint_cannot_gain_implicit_approval(tmp_path):
    world = world_with_history(tmp_path); patch = approved(world, suggestion(world))
    with world[0].session() as db:
        original = export_storage.latest('patch_approval', patch.id, db)
        payload = json.loads(original.payload); payload.pop('finding_decision_sha256')
        export_storage.append('patch_approval', patch.id, payload, world[2], world[3].id, db)
        assert export_storage.load_patch(world[3].id, patch, world[1], db, audience='counterparty')[0] == patch
    finding = next(f for f in world[6].findings if f.id == patch.finding_id)
    decide(world, 'accept', finding)
    with world[0].session() as db, pytest.raises(ServiceError) as error:
        export_storage.load_patch(world[3].id, patch, world[1], db, audience='counterparty')
    assert error.value.code == 'APPROVAL_STALE'


@pytest.mark.parametrize('revocation', ['role','disabled'])
def test_latest_effective_author_revocation_stales_without_restoring_old_advice(tmp_path, revocation):
    from cn_contract.persistence import UserRow
    world = world_with_history(tmp_path); decide(world, 'reject'); bundle = package(world)
    with world[0].session() as db:
        author = db.get(UserRow,str(world[1].user_id))
        if revocation == 'role': author.roles=json.dumps(['assistant'])
        else: author.disabled=True
    with world[0].session() as db, pytest.raises(ServiceError) as error:
        approvals.read_bundle(bundle.id, world[2], db=db)
    assert error.value.code == 'APPROVAL_STALE'


def test_outer_rollback_restores_old_bundle_and_decision_history(tmp_path):
    world = world_with_history(tmp_path); bundle = package(world)
    database, actor, _, matter, _, _, run = world
    with database.session() as db: before = db.scalar(select(func.count()).select_from(AuditRow))
    with pytest.raises(RuntimeError):
        with database.session() as db:
            value=FindingDecisionInput(run_id=run.id,run_sha256=web_storage.sha(run.model_dump(mode='json')),
                decision='reject',reason=PRIVATE)
            services.save_decision(matter.id,run.findings[0].id,value,actor,db)
            raise RuntimeError('synthetic caller rolls back')
    with database.session() as db:
        assert services.decisions(matter.id,run.id,actor,db)==[]
        assert db.scalar(select(func.count()).select_from(AuditRow))==before
        assert not db.get(ExportRow,str(bundle.artifacts[0].id)).superseded
        assert approvals.read_bundle(bundle.id,actor,db=db)==bundle


def test_explicit_replacement_keeps_exact_whitespace_for_patch_approval(tmp_path):
    world = world_with_history(tmp_path); value = suggestion(world)
    finding = next(f for f in world[6].findings if f.id == value.finding_id)
    exact = '  律师明确保留首尾空白的拟替换整段。  '
    saved = decide(world, 'edit', finding, edited_analysis=EDIT_A, edited_recommendation=EDIT_R,
        edited_replacement_text=exact)
    assert saved['decision']['edited_replacement_text'] == exact
    patch = approved(world, value.model_copy(update={'new_text':exact}))
    with world[0].session() as db:
        assert export_storage.load_patch(world[3].id,patch,world[1],db,audience='counterparty')[0].new_text == exact


@pytest.mark.parametrize('revocation', ['role','disabled'])
def test_api_multiple_revoked_effective_authors_can_be_rechecked_one_finding_at_a_time(api, revocation):
    from cn_contract.persistence import UserRow
    client, database, identities, _ = api
    matter, run, headers, _ = reviewed_case(api, reviewer='reviewer')
    findings = run['findings'][:2]
    assert len(findings) == 2
    old_token = client.cookies.get('qx_session')
    def decision_body(kind='accept'):
        return {'run_id':run['id'],'run_sha256':run['run_sha256'],'decision':kind,'reason':'独立虚构逐条复核'}
    for finding in findings:
        response=client.post(f'/api/matters/{matter}/findings/{finding["id"]}/decision',headers=headers,json=decision_body())
        assert response.status_code==201,response.text
    structure_sha=client.get(f'/api/matters/{matter}/reviews/{run["id"]}').json()['decision_snapshot']['sha256']
    before = client.post(f'/api/matters/{matter}/exports/preview',headers=headers,
        json={'run_id':run['id'],'run_sha256':run['run_sha256'],'audience':'client','patch_ids':[]})
    assert before.status_code==201,before.text
    old_artifact = before.json()['artifacts'][0]['id']
    with database.session() as db:
        author = db.get(UserRow,str(identities['lawyer']))
        if revocation=='role': author.roles=json.dumps(['assistant'])
        else: author.disabled=True
    headers=sign_in(client,'reviewer')
    response=client.get(f'/api/matters/{matter}/reviews/{run["id"]}')
    assert response.status_code==200,response.text
    internal=response.json()
    assert internal['findings']==run['findings'] and internal['run_sha256']==run['run_sha256']
    authority=internal['decision_authority']
    assert authority['status']=='recheck_required'
    assert authority['decision_snapshot_sha256']==internal['decision_snapshot']['sha256']
    assert internal['decision_snapshot']['sha256']==structure_sha
    assert set(authority['recheck_finding_ids'])=={f['id'] for f in findings}
    assert len(internal['decisions'])==2
    denied=client.get(f'/api/matters/{matter}/exports/{old_artifact}/download')
    assert denied.status_code==409 and denied.json()['code']=='APPROVAL_STALE'
    bypass=client.post(f'/api/matters/{matter}/exports/preview',headers=headers,
        json={'run_id':run['id'],'run_sha256':run['run_sha256'],'audience':'client','patch_ids':[],
              'require_authority':False})
    assert bypass.status_code==422
    for index,finding in enumerate(findings):
        saved=client.post(f'/api/matters/{matter}/findings/{finding["id"]}/decision',headers=headers,json=decision_body())
        assert saved.status_code==201,saved.text
        internal=client.get(f'/api/matters/{matter}/reviews/{run["id"]}').json()
        assert len(internal['decisions'])==3+index
        assert internal['findings']==run['findings']
        preview=client.post(f'/api/matters/{matter}/exports/preview',headers=headers,
            json={'run_id':run['id'],'run_sha256':run['run_sha256'],'audience':'client','patch_ids':[]})
        if index==0:
            assert internal['decision_authority']['status']=='recheck_required'
            assert internal['decision_authority']['recheck_finding_ids']==[findings[1]['id']]
            assert preview.status_code==409 and preview.json()['code']=='APPROVAL_STALE'
            with database.session() as db:
                assert db.get(ExportRow,old_artifact).superseded
        else:
            assert internal['decision_authority']['status']=='current'
            assert internal['decision_authority']['recheck_finding_ids']==[]
            assert preview.status_code==201,preview.text
            current_artifact=preview.json()['artifacts'][0]['id']
            assert client.get(f'/api/matters/{matter}/exports/{current_artifact}/download').status_code==200
    old=client.get(f'/api/matters/{matter}/exports/{old_artifact}/download')
    assert old.status_code==409 and old.json()['code']=='APPROVAL_STALE'
    if revocation=='role':
        assistant_headers=sign_in(client,'lawyer')
        denied=client.post(f'/api/matters/{matter}/findings/{findings[0]["id"]}/decision',headers=assistant_headers,json=decision_body())
        assert denied.status_code==403
    else:
        client.cookies.set('qx_session',old_token)
        assert client.get(f'/api/matters/{matter}/reviews/{run["id"]}').status_code==401


@pytest.mark.parametrize('revocation', ['role','disabled'])
def test_service_partial_author_recovery_persists_while_other_findings_still_block_delivery(tmp_path, revocation):
    from cn_contract.persistence import UserRow
    body=BODY+'<w:p><w:r><w:t>付款比例：60%。</w:t></w:r></w:p><w:p><w:r><w:t>付款比例：50%。</w:t></w:r></w:p>'
    world=world_with_history(tmp_path,body=body); database,actor,reviewer,matter,_,_,run=world
    assert len(run.findings)>=2
    findings=run.findings[:2]
    for finding in findings: decide(world,'accept',finding)
    with database.session() as db:
        user=db.get(UserRow,str(actor.user_id))
        if revocation=='role': user.roles=json.dumps(['assistant'])
        else: user.disabled=True
    value=FindingDecisionInput(run_id=run.id,run_sha256=web_storage.sha(run.model_dump(mode='json')),
        decision='accept',reason='独立虚构获授权复核律师逐条接手')
    with database.session() as db:
        try: services.save_decision(matter.id,findings[0].id,value,reviewer,db)
        except ServiceError as error: pytest.fail('authorized partial correction must persist; got '+error.code)
        assert len(services.decisions(matter.id,run.id,reviewer,db))==3
        with pytest.raises(ServiceError) as error: approvals.prepare_exports(run,'client',[],reviewer,db=db)
        assert error.value.code=='APPROVAL_STALE'
    with database.session() as db:
        services.save_decision(matter.id,findings[1].id,value,reviewer,db)
        assert len(services.decisions(matter.id,run.id,reviewer,db))==4
        assert approvals.prepare_exports(run,'client',[],reviewer,db=db).artifacts
