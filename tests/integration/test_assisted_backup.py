"""Every admitted fiction must survive the same guarded restore pipeline."""
from pathlib import Path
import hashlib
import pytest
from cn_contract.domain import BackupConfig
from cn_contract.ops.backup import backup_and_verify, _registered_hashes
from cn_contract.security import login, authenticate
from cn_contract.web.assisted_demo_server import load_seed_policy
from tests.integration.test_assisted_review import assisted_api, parsed_case, CASES
from tests.helpers.synthetic_operations import keys


def test_current_seed_inventory_is_backed_by_backup_registry():
    assert set(load_seed_policy().document_hashes) <= _registered_hashes()


@pytest.mark.parametrize('case', CASES, ids=lambda case: case['id'])
def test_each_current_fixture_backup_restore(assisted_api, tmp_path, case):
    parsed_case(assisted_api,case)
    _,database,_,_=assisted_api
    with database.session() as db:
        token,_=login('admin','fictional-pass-12345',db)
        actor=authenticate(token,db)
    result=backup_and_verify(BackupConfig(storage_ref=str(tmp_path/'archives'),
        key_ref='synthetic-key-1',retention_days=30),database=database,actor=actor,
        key_resolver=keys(),restore_parent=tmp_path/'restores')
    assert result.ok and result.verified_file_count==1
    originals=list((Path(result.restored_root)/'protected').rglob('original.bin'))
    assert len(originals)==1
    assert hashlib.sha256(originals[0].read_bytes()).hexdigest()==case['sha256']
    assert 'OLD_SESSIONS_REVOKED' in result.limitations
