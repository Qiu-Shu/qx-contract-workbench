"""Actual local API authorization and immutable PDF byte delivery."""
import hashlib
from uuid import UUID

import pytest
from sqlalchemy import delete

from cn_contract.persistence import DocumentRow, MembershipRow
from tests.helpers.synthetic_documents import pdf
from tests.integration.test_api import create_case, sign_in
from tests.integration.test_assisted_review import assisted_api


def uploaded(assisted_api):
    raw = pdf(['SYNTHETIC total CNY 28460', 'SYNTHETIC no automatic acceptance'])
    digest = hashlib.sha256(raw).hexdigest()
    client, database, ids, app = assisted_api.setup([digest])
    headers = sign_in(client)
    matter = create_case(client, headers, reviewer='reviewer')
    response = client.post(f'/api/matters/{matter}/documents', headers={**headers, 'Idempotency-Key': 'viewer-upload'},
        files={'file': ('fictional-preview.pdf', raw, 'application/pdf')}, data={'baseline_view': 'original'})
    assert response.status_code == 202, response.text
    sent = response.json()
    app.run_next_job(database)
    url = f'/api/matters/{matter}/documents/{sent["version_id"]}/original?sha256={digest}'
    return client, database, ids, headers, matter, sent, raw, url


def test_authorized_original_is_exact_pdf_with_no_store(assisted_api):
    client, _, _, _, _, sent, raw, url = uploaded(assisted_api)
    response = client.get(url)
    assert response.status_code == 200, 'original viewer endpoint must exist'
    assert response.content == raw
    assert response.headers['content-type'].startswith('application/pdf')
    assert response.headers['cache-control'] == 'no-store'
    assert response.headers['x-content-sha256'] == sent['sha256']
    assert 'storage_ref' not in response.headers
    import json
    geometry=json.loads(response.headers['x-qx-pdf-geometry'])
    assert len(geometry)==2 and geometry[0]['media']==geometry[0]['crop']


@pytest.mark.parametrize('change', ['anonymous', 'cross_matter', 'revoked', 'wrong_hash', 'tampered', 'superseded'])
def test_original_read_rechecks_live_authority_and_version(assisted_api, change):
    client, database, ids, headers, matter, sent, raw, url = uploaded(assisted_api)
    expected = 409
    if change == 'anonymous': client.cookies.clear(); expected = 401
    elif change == 'cross_matter':
        another = create_case(client, headers)
        url = url.replace(matter, another)
        expected = 403
    elif change == 'revoked':
        with database.session() as db:
            db.execute(delete(MembershipRow).where(MembershipRow.matter_id == matter, MembershipRow.user_id == str(ids['lawyer'])))
        expected = 403
    elif change == 'wrong_hash': url = url.replace(sent['sha256'], '0' * 64)
    elif change == 'tampered':
        with database.session() as db:
            from cn_contract.persistence import read_version
            from cn_contract.security import authenticate
            actor = authenticate(client.cookies.get('qx_session'), db)
            version = read_version(UUID(matter), UUID(sent['version_id']), actor, db)
        path = database.storage_root / version.storage_ref
        path.chmod(0o600)  # only this test's disposable synthetic original
        path.write_bytes(raw + b'changed')
    else:
        response = client.post(f'/api/matters/{matter}/documents', headers={**headers, 'Idempotency-Key': 'viewer-new-version'},
            files={'file': ('fictional-preview.pdf', raw, 'application/pdf')}, data={'baseline_view':'original', 'supersedes_id': sent['version_id']})
        assert response.status_code == 202
    response = client.get(url)
    assert response.status_code == expected, response.text
    assert not response.content.startswith(b'%PDF')


def test_original_rejects_docx_without_leaking_path(assisted_api):
    from tests.integration.test_assisted_review import parsed_case
    client, _, _, _ = assisted_api
    matter, sent, *_ = parsed_case(assisted_api)
    response = client.get(f'/api/matters/{matter}/documents/{sent["version_id"]}/original?sha256={sent["sha256"]}')
    assert response.status_code == 415
    assert 'storage_ref' not in response.text and '.docx' not in response.text


def test_fact_page_offers_same_origin_pdf_panel(assisted_api):
    client, _, _, _, matter, _, _, _ = uploaded(assisted_api)
    response = client.get(f'/matters/{matter}/facts')
    assert response.status_code == 200
    assert 'id="pdf-panel"' in response.text
    assert 'type="module" src="/static/pdf-review.mjs"' in response.text
    assert 'https://' not in response.text
