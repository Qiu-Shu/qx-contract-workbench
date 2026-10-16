"""Explicit parser upgrades preserve history and never reuse confirmed facts."""
import importlib
from hashlib import sha256
from uuid import UUID

import pytest
from sqlalchemy import select

from cn_contract.documents.ingest import DOCX_MIME
from cn_contract.domain import FactSnapshot
from cn_contract.persistence import (ParseRow, FactSnapshotRow, get_fact_snapshot,
    save_fact_snapshot, fact_snapshot_sha256)
from cn_contract.security import authenticate
from tests.integration.test_assisted_review import assisted_api
from tests.integration.test_api import create_case, sign_in
from tests.integration.test_docx_office_parts import office_document, saved


def old_case(assisted_api, monkeypatch):
    import importlib
    ingestion = importlib.import_module('cn_contract.documents.ingest')
    original = ingestion.parse_docx
    first = office_document()
    second = office_document()
    second.add_paragraph('SYNTHETIC separate attachment 2200 CNY.')
    raw = [saved(first), saved(second)]
    client, database, ids, module = assisted_api.setup(extra_hashes=tuple(sha256(b).hexdigest() for b in raw))
    headers = sign_in(client)
    matter = create_case(client, headers, title='独立虚构解析升级')
    versions = []
    # Simulate a historical parser with a now-recognized metadata gap.
    def old_parser(*args, **kwargs):
        result = original(*args, **kwargs)
        return result.model_copy(update={'unsupported_parts': ('synthetic-old-format:manual_required',)})
    with monkeypatch.context() as prior:
        prior.setattr(ingestion, 'parse_docx', old_parser)
        for i, data in enumerate(raw):
            sent = client.post(f'/api/matters/{matter}/documents',
                headers={**headers, 'Idempotency-Key': f'old-{i}'},
                files={'file': (f'synthetic-{i}.docx', data, DOCX_MIME)}, data={'baseline_view': 'original'})
            assert sent.status_code == 202, sent.text
            assert module.run_next_job(database).state == 'completed'
            versions.append(sent.json())
        parsed = client.get(f'/api/matters/{matter}/documents/{versions[0]["version_id"]}/anchors').json()
        facts = client.get(f'/api/matters/{matter}/facts').json()
        candidate = client.post(f'/api/matters/{matter}/facts/candidates', headers=headers, json={
            'document_version_id': versions[0]['version_id'], 'document_sha256': versions[0]['sha256'],
            'fact_version': facts['version'], 'candidates': [{'field': 'total_price',
                'typed_value': {'kind': 'decimal', 'value': '14200'}, 'unit': 'CNY',
                'anchor_ids': [parsed['anchors'][0]['id']]}]})
        assert candidate.status_code == 201, candidate.text
        value = candidate.json()
        confirmed = client.post(f'/api/matters/{matter}/facts/confirm', headers=headers, json={
            'fact_version': value['version'], 'decisions': [{'fact_id': value['facts'][0]['id'],
                'decision': 'confirmed', 'confirmed_value': value['facts'][0]['typed_value'],
                'reason': '独立虚构旧版本确认'}]})
        assert confirmed.status_code == 200, confirmed.text
    body = {'document_hashes': {v['version_id']: v['sha256'] for v in versions},
        'fact_version': confirmed.json()['version'], 'reason': '升级解析后重新核对全部原件',
        'reconfirmation_acknowledged': True}
    return client, database, module, headers, matter, versions, raw, body


def submit(values, body=None, key='reparse-one', headers=None):
    client, _, _, actor_headers, matter, _, _, default = values
    return client.post(f'/api/matters/{matter}/documents/reparse',
        headers={**(actor_headers if headers is None else headers), 'Idempotency-Key': key},
        json=default if body is None else body)


def snapshots(database):
    with database.session() as db:
        return ([r.payload for r in db.scalars(select(ParseRow).order_by(ParseRow.id))],
            [r.payload for r in db.scalars(select(FactSnapshotRow).order_by(FactSnapshotRow.version))])


