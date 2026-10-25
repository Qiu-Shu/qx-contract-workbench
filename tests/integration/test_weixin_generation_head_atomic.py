"""Independent real-SQL head snapshots never mix generation and checkpoint reads."""
from concurrent.futures import ThreadPoolExecutor
import json
from threading import Event, current_thread
from uuid import uuid4

import pytest
from sqlalchemy import event, text

from cn_contract import domain as d
from cn_contract.ops import backup
from cn_contract.persistence import Database
from cn_contract.security import ServiceError
from cn_contract.weixin_inbox import ingress
from tests.helpers.synthetic_weixin_generation_service import api, append, request
from tests.helpers.synthetic_weixin_generations import setup_history, state
from tests.integration.test_weixin_dispatch import message
from tests.integration.test_weixin_dispatch_integrity import corrupt
from tests.integration.test_weixin_ingress_atomic import world


def head(history, *, database=None):
    service = api()
    operation = getattr(service, 'read_peer_generation_head', None)
    assert callable(operation), 'D2g3 needs an atomic current generation head service'
    return operation(history['actor'], history['mapping'].id,
        database=database if database is not None else history['database'])


def assert_head(value, *, generation, digest, scope, scope_digest, checkpoint):
    assert value.model_dump(mode='json') == {
        'mode':'synthetic', 'state':'history_only', 'generation':generation,
        'generation_sha256':digest, 'scope':scope.model_dump(mode='json'),
        'scope_sha256':scope_digest, 'checkpoint_revision':checkpoint,
    }


def ordered_transactions(database, first_call, second_call, *, first_mutation=None):
    """Release the holder only after the other real SQLite session tries BEGIN."""
    locked, contender_began = Event(), Event()
    first_thread = []

    def before(connection, cursor, statement, parameters, context, executemany):
        normalized = ' '.join(statement.lower().split())
        name = current_thread().name
        if normalized == 'begin immediate' and first_thread and name != first_thread[0]:
            contender_began.set()
        if first_mutation and normalized.startswith(first_mutation) and name == first_thread[0]:
            locked.set()
            assert contender_began.wait(timeout=10), 'second actual SQLite session did not contend'

    def after(connection, cursor, statement, parameters, context, executemany):
        if (not first_mutation and ' '.join(statement.lower().split()) == 'begin immediate'
                and current_thread().name == first_thread[0]):
            locked.set()
            assert contender_began.wait(timeout=10), 'head did not retain its BEGIN IMMEDIATE lock'

    def first():
        first_thread.append(current_thread().name)
        return first_call()

    event.listen(database.engine, 'before_cursor_execute', before)
    event.listen(database.engine, 'after_cursor_execute', after)
    try:
        with ThreadPoolExecutor(max_workers=2, thread_name_prefix='generation-head') as pool:
            earlier = pool.submit(first)
            assert locked.wait(timeout=10), 'first operation did not acquire its real SQLite transaction'
            later = pool.submit(second_call)
            result = earlier.result(timeout=30), later.result(timeout=30)
    finally:
        event.remove(database.engine, 'before_cursor_execute', before)
        event.remove(database.engine, 'after_cursor_execute', after)
    assert contender_began.is_set()
    return result


@pytest.mark.parametrize('winner', ['head', 'append'])
def test_head_and_append_serialize_old_or_complete_new_snapshot(world, winner):
    h = setup_history(world)
    value = request(h)
    # Fail before launching any worker when the requested public operation is absent.
    old = head(h)
    assert_head(old, generation=0, digest=None, scope=h['grant'].scope,
        scope_digest=h['grant'].scope_sha256, checkpoint=2)
    calls = {'head':lambda:head(h), 'append':lambda:append(h, value)}
    later = 'append' if winner == 'head' else 'head'
    first, second = ordered_transactions(h['database'], calls[winner], calls[later],
        first_mutation='insert into weixin_peer_generations' if winner == 'append' else None)
    observed, saved = (first, second) if winner == 'head' else (second, first)
    if winner == 'head':
        assert observed == old
    else:
        assert_head(observed, generation=1, digest=saved.generation_sha256,
            scope=h['targets'][0][0].scope, scope_digest=saved.scope_sha256, checkpoint=2)
    fresh = head(h)
    assert_head(fresh, generation=1, digest=saved.generation_sha256,
        scope=h['targets'][0][0].scope, scope_digest=saved.scope_sha256, checkpoint=2)
    with pytest.raises(ServiceError) as stale:
        append(h, request(h, task_binding_id=h['targets'][1][1].id,
            expected_scope=h['targets'][1][0].scope,
            expected_generation=old.generation,
            expected_previous_generation_sha256=old.generation_sha256,
            expected_previous_scope_sha256=old.scope_sha256,
            expected_checkpoint_revision=old.checkpoint_revision))
    assert (stale.value.code, stale.value.status_code) == ('VERSION_CONFLICT', 409)
    assert head(h) == fresh


