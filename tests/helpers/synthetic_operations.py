"""T12 actual standalone fictional SQLite/original with no real credentials."""
import importlib
import importlib.util
from io import BytesIO
from uuid import uuid4

from cn_contract.config import load_settings
from cn_contract.domain import Matter, Role, UploadMeta
from cn_contract.persistence import Database, provision_matter
from cn_contract.security import provision_user, login, authenticate
from cn_contract.web.app import initialize_storage
from cn_contract.review.synthetic import select_fixture
from cn_contract.documents import ingest


def feature(module, name):
    assert importlib.util.find_spec('cn_contract.ops') is not None, 'T12 requires actual operations services'
    assert importlib.util.find_spec('cn_contract.ops.'+module) is not None, 'T12 requires '+module
    result = getattr(importlib.import_module('cn_contract.ops.'+module), name, None)
    assert callable(result), 'T12 requires '+name
    return result


def world(tmp_path):
    database = Database('sqlite:///'+str(tmp_path/'source.db'), tmp_path/'source-store', load_settings())
    initialize_storage(database)
    with database.session() as db:
        user = provision_user('synthetic-ops-admin', 'local-test-password', {Role.ADMIN, Role.HANDLING_LAWYER}, db)
        token, _ = login('synthetic-ops-admin', 'local-test-password', db)
        actor = authenticate(token, db)
        matter = Matter(id=uuid4(), client_ref='SYNTHETIC', title='独立虚构T12案件', jurisdiction='CN-mainland',
            contract_type='sales', review_mode='pre_sign', position='buyer', objectives=(), member_ids={user},
            status='intake', active_fact_version=None, active_policy_version=None, gate_issues=())
        provision_matter(matter, db)
        _, _, path, raw = select_fixture('sales')
        version = ingest(BytesIO(raw), UploadMeta(matter_id=matter.id, original_name=path.name,
            mime='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            baseline_view='original', supersedes_id=None), actor, db=db)
    return database, actor, matter, version


def keys():
    # Clearly synthetic public test key material; never an external credential.
    return feature('backup', 'SyntheticKeyStore')({'synthetic-key-1': bytes(range(32))})


def seed_operational_world(tmp_path):
    """Actual registered original/review/patch/bundles/unknown ledger/pending jobs."""
    from fastapi.testclient import TestClient
    from cn_contract.web import app as web
    from tests.helpers.synthetic_queries import setup, plan, execute
    from tests.integration.test_api import reviewed_case
    from cn_contract.web.jobs import start_job, claim_next_job
    from cn_contract.web.storage import sha
    from cn_contract.domain import JobInput
    from sqlalchemy import select
    from cn_contract.exports.storage import ExportRecordRow
    context = setup(tmp_path, price='15', mode='timeout')
    database, owner, query_actor, query_matter, _, _ = context
    web.initialize_storage(database)
    with database.session() as db:
        provision_user('lawyer', 'fictional-pass-12345', {Role.HANDLING_LAWYER}, db)
    app = web.create_app(database.settings, database=database)
    with TestClient(app) as client:
        api = (client, database, {}, web)
        matter, run, headers, sent = reviewed_case(api)
        finding = next(f for f in run['findings'] if f['severity'] != 'high')
        anchors = client.get(f'/api/matters/{matter}/documents/{sent["version_id"]}/anchors').json()['anchors']
        anchor = next(a for a in anchors if a['id'] in finding['anchor_ids']+finding['cross_anchor_ids'])
        response = client.post(f'/api/matters/{matter}/patches/approve', headers=headers, json={
            'run_id': run['id'], 'run_sha256': run['run_sha256'], 'finding_id': finding['id'], 'anchor_id': anchor['id'],
            'new_text': '虚构T12测试：具体安排由双方书面确认。', 'reason': '完整原文与新文人工技术核对', 'audiences': ['internal', 'client', 'counterparty']})
        assert response.status_code == 201, response.text
        patch = response.json()
        from cn_contract.exports.redline_adapter import apply_patch
        from cn_contract.persistence import read_version
        from cn_contract.domain import Patch
        from uuid import UUID
        with database.session() as db:
            actor = authenticate(client.cookies.get('qx_session'), db)
            actual_version = read_version(UUID(matter), UUID(sent['version_id']), actor, db)
            result = apply_patch(actual_version, Patch.model_validate(patch), actor=actor, db=db)
            assert result.status == 'applied' and result.target_sha256
        bundles, artifacts = [], []
        for audience in ('internal', 'client', 'counterparty'):
            response = client.post(f'/api/matters/{matter}/exports/preview', headers=headers, json={
                'run_id': run['id'], 'run_sha256': run['run_sha256'], 'audience': audience, 'patch_ids': [patch['id']]})
            assert response.status_code == 201, response.text
            bundles.append(response.json())
            for item in response.json()['artifacts']:
                response_bytes = client.get(f'/api/matters/{matter}/exports/{item["id"]}/download')
                assert response_bytes.status_code == 200
                artifacts.append({'id': item['id'], 'sha256': item['content_sha256'], 'raw': response_bytes.content})
    unknown_plan = plan(context)
    receipts, transport = execute(context, unknown_plan)
    assert receipts[0].billing_state == 'sent_unknown' and transport.dispatch_count == 1
    extra_plan = plan(context)
    local_plan = plan(context, scope='Q0')
    payload = {'plan_id': str(local_plan.id), 'plan_sha256': local_plan.plan_sha256}
    job_input = JobInput(matter_id=query_matter.id, job_type='query', parameters_sha256=sha(payload))
    running = start_job(job_input, query_actor, database=database, parameters=payload, idempotency_key='restore-running')
    assert claim_next_job(database) == running.id
    queued = start_job(job_input, query_actor, database=database, parameters=payload, idempotency_key='restore-queued')
    with database.session() as db:
        patch_rows = list(db.scalars(select(ExportRecordRow).where(ExportRecordRow.kind == 'patch_result')))
        patch_refs = [r.ref for r in patch_rows]
        assert patch_refs, 'actual standalone patch_result must exist'
    return {'database': database, 'owner': owner, 'query_actor': query_actor, 'query_matter': query_matter,
        'unknown_plan': unknown_plan, 'extra_plan': extra_plan, 'matter_id': matter, 'run': run,
        'sent': sent, 'patch': patch, 'bundles': bundles, 'artifacts': artifacts, 'patch_result_refs': patch_refs,
        'pending_job_ids': (running.id, queued.id), 'context': context}


def rewrite_synthetic_archive(report, target, *, header_change=None, manifest_change=None, member_change=None):
    """Authenticated negative fixture using public test bytes, no real credential."""
    import json, os
    from zipfile import ZipFile, ZIP_STORED
    from cn_contract.ops.backup import _decode_archive, MAGIC, encode
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    _, header, plain = _decode_archive(report.backup_ref, keys())
    with ZipFile(BytesIO(plain)) as archive:
        members = {i.filename: archive.read(i) for i in archive.infolist()}
    manifest = json.loads(members['manifest.json'])
    if manifest_change: manifest_change(manifest)
    members['manifest.json'] = encode(manifest)
    if member_change: member_change(members)
    if header_change: header_change(header)
    out = BytesIO()
    with ZipFile(out, 'w', compression=ZIP_STORED) as archive:
        for name, raw in members.items(): archive.writestr(name, raw)
    header_raw = encode(header)
    aad = MAGIC+len(header_raw).to_bytes(4, 'big')+header_raw
    nonce = os.urandom(12)
    target.write_bytes(aad+nonce+AESGCM(bytes(range(32))).encrypt(nonce, out.getvalue(), aad))