def test_reparse_all_old_versions_is_atomic_append_only_and_idempotent(assisted_api, monkeypatch):
    values = old_case(assisted_api, monkeypatch)
    client, database, module, headers, matter, versions, raw, body = values
    before = snapshots(database)
    for version in versions:
        assert client.get(f'/api/matters/{matter}/documents/{version["version_id"]}/anchors').status_code == 409
    sent = submit(values)
    assert sent.status_code == 202, sent.text
    assert module.run_next_job(database).state == 'completed'
    after = snapshots(database)
    assert after[0][:len(before[0])] == before[0] and len(after[0]) == len(before[0]) + 2
    assert after[1][:-1] == before[1]
    facts = client.get(f'/api/matters/{matter}/facts').json()
    assert facts['version'] == body['fact_version'] + 1
    assert len(facts['facts']) == 1
    assert facts['facts'][0]['confirmation_status'] == 'unconfirmed'
    assert facts['facts'][0]['confirmed_by'] is None
    assert client.get(f'/api/matters/{matter}/review-context').status_code == 409
    for version, data in zip(versions, raw):
        parsed = client.get(f'/api/matters/{matter}/documents/{version["version_id"]}/anchors')
        assert parsed.status_code == 200 and parsed.json()['anchors']
        original = client.get(f'/api/matters/{matter}/documents/{version["version_id"]}/original?sha256={version["sha256"]}')
        assert original.content == data
    repeated = submit(values)
    assert repeated.status_code == 202 and repeated.json() == sent.json()
    assert module.run_next_job(database) is None
    assert snapshots(database) == after


def test_reparse_second_file_failure_rolls_back_both_results_and_facts(assisted_api, monkeypatch):
    values = old_case(assisted_api, monkeypatch)
    _, database, module, _, _, _, _, _ = values
    from cn_contract.web import services
    original = services.parse_document
    attempts = []
    def interrupted(*args, **kwargs):
        attempts.append(True)
        if len(attempts) == 2:
            raise OSError('synthetic second-file interruption')
        return original(*args, **kwargs)
    before = snapshots(database)
    assert submit(values).status_code == 202
    monkeypatch.setattr(services, 'parse_document', interrupted)
    status = module.run_next_job(database)
    assert status.state == 'failed'
    assert len(attempts) == 2
    assert snapshots(database) == before


def test_reparse_changed_text_at_same_anchor_keeps_fact_only_in_history(assisted_api, monkeypatch):
    values = old_case(assisted_api, monkeypatch)
    client, database, module, _, matter, *_ = values
    before = snapshots(database)
    ingestion = importlib.import_module('cn_contract.documents.ingest')
    original = ingestion.parse_docx
    def changed_parser(*args, **kwargs):
        result = original(*args, **kwargs)
        anchor = result.anchors[0]
        quote = anchor.quote + ' SYNTHETIC newly supported text.'
        changed = anchor.model_copy(update={'quote': quote, 'end': len(quote),
            'quote_sha256': sha256(quote.encode('utf-8')).hexdigest()})
        assert changed.id == anchor.id
        return result.model_copy(update={'anchors': (changed, *result.anchors[1:])})
    monkeypatch.setattr(ingestion, 'parse_docx', changed_parser)
    assert submit(values).status_code == 202
    assert module.run_next_job(database).state == 'completed'
    assert client.get(f'/api/matters/{matter}/facts').json()['facts'] == []
    assert snapshots(database)[1][:-1] == before[1]


