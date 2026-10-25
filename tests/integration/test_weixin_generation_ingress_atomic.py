"""Synthetic generation polls commit sources and checkpoints as one transaction."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import importlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy import event, text

from cn_contract import domain as d
from cn_contract.matters import create_matter
from cn_contract.ops import backup, workspace_backup
from cn_contract.persistence import Database, MembershipRow, read_original
from cn_contract.security import ServiceError, authenticate, login
from cn_contract.weixin_inbox import accounts, dispatch, ingress
from cn_contract.weixin_inbox.integrity import validate_weixin_records
from cn_contract.weixin_inbox.provenance_integrity import validate_descriptor_generations
from tests.helpers.legacy_assistant_backup import PASSWORD, PASSPHRASE, USERNAME
from tests.helpers.synthetic_weixin_generations import setup_history
from tests.helpers.synthetic_weixin_generation_service import append, request as generation_request
from tests.integration.test_weixin_dispatch import message
from tests.integration.test_weixin_dispatch_integrity import corrupt
from tests.integration.test_weixin_ingress_atomic import world
from tests.integration.test_weixin_provenance_backup import original_material


def api():
    name = 'cn_contract.weixin_inbox.generation_ingress'
    assert importlib.util.find_spec(name), 'D2g5c needs the dedicated atomic generation-poll service'
    return importlib.import_module(name)


def history(world):
    value = setup_history(world)
    value['generation'] = append(value)
    return value


def rows(db):
    tables = db.scalars(text("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"))
    return {name: [tuple(row) for row in db.execute(text('SELECT * FROM "'+name+'" ORDER BY rowid'))]
            for name in tables}


def checked_state(database):
    with database.session() as db:
        validate_weixin_records(db, allow_inbox=True)
        validate_descriptor_generations(db, allow_provenance=True)
        return rows(db)


def poll(h, messages=None):
    with h['database'].session() as db:
        revision, cursor = db.execute(text('SELECT checkpoint_revision,upstream_cursor FROM weixin_accounts WHERE id=:id'),
            {'id': str(h['account'].id)}).one()
    request = d.WeixinPollInput(request_id=uuid4(), expected_revision=revision, expected_cursor=cursor)
    raw = json.dumps({'ret': 0, 'msgs': messages if messages is not None else [message(50)],
                      'get_updates_buf': 'independent:cursor:'+str(revision+1)}, ensure_ascii=False).encode('utf-8')
    return request, raw


def record(service, h, request, raw):
    return service.record_generation_poll(h['actor'], h['account'].id, request, raw, database=h['database'])


def find(service, h, request_id):
    return service.find_generation_poll_receipt(h['actor'], h['account'].id, request_id, database=h['database'])


def denied(code, operation):
    with pytest.raises(ServiceError) as caught:
        operation()
    assert caught.value.code == code
    assert caught.value.status_code == (401 if code == 'AUTHORIZATION_REQUIRED' else
                                        403 if code == 'CROSS_MATTER_DENIED' else 409)


def target_link(h, descriptor):
    with h['database'].session() as db:
        row = db.execute(text('SELECT * FROM weixin_descriptor_generations WHERE descriptor_id=:id'),
            {'id': str(descriptor.id)}).mappings().one()
        return d.WeixinDescriptorGeneration(**row)


def assert_only_poll_changed(before, after):
    poll_tables = {'weixin_accounts', 'weixin_poll_receipts', 'weixin_inbox_descriptors', 'weixin_descriptor_generations'}
    assert {name: value for name, value in after.items() if name not in poll_tables} == {
        name: value for name, value in before.items() if name not in poll_tables}


def test_unknown_generation_poll_find_preserves_complete_history(world):
    service = api()
    h = history(world)
    before = checked_state(h['database'])
    assert service.find_generation_poll_receipt(h['actor'], h['account'].id, uuid4(), database=h['database']) is None
    assert checked_state(h['database']) == before


@pytest.mark.parametrize('point', ['sidecar', 'checkpoint', 'commit'])
def test_sql_and_commit_failure_rolls_back_poll_sidecar_and_checkpoint(world, monkeypatch, point):
    service = api(); h = history(world); database = h['database']
    request, raw = poll(h)
    before = checked_state(database)
    triggered = []
    if point == 'commit':
        def fail(session):
            triggered.append(point)
            raise OSError('independent synthetic generation pre-commit failure')
        with monkeypatch.context() as patch:
            patch.setattr(database.session_factory.class_, 'commit', fail)
            with pytest.raises(OSError):
                record(service, h, request, raw)
    else:
        def fail(connection, cursor, statement, parameters, context, executemany):
            sql = ' '.join(statement.lower().split())
            if ((point == 'sidecar' and sql.startswith('insert into weixin_descriptor_generations'))
                    or (point == 'checkpoint' and sql.startswith('update weixin_accounts'))):
                triggered.append(point)
                raise OSError('independent synthetic generation SQL failure')
        event.listen(database.engine, 'before_cursor_execute', fail)
        try:
            with pytest.raises(OSError):
                record(service, h, request, raw)
        finally:
            event.remove(database.engine, 'before_cursor_execute', fail)
    assert triggered == [point]
    assert checked_state(database) == before
    assert find(service, h, request.request_id) is None
    saved = record(service, h, request, raw)
    assert saved.next_revision == request.expected_revision+1 and saved.descriptor_count == 1
    assert target_link(h, saved.descriptors[0]).generation_id == h['generation'].id
    assert_only_poll_changed(before, checked_state(database))


def deny_projected_case(h, conversation_id):
    actor = h['actor']
    with h['database'].session() as db:
        matter = create_matter(d.MatterCreateInput(title='独立虚构固定回执权限案件', contract_type='sales',
            review_mode='pre_sign', position='buyer', objectives=('仅为当前权限验证',)), actor, db)
        intake = uuid4()
        db.execute(text('''INSERT INTO intake_cases(id,owner_id,request_id,request_sha256,current_revision,matter_id)
            VALUES(:id,:owner,:request,:sha,1,:matter)'''), dict(id=str(intake), owner=str(actor.user_id),
                request=str(uuid4()), sha='a'*64, matter=str(matter.id)))
        db.execute(text('UPDATE assistant_conversations SET projection_intake_id=:intake WHERE id=:id'),
            {'intake': str(intake), 'id': str(conversation_id)})
        db.delete(db.get(MembershipRow, (str(matter.id), str(actor.user_id))))


def test_lost_ack_find_and_exact_replay_use_fixed_target_after_later_acl_change(world, monkeypatch):
    service = api(); h = history(world); database = h['database']
    request, raw = poll(h)
    commit = database.session_factory.class_.commit
    committed = []
    def lose_ack(session):
        commit(session)
        committed.append(True)
        raise OSError('independent synthetic generation acknowledgement lost after commit')
    with monkeypatch.context() as patch:
        patch.setattr(database.session_factory.class_, 'commit', lose_ack)
        with pytest.raises(OSError):
            record(service, h, request, raw)
    assert committed == [True]
    saved = find(service, h, request.request_id)
    assert saved is not None and saved.next_revision == request.expected_revision+1
    second = append(h, generation_request(h, h['generation']))
    deny_projected_case(h, second.scope.conversation_id)
    before = checked_state(database)
    assert find(service, h, request.request_id) == saved
    assert record(service, h, request, raw) == saved
    assert checked_state(database) == before
    deny_projected_case(h, h['generation'].scope.conversation_id)
    before = checked_state(database)
    denied('CROSS_MATTER_DENIED', lambda: find(service, h, request.request_id))
    after = checked_state(database)
    assert_only_poll_changed(before, after)
    assert {name: value for name, value in after.items() if name != 'audit_events'} == {
        name: value for name, value in before.items() if name != 'audit_events'}


@pytest.mark.parametrize('same_request', [False, True])
def test_concurrent_generation_polls_serialize_checkpoint_and_exact_request(world, same_request):
    service = api(); h = history(world); database = h['database']
    request, raw = poll(h)
    before = checked_state(database)
    barrier = Barrier(2)
    def send(index):
        candidate = request if same_request or index == 0 else request.model_copy(update={'request_id': uuid4()})
        barrier.wait(timeout=10)
        try:
            return record(service, h, candidate, raw)
        except ServiceError as error:
            return error.code
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = [future.result(timeout=30) for future in [pool.submit(send, 0), pool.submit(send, 1)]]
    saved = [value for value in results if isinstance(value, d.WeixinPollReceipt)]
    assert len(saved) == (2 if same_request else 1)
    if same_request:
        assert saved[0] == saved[1]
    else:
        assert results.count('VERSION_CONFLICT') == 1
    after = checked_state(database)
    for table in ('weixin_poll_receipts', 'weixin_inbox_descriptors', 'weixin_descriptor_generations'):
        assert len(after[table]) == len(before[table])+1
    assert target_link(h, saved[0].descriptors[0]).generation_id == h['generation'].id


def test_generation_append_racing_poll_has_one_complete_historical_target(world):
    service = api(); h = history(world); database = h['database']
    request, raw = poll(h)
    generation_input = generation_request(h, h['generation'])
    before = checked_state(database)
    barrier = Barrier(2)
    def receive():
        barrier.wait(timeout=10)
        return record(service, h, request, raw)
    def switch():
        barrier.wait(timeout=10)
        try:
            return append(h, generation_input)
        except ServiceError as error:
            return error.code
    with ThreadPoolExecutor(max_workers=2) as pool:
        receive_future, switch_future = pool.submit(receive), pool.submit(switch)
        saved, changed = receive_future.result(timeout=30), switch_future.result(timeout=30)
    target = target_link(h, saved.descriptors[0])
    if isinstance(changed, d.WeixinPeerGeneration):
        assert target.generation_id == changed.id and saved.created_at > changed.created_at
    else:
        assert changed == 'VERSION_CONFLICT' and target.generation_id == h['generation'].id
    after = checked_state(database)
    assert len(after['weixin_poll_receipts']) == len(before['weixin_poll_receipts'])+1
    assert len(after['weixin_descriptor_generations']) == len(before['weixin_descriptor_generations'])+1


def test_new_python_process_reads_the_same_committed_generation_receipt(world):
    service = api(); h = history(world)
    request, raw = poll(h)
    saved = record(service, h, request, raw)
    before = checked_state(h['database'])
    code = '''import sys
from pathlib import Path
from uuid import UUID
from cn_contract import domain as d
from cn_contract.config import load_settings
from cn_contract.persistence import Database
from cn_contract.ops import backup
from cn_contract.weixin_inbox.generation_ingress import find_generation_poll_receipt
from cn_contract.weixin_inbox.provenance_integrity import validate_descriptor_generations
root=Path(sys.argv[1]); database=Database('sqlite:///'+str(root/'workbench.db'),root/'protected',load_settings(),initialize_schema=False)
backup._mark_storage_flags(database)
try:
    result=find_generation_poll_receipt(d.Actor.model_validate_json(sys.argv[2]),UUID(sys.argv[3]),UUID(sys.argv[4]),database=database)
    with database.session() as db: validate_descriptor_generations(db,allow_provenance=True)
    print(result.model_dump_json())
finally: database.engine.dispose()
'''
    run = subprocess.run([sys.executable, '-B', '-X', 'utf8', '-c', code, str(h['root']),
        h['actor'].model_dump_json(), str(h['account'].id), str(request.request_id)],
        capture_output=True, text=True, timeout=30)
    assert run.returncode == 0, run.stderr
    assert json.loads(run.stdout) == saved.model_dump(mode='json')
    assert checked_state(h['database']) == before


def test_real_qxbak_preserves_sources_and_restored_receipt_lookup_only(world, tmp_path):
    service = api(); h = history(world); database = h['database']; root = h['root']
    matter, version, material = original_material(h)
    request, raw = poll(h)
    saved = record(service, h, request, raw)
    before = checked_state(database)
    original = {path.relative_to(root).as_posix(): path.read_bytes() for path in root.rglob('*') if path.is_file()}
    archive = tmp_path/'独立合成代际原子收件.qxbak'
    workspace_backup.create_workspace_backup(root, archive, PASSPHRASE, data_parent=tmp_path)
    result = workspace_backup.restore_workspace_backup(archive, tmp_path/'独立合成代际恢复', PASSPHRASE)
    target = Path(result['restored_root'])
    restored = Database('sqlite:///'+str(target/'workbench.db'), target/'protected', database.settings, initialize_schema=False)
    backup._mark_storage_flags(restored)
    try:
        denied('AUTHORIZATION_REQUIRED', lambda: service.find_generation_poll_receipt(
            h['actor'], h['account'].id, request.request_id, database=restored))
        with restored.session() as db:
            token, _ = login(USERNAME, PASSWORD, db)
            current = authenticate(token, db)
            assert read_original(matter.id, version.id, current, db) == material
            fence = json.loads(db.scalar(text('SELECT payload FROM ops_restore_fences ORDER BY rowid DESC LIMIT 1')))
            assert fence['old_sessions_revoked'] is True
            for flag in ('weixin_inbox_enabled', 'weixin_dispatch_enabled', 'weixin_generation_enabled', 'live_egress'):
                assert fence[flag] is False
        restored_before = checked_state(restored)
        assert {name: value for name, value in restored_before.items() if name.startswith('weixin_')} == {
            name: value for name, value in before.items() if name.startswith('weixin_')}
        assert service.find_generation_poll_receipt(current, h['account'].id, request.request_id, database=restored) == saved
        denied('BLOCKED_LIVE', lambda: service.record_generation_poll(current, h['account'].id, request, raw, database=restored))
        assert checked_state(restored) == restored_before
    finally:
        restored.engine.dispose()
    assert checked_state(database) == before
    assert {path.relative_to(root).as_posix(): path.read_bytes() for path in root.rglob('*') if path.is_file()} == original


@pytest.mark.parametrize('reverse', [False, True])
def test_cross_generation_reply_discovery_rejects_entire_poll_and_cursor(world, reverse):
    service = api(); h = history(world)
    first_request, first_raw = poll(h, [message(80, reply=81 if reverse else None)])
    record(service, h, first_request, first_raw)
    append(h, generation_request(h, h['generation']))
    request, raw = poll(h, [message(81, reply=None if reverse else 80), message(82)])
    before = checked_state(h['database'])
    denied('VERSION_CONFLICT', lambda: record(service, h, request, raw))
    assert checked_state(h['database']) == before
    assert find(service, h, request.request_id) is None


def test_wall_clock_repetition_still_orders_each_poll_after_all_generation_activity(world, monkeypatch):
    service = api(); h = history(world)
    frozen = h['generation'].created_at.isoformat()
    with monkeypatch.context() as patch:
        patch.setattr(ingress, '_at', lambda: frozen)
        request, raw = poll(h)
        first = record(service, h, request, raw)
        checked_state(h['database'])
        request, raw = poll(h, [message(51)])
        second = record(service, h, request, raw)
    assert second.created_at > first.created_at > h['generation'].created_at
    assert first.created_at.utcoffset() == second.created_at.utcoffset() == timedelta(0)
    assert target_link(h, second.descriptors[0]).generation_id == h['generation'].id
    checked_state(h['database'])


def test_existing_ingress_refresh_and_dispatch_stay_paused_after_new_poll(world):
    service = api(); h = history(world)
    request, raw = poll(h)
    saved = record(service, h, request, raw)
    before = checked_state(h['database'])
    denied('STATE_CONFLICT', lambda: ingress.record_synthetic_poll(h['actor'], h['account'].id, request, raw, database=h['database']))
    denied('STATE_CONFLICT', lambda: accounts.refresh_synthetic_peer(h['actor'], h['mapping'].id,
        h['grant_request'], database=h['database']))
    denied('STATE_CONFLICT', lambda: dispatch.dispatch_synthetic_descriptor(h['actor'],
        saved.descriptors[0].id, database=h['database']))
    assert checked_state(h['database']) == before


def test_corrupt_existing_provenance_rejects_new_poll_without_any_partial_write(world):
    service = api(); h = history(world); database = h['database']
    request, raw = poll(h)
    saved = record(service, h, request, raw)
    original = target_link(h, saved.descriptors[0]).payload_sha256
    with database.session() as db:
        corrupt(db, 'UPDATE weixin_descriptor_generations SET payload_sha256=:sha WHERE descriptor_id=:id',
            {'sha': 'f'*64, 'id': str(saved.descriptors[0].id)})
    with database.session() as db:
        before = rows(db)
        with pytest.raises(ValueError, match='WEIXIN_PROVENANCE_INTEGRITY'):
            validate_descriptor_generations(db, allow_provenance=True)
    request, raw = poll(h, [message(51)])
    denied('VERSION_CONFLICT', lambda: record(service, h, request, raw))
    with database.session() as db:
        assert rows(db) == before
        corrupt(db, 'UPDATE weixin_descriptor_generations SET payload_sha256=:sha WHERE descriptor_id=:id',
            {'sha': original, 'id': str(saved.descriptors[0].id)})
    checked_state(database)