@pytest.mark.parametrize('winner', ['head', 'poll'])
def test_head_and_poll_serialize_checkpoint_and_reject_stale_checkpoint(world, winner):
    h = setup_history(world)
    old = head(h)
    poll_input = d.WeixinPollInput(request_id=uuid4(), expected_revision=2, expected_cursor='opaque:2')
    raw = json.dumps({'ret':0, 'msgs':[message(90)], 'get_updates_buf':'opaque:3'},
        ensure_ascii=False).encode('utf-8')
    calls = {'head':lambda:head(h), 'poll':lambda:ingress.record_synthetic_poll(h['actor'],
        h['account'].id, poll_input, raw, database=h['database'])}
    later = 'poll' if winner == 'head' else 'head'
    first, second = ordered_transactions(h['database'], calls[winner], calls[later],
        first_mutation='update weixin_accounts' if winner == 'poll' else None)
    observed, received = (first, second) if winner == 'head' else (second, first)
    assert received.next_revision == 3
    assert_head(observed, generation=0, digest=None, scope=h['grant'].scope,
        scope_digest=h['grant'].scope_sha256, checkpoint=2 if winner == 'head' else 3)
    fresh = head(h)
    assert_head(fresh, generation=0, digest=None, scope=h['grant'].scope,
        scope_digest=h['grant'].scope_sha256, checkpoint=3)
    before = state(h['database'])
    with pytest.raises(ServiceError) as stale:
        append(h, request(h, expected_checkpoint_revision=old.checkpoint_revision))
    assert (stale.value.code, stale.value.status_code) == ('VERSION_CONFLICT', 409)
    assert state(h['database']) == before


@pytest.mark.parametrize('family', ['scope', 'grant', 'generation'])
def test_head_rejects_corrupt_authorization_or_generation_without_repair(world, family):
    h = setup_history(world)
    head(h)
    if family == 'generation':
        append(h)
    with h['database'].session() as db:
        if family == 'scope':
            corrupt(db, 'UPDATE weixin_peer_bindings SET scope_sha256=:sha WHERE id=:id',
                {'id':str(h['mapping'].id), 'sha':'f'*64})
        elif family == 'grant':
            corrupt(db, 'UPDATE weixin_peer_scope_grants SET grant_sha256=:sha', {'sha':'f'*64})
        else:
            corrupt(db, 'UPDATE weixin_peer_generations SET generation_sha256=:sha', {'sha':'f'*64})
    before = state(h['database'])
    with pytest.raises(ServiceError) as rejected:
        head(h)
    assert (rejected.value.code, rejected.value.status_code) == ('VERSION_CONFLICT', 409)
    assert state(h['database']) == before


@pytest.mark.parametrize('changed', ['previous_schema', 'pre_inbox_schema', 'unknown_schema'])
def test_head_requires_exact_schema17_and_never_upgrades(world, changed):
    h = setup_history(world)
    head(h)
    with h['database'].session() as db:
        if changed == 'pre_inbox_schema':
            for table in ('weixin_peer_generations', 'weixin_peer_scope_grants', 'weixin_dispatch_receipts',
                    'weixin_inbox_descriptors', 'weixin_poll_receipts', 'weixin_peer_bindings', 'weixin_accounts'):
                db.execute(text('DROP TABLE '+table))
        else:
            db.execute(text('DROP TABLE weixin_peer_generations' if changed == 'previous_schema'
                else 'CREATE TABLE future_schema(id TEXT)'))
        before = [tuple(row) for row in db.execute(text(
            'SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name'))]
    with pytest.raises(ServiceError) as rejected:
        head(h)
    assert (rejected.value.code, rejected.value.status_code) == ('VERSION_CONFLICT', 409)
    with h['database'].session() as db:
        assert [tuple(row) for row in db.execute(text(
            'SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name'))] == before


def test_head_survives_reopened_database_and_success_does_not_write_any_rows(world):
    h = setup_history(world)
    head(h)
    first = append(h)
    second = append(h, request(h, first))
    before = state(h['database'])
    with h['database'].session() as db:
        audits = [tuple(row) for row in db.execute(text('SELECT * FROM audit_events ORDER BY rowid'))]
    database = Database('sqlite:///'+str(h['root']/'workbench.db'), h['root']/'protected',
        h['database'].settings, initialize_schema=False)
    backup._mark_storage_flags(database)
    try:
        assert_head(head(h, database=database), generation=2, digest=second.generation_sha256,
            scope=h['targets'][1][0].scope, scope_digest=second.scope_sha256, checkpoint=2)
    finally:
        database.engine.dispose()
    assert state(h['database']) == before
    with h['database'].session() as db:
        assert [tuple(row) for row in db.execute(text('SELECT * FROM audit_events ORDER BY rowid'))] == audits