@pytest.mark.parametrize('change', ['hash', 'missing', 'fact_version', 'unchecked'])
def test_reparse_rejects_changed_scope_before_queue(assisted_api, monkeypatch, change):
    values = old_case(assisted_api, monkeypatch)
    body = {**values[-1], 'document_hashes': dict(values[-1]['document_hashes'])}
    if change == 'hash': body['document_hashes'][next(iter(body['document_hashes']))] = '0' * 64
    elif change == 'missing': body['document_hashes'].pop(next(iter(body['document_hashes'])))
    elif change == 'fact_version': body['fact_version'] += 1
    else: body['reconfirmation_acknowledged'] = False
    before = snapshots(values[1])
    assert submit(values, body).status_code in (409, 422)
    assert values[2].run_next_job(values[1]) is None
    assert snapshots(values[1]) == before


def test_reparse_requires_csrf_and_current_case_authorization(assisted_api, monkeypatch):
    values = old_case(assisted_api, monkeypatch)
    assert submit(values, headers={}).status_code == 403
    headers = sign_in(values[0], 'admin')
    assert submit(values, headers=headers).status_code == 403
    assert values[2].run_next_job(values[1]) is None


@pytest.mark.parametrize('change', ['logout', 'position'])
def test_reparse_rechecks_actor_and_case_after_queue(assisted_api, monkeypatch, change):
    values = old_case(assisted_api, monkeypatch)
    client, database, module, headers, matter, *_ = values
    before = snapshots(database)
    assert submit(values).status_code == 202
    if change == 'logout':
        assert client.post('/api/logout', headers=headers).status_code == 200
    else:
        response = client.post(f'/api/matters/{matter}/position', headers=headers,
            json={'position': 'seller', 'objectives': ['独立虚构改变立场']})
        assert response.status_code == 200, response.text
    assert module.run_next_job(database).state == 'blocked'
    assert snapshots(database) == before


def test_reparse_is_blocked_in_readonly_recovery(assisted_api, monkeypatch):
    from cn_contract.ops.storage import RestoreFenceRow
    values = old_case(assisted_api, monkeypatch)
    before = snapshots(values[1])
    with values[1].session() as db:
        db.add(RestoreFenceRow(ref='synthetic-fence',archive_sha256='1'*64,
            manifest_sha256='2'*64,payload='{}'))
    response = submit(values)
    assert response.status_code == 409 and response.json()['code'] == 'BLOCKED_LIVE'
    assert values[2].run_next_job(values[1]) is None
    assert snapshots(values[1]) == before


def test_reparse_current_files_removes_stale_history_blocker(assisted_api, monkeypatch):
    values = old_case(assisted_api, monkeypatch)
    client, database, module, headers, matter, versions, raw, body = values
    ingestion = importlib.import_module('cn_contract.documents.ingest')
    original = ingestion.parse_docx
    def old_parser(*args, **kwargs):
        result = original(*args, **kwargs)
        return result.model_copy(update={'unsupported_parts': ('synthetic-old-format:manual_required',)})
    with monkeypatch.context() as prior:
        prior.setattr(ingestion, 'parse_docx', old_parser)
        sent = client.post(f'/api/matters/{matter}/documents',
            headers={**headers, 'Idempotency-Key': 'superseding-attachment'},
            files={'file': ('synthetic-new-attachment.docx', raw[1], DOCX_MIME)},
            data={'baseline_view': 'original', 'supersedes_id': versions[1]['version_id']})
        assert sent.status_code == 202, sent.text
        assert module.run_next_job(database).state == 'completed'
    latest = sent.json()
    facts = client.get(f'/api/matters/{matter}/facts').json()
    assert len(facts['facts']) == 1
    body = {**body, 'fact_version': facts['version'], 'document_hashes': {
        versions[0]['version_id']: versions[0]['sha256'], latest['version_id']: latest['sha256']}}
    assert submit(values, body).status_code == 202
    assert module.run_next_job(database).state == 'completed'
    facts = client.get(f'/api/matters/{matter}/facts').json()
    fact = facts['facts'][0]
    result = client.post(f'/api/matters/{matter}/facts/confirm', headers=headers,
        json={'fact_version': facts['version'], 'decisions': [{'fact_id': fact['id'],
            'decision': 'confirmed', 'confirmed_value': fact['typed_value'],
            'reason': 'SYNTHETIC current file recheck'}]})
    assert result.status_code == 200, result.text


