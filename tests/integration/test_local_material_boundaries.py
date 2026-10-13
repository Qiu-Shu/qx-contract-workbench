from pathlib import Path
from uuid import UUID
import sqlite3

import pytest
from fastapi.testclient import TestClient

from cn_contract.domain import BackupConfig, MatterCreateInput, Role
from cn_contract.security import authenticate, ServiceError
from cn_contract.persistence import get_parse_result
from tests.integration.test_local_workbench import local, login, PASSWORD
from tests.integration.test_local_materials import new_local_case, independent_docx, upload_and_parse


def test_local_direct_mock_intake_is_denied(local):
    from cn_contract.review.workflow import extract_document_candidates
    from cn_contract.review.model_adapter import MockProvider
    module, root = local
    module.initialize_workspace(root, 'local-lawyer', PASSWORD)
    with TestClient(module.build_local_app(root)) as client:
        headers = login(client)
        matter = UUID(new_local_case(client, headers))
        uploaded = upload_and_parse(client, headers, str(matter), independent_docx())
        with client.app.state.database.session() as db:
            actor = authenticate(client.cookies.get('qx_session'), db)
            parsed = get_parse_result(matter, UUID(uploaded['version_id']), actor, db)
            with pytest.raises(ServiceError) as denied:
                extract_document_candidates(parsed, MockProvider(), matter_id=matter, actor=actor, db=db)
            assert denied.value.code == 'DATA_POLICY_UNAPPROVED'


def test_backup_rechecks_local_case_at_snapshot_transaction(tmp_path, monkeypatch):
    from tests.helpers.synthetic_operations import world, keys
    from cn_contract.ops import backup
    from cn_contract.web.services import create_matter
    database, actor, _, _ = world(tmp_path)
    database._local_materials_enabled = True
    original_schema = backup.schema_reference
    inserted = []
    def concurrent_local_create(settings):
        if not inserted:
            with database.session() as db:
                local_matter = create_matter(MatterCreateInput(title='独立虚构并发本机案件',
                    contract_type='sales', review_mode='pre_sign', position='buyer',
                    objectives=('虚构隔离测试',), material_mode='local'), actor, db)
                inserted.append(local_matter.id)
        return original_schema(settings)
    monkeypatch.setattr(backup, 'schema_reference', concurrent_local_create)
    with pytest.raises(ServiceError) as denied:
        report = backup.backup_and_verify(BackupConfig(storage_ref=str(tmp_path/'archives'),
            key_ref='synthetic-key-1', retention_days=30), database=database, actor=actor,
            key_resolver=keys(), restore_parent=tmp_path/'restores')
        with sqlite3.connect(str(Path(report.restored_root)/'database.db')) as conn:
            assert conn.execute('select title from matters where id=?', (str(inserted[0]),)).fetchone() == ('独立虚构并发本机案件',)
    assert denied.value.code == 'DATA_POLICY_UNAPPROVED'
    assert not list((tmp_path/'archives').glob('*.cnbak'))


def test_upload_auth_csrf_cross_case_preserves_originals(local):
    module, root = local
    module.initialize_workspace(root, 'local-lawyer', PASSWORD)
    module.add_local_user(root, 'other-lawyer', PASSWORD, Role.HANDLING_LAWYER)
    with TestClient(module.build_local_app(root)) as client:
        headers = login(client)
        matter = new_local_case(client, headers)
        url = f'/api/matters/{matter}/documents'
        files = {'file': ('independent.docx', independent_docx(), 'application/vnd.openxmlformats-officedocument.wordprocessingml.document')}
        data = {'baseline_view':'original', 'local_processing_confirmed':'yes', 'local_policy_id':'local-workpaper-v1'}
        assert client.post(url, files=files, data=data).status_code == 403
        other = login(client, 'other-lawyer')
        assert client.post(url, headers=other, files=files, data=data).status_code == 403
        client.cookies.clear()
        assert client.post(url, headers=headers, files=files, data=data).status_code == 401
        assert not list((root/'protected').rglob('original.bin'))