def test_superseded_anchor_cannot_be_confirmed_after_history_filter(assisted_api, monkeypatch):
    values = old_case(assisted_api, monkeypatch)
    client, database, module, headers, matter, versions, raw, body = values
    with database.session() as db:
        actor = authenticate(client.cookies.get('qx_session'), db)
        old_fact = get_fact_snapshot(UUID(matter), body['fact_version'], actor, db).facts[0]
    ingestion = importlib.import_module('cn_contract.documents.ingest')
    original = ingestion.parse_docx
    def old_parser(*args, **kwargs):
        result = original(*args, **kwargs)
        return result.model_copy(update={'unsupported_parts': ('synthetic-old-format:manual_required',)})
    with monkeypatch.context() as prior:
        prior.setattr(ingestion, 'parse_docx', old_parser)
        sent = client.post(f'/api/matters/{matter}/documents',
            headers={**headers, 'Idempotency-Key': 'superseding-fact-document'},
            files={'file': ('synthetic-new-primary.docx', raw[0], DOCX_MIME)},
            data={'baseline_view': 'original', 'supersedes_id': versions[0]['version_id']})
        assert sent.status_code == 202, sent.text
        assert module.run_next_job(database).state == 'completed'
    latest = sent.json()
    facts = client.get(f'/api/matters/{matter}/facts').json()
    body = {**body, 'fact_version': facts['version'], 'document_hashes': {
        versions[1]['version_id']: versions[1]['sha256'], latest['version_id']: latest['sha256']}}
    assert submit(values, body).status_code == 202
    assert module.run_next_job(database).state == 'completed'
    facts = client.get(f'/api/matters/{matter}/facts').json()
    assert facts['facts'] == []
    # Persisted candidate snapshots are not a trust root: replay an old anchor.
    stale = type(old_fact).model_validate({**old_fact.model_dump(mode='python'), 'version': facts['version'] + 1,
        'confirmation_status': 'unconfirmed', 'confirmed_by': None, 'confirmed_at': None})
    with database.session() as db:
        actor = authenticate(client.cookies.get('qx_session'), db)
        save_fact_snapshot(UUID(matter), FactSnapshot(version=stale.version, facts=(stale,),
            sha256=fact_snapshot_sha256((stale,))), actor, db)
    result = client.post(f'/api/matters/{matter}/facts/confirm', headers=headers,
        json={'fact_version': stale.version, 'decisions': [{'fact_id': str(stale.id),
            'decision': 'confirmed', 'confirmed_value': stale.typed_value.model_dump(mode='json'),
            'reason': 'SYNTHETIC stale anchor replay'}]})
    assert result.status_code == 409, result.text
    assert result.json()['code'] == 'VERSION_CONFLICT'


def test_reparse_does_not_revive_old_review_or_export_after_reconfirmation(assisted_api):
    from sqlalchemy import select
    from cn_contract.review.storage import ReviewRunRow
    from cn_contract.persistence import ExportRow
    from tests.integration.test_assisted_review import submit_proposal
    client, database, _, module = assisted_api
    matter, sent, parsed, confirmed, context, headers, body, run = submit_proposal(assisted_api)
    preview = client.post(f'/api/matters/{matter}/exports/preview', headers=headers,
        json={'run_id': run['id'], 'run_sha256': run['run_sha256'], 'audience': 'internal', 'patch_ids': []})
    assert preview.status_code == 201, preview.text
    artifact = preview.json()['artifacts'][0]['id']
    assert client.get(f'/api/matters/{matter}/exports/{artifact}/download').status_code == 200
    with database.session() as db:
        before = db.get(ReviewRunRow, run['id']).payload
    request = client.post(f'/api/matters/{matter}/documents/reparse',
        headers={**headers, 'Idempotency-Key': 'review-invalidation'},
        json={'document_hashes': context['document_hashes'], 'fact_version': confirmed['version'],
            'reason': 'SYNTHETIC parser upgrade recheck', 'reconfirmation_acknowledged': True})
    assert request.status_code == 202, request.text
    assert module.run_next_job(database).state == 'completed'
    facts = client.get(f'/api/matters/{matter}/facts').json()
    again = client.post(f'/api/matters/{matter}/facts/confirm', headers=headers,
        json={'fact_version': facts['version'], 'decisions': [
            {'fact_id': fact['id'], 'decision': 'confirmed', 'confirmed_value': fact['typed_value'],
             'reason': 'SYNTHETIC complete recheck'} for fact in facts['facts']]})
    assert again.status_code == 200, again.text
    assert client.get(f'/api/matters/{matter}/reviews/{run["id"]}').status_code == 409
    assert client.get(f'/api/matters/{matter}/exports/{artifact}/download').status_code == 409
    with database.session() as db:
        assert db.get(ReviewRunRow, run['id']).payload == before
        exports = db.scalars(select(ExportRow).where(ExportRow.matter_id == matter)).all()
        assert exports and all(row.superseded for row in exports)


@pytest.mark.parametrize('change', ['location', 'quote', 'unchanged'])
def test_reparse_drops_independent_source_fact_whose_location_disappears(assisted_api, monkeypatch, change):
    from hashlib import sha256
    from cn_contract.documents.anchors import make_anchor
    from tests.integration.test_api import create_case, sign_in
    from tests.integration.test_docx_office_parts import office_document, saved
    raw = saved(office_document())
    client, database, _, module = assisted_api.setup(extra_hashes=(sha256(raw).hexdigest(),))
    headers = sign_in(client)
    matter = create_case(client, headers, title='SYNTHETIC independent source location upgrade')
    ingestion = importlib.import_module('cn_contract.documents.ingest')
    original = ingestion.parse_docx
    def old_parser(*args, **kwargs):
        result = original(*args, **kwargs)
        if change == 'unchanged':
            return result
        anchor = result.anchors[0]
        legacy = make_anchor(result.version_id, anchor.part_name,
            anchor.element_id + '/legacy' if change == 'location' else anchor.element_id,
            anchor.quote + ' SYNTHETIC LEGACY TEXT' if change == 'quote' else anchor.quote)
        return result.model_copy(update={'anchors': (legacy, *result.anchors[1:])})
    with monkeypatch.context() as prior:
        prior.setattr(ingestion, 'parse_docx', old_parser)
        sent = client.post(f'/api/matters/{matter}/documents',
            headers={**headers, 'Idempotency-Key': 'old-location-file'},
            files={'file': ('synthetic-old-location.docx', raw, DOCX_MIME)}, data={'baseline_view': 'original'})
        assert sent.status_code == 202, sent.text
        assert module.run_next_job(database).state == 'completed'
        version = sent.json()
        parsed = client.get(f'/api/matters/{matter}/documents/{version["version_id"]}/anchors').json()
        facts = client.get(f'/api/matters/{matter}/facts').json()
        recorded = client.post(f'/api/matters/{matter}/page-verifications', headers=headers, json={
            'document_version_id': version['version_id'], 'document_sha256': version['sha256'],
            'fact_version': facts['version'], 'page': None, 'source_anchor_id': parsed['anchors'][0]['id'],
            'source_kind': 'lawyer_transcription', 'observed_text': parsed['anchors'][0]['quote'],
            'field': 'total_price', 'typed_value': {'kind': 'decimal', 'value': '14200'}, 'unit': 'CNY',
            'reason': 'SYNTHETIC original checked', 'original_page_checked': True,
            'previous_id': None, 'candidate_id': None, 'candidate_sha256': None})
        assert recorded.status_code == 200, recorded.text
        before = client.get(f'/api/matters/{matter}/facts').json()
        confirmed = client.post(f'/api/matters/{matter}/facts/confirm', headers=headers,
            json={'fact_version': before['version'], 'decisions': [
                {'fact_id': fact['id'], 'decision': 'confirmed', 'confirmed_value': fact['typed_value'],
                 'reason': 'SYNTHETIC prior original verification'} for fact in before['facts']]})
        assert confirmed.status_code == 200, confirmed.text
    facts = client.get(f'/api/matters/{matter}/facts').json()
    sent = client.post(f'/api/matters/{matter}/documents/reparse',
        headers={**headers, 'Idempotency-Key': 'source-location-reparse'},
        json={'document_hashes': {version['version_id']: version['sha256']},
              'fact_version': facts['version'], 'reason': 'SYNTHETIC anchor parser upgrade',
              'reconfirmation_acknowledged': True})
    assert sent.status_code == 202, sent.text
    assert module.run_next_job(database).state == 'completed'
    facts = client.get(f'/api/matters/{matter}/facts').json()
    if change == 'unchanged':
        assert len(facts['facts']) == 1
        assert facts['facts'][0]['confirmation_status'] == 'unconfirmed'
        assert facts['facts'][0]['confirmed_by'] is None
        confirmed = client.post(f'/api/matters/{matter}/facts/confirm', headers=headers,
            json={'fact_version': facts['version'], 'decisions': [
                {'fact_id': fact['id'], 'decision': 'confirmed', 'confirmed_value': fact['typed_value'],
                 'reason': 'SYNTHETIC rechecked original verification'} for fact in facts['facts']]})
        assert confirmed.status_code == 200, confirmed.text
        return
    if facts['facts']:
        rejected = client.post(f'/api/matters/{matter}/facts/confirm', headers=headers,
            json={'fact_version': facts['version'], 'decisions': [
                {'fact_id': fact['id'], 'decision': 'rejected', 'confirmed_value': fact['typed_value'],
                 'reason': 'SYNTHETIC obsolete source location'} for fact in facts['facts']]})
        assert rejected.status_code == 200, 'Stale source fact retained; cannot even reject: ' + rejected.text
    assert facts['facts'] == [], 'Obsolete source location must stay historical, not active'


@pytest.mark.parametrize('change', ['facts', 'document', 'archived', 'membership'])
def test_queued_reparse_rejects_new_current_state(assisted_api, monkeypatch, change):
    from cn_contract.persistence import MatterRow
    from cn_contract.security import remove_membership
    values = old_case(assisted_api, monkeypatch)
    client, database, module, headers, matter, versions, raw, body = values
    assert submit(values).status_code == 202
    if change == 'document':
        sent = client.post(f'/api/matters/{matter}/documents',
            headers={**headers, 'Idempotency-Key': 'concurrent-current-file'},
            files={'file': ('synthetic-concurrent.docx', raw[0], DOCX_MIME)}, data={'baseline_view': 'original'})
        assert sent.status_code == 202, sent.text
    else:
        with database.session() as db:
            actor = authenticate(client.cookies.get('qx_session'), db)
            if change == 'archived':
                db.get(MatterRow, matter).status = 'archived'
            elif change == 'membership':
                remove_membership(UUID(matter), actor.user_id, db)
            else:
                old = get_fact_snapshot(UUID(matter), body['fact_version'], actor, db)
                facts = tuple(type(fact).model_validate({**fact.model_dump(mode='python'),
                    'version': old.version + 1}) for fact in old.facts)
                save_fact_snapshot(UUID(matter), FactSnapshot(version=old.version+1,
                    facts=facts, sha256=fact_snapshot_sha256(facts)), actor, db)
    before = snapshots(database)
    assert module.run_next_job(database).state == 'blocked'
    assert snapshots(database) == before
