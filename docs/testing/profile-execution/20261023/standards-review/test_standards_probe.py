"""Independent transaction probes; all workspaces and replies are synthetic."""
import asyncio
from functools import wraps
from hashlib import sha256
import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from cn_contract import domain as d
from cn_contract.assistant import profile_store
from cn_contract.assistant.providers import attempts, profile_codec
from cn_contract.security import ServiceError, deny
from tests.integration.test_assistant_generation import world
from tests.integration.test_assistant_profile_execution import (
    profile_world, authorize, enqueue, unsent_provider, no_archive, archive_response)
from tests.integration.test_assistant_storage import add_matter
from tests.integration.test_assistant_main_provider import KEY
from tests.unit.test_assistant_profile_codec import candidate as wire_candidate, response


def looped(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        async def run():
            return function(*args, **kwargs)
        return asyncio.run(run())
    return wrapped


def ready(world):
    database, actor, _, _ = world
    _, runtime, _, _ = authorize(world, unsent_provider(), project_intake=True)
    first = enqueue(world, runtime, project_intake=True)
    with database.session() as db:
        token, prepared, config = attempts.claim(actor, first.id, db, runtime)
    reply = profile_codec.decode_response(archive_response(), prepared.request, config, KEY)
    assert reply.output is not None
    return runtime, first, token, reply


@pytest.mark.parametrize('failure', ['exception', 'deny'])
@looped
def test_failure_after_real_profile_write_rolls_back_business_but_retains_fee_and_audit(profile_world, monkeypatch, failure):
    database, actor, _, _ = profile_world
    matter = add_matter(database, actor)
    runtime, first, token, reply = ready(profile_world)
    original = profile_store._commit
    with database.session() as db:
        audits = db.scalar(text('SELECT count(*) FROM audit_events'))
    def fail_after_write(caller, request, sources, db):
        original(caller, request, sources, db)
        assert db.scalar(text('SELECT count(*) FROM assistant_profile_receipts')) == 1
        if failure == 'deny':
            deny(caller, matter, 'authorization_denied', db)
        raise ServiceError('VERSION_CONFLICT', 409)
    monkeypatch.setattr(profile_store, '_commit', fail_after_write)
    with database.session() as db:
        attempts.settle(actor, first.id, token, reply, db, runtime)
    with database.session() as db:
        result = attempts.read_attempt(actor, first.id, db)
        assert result.output is not None and result.receipt.usage.total_tokens == 42
        handler = db.execute(text('SELECT * FROM assistant_profile_handlers')).mappings().one()
        assert handler['outcome'] == 'blocked' and handler['profile_receipt_sequence'] is None
        assert db.scalar(text('SELECT count(*) FROM assistant_profile_receipts')) == 0
        assert db.scalar(text('SELECT count(*) FROM assistant_profile_revisions')) == 0
        assert db.scalar(text('SELECT count(*) FROM intake_cases')) == 0
        assert db.scalar(text('SELECT count(*) FROM audit_events')) == audits + (failure == 'deny')


@pytest.mark.parametrize('failure', ['receipt', 'output', 'handler', 'ready', 'saved', 'finished'])
@looped
def test_caller_catches_ledger_error_then_commits_without_half_profile(profile_world, failure):
    database, actor, _, _ = profile_world
    runtime, first, token, reply = ready(profile_world)
    tables = {'receipt': 'assistant_model_receipts', 'output': 'assistant_model_outputs',
              'handler': 'assistant_profile_handlers'}
    events = {'ready': 'response.ready', 'saved': 'profile.saved', 'finished': 'model.finished'}
    table = tables.get(failure, 'assistant_run_events')
    condition = " WHEN NEW.event_type='" + events[failure] + "'" if failure in events else ''
    with database.session() as db:
        db.execute(text('CREATE TRIGGER reject_probe BEFORE INSERT ON ' + table + condition +
                        " BEGIN SELECT RAISE(ABORT,'synthetic late ledger failure'); END"))
    with database.session() as db:
        with pytest.raises(IntegrityError):
            attempts.settle(actor, first.id, token, reply, db, runtime)
        # This is a catch-and-commit caller, not Database.session's exception rollback.
        db.execute(text("UPDATE assistant_conversations SET draft_input='保留合成后续草稿'"))
    no_archive(database)
    with database.session() as db:
        assert db.scalar(text('SELECT count(*) FROM intake_cases')) == 0
        assert db.scalar(text('SELECT count(*) FROM assistant_model_outputs')) == 0
        assert db.scalar(text('SELECT count(*) FROM assistant_model_receipts')) == 0
        assert db.scalar(text("SELECT count(*) FROM assistant_run_events WHERE event_type IN ('response.ready','profile.saved','profile.unchanged','profile.blocked','model.finished')")) == 0
        assert attempts.read_attempt(actor, first.id, db).state == 'sending'
        assert db.scalar(text('SELECT draft_input FROM assistant_conversations')) == '保留合成后续草稿'


@pytest.mark.parametrize('failure', ['quote', 'scope'])
@looped
def test_candidate_boundary_rejects_bypassed_dto_without_losing_usage(profile_world, failure):
    database, actor, _, _ = profile_world
    runtime, first, token, reply = ready(profile_world)
    patch = reply.output.profile_patch
    if failure == 'scope':
        patch = patch.model_copy(update={'base_profile_revision': 9})
    else:
        proposal = patch.changes[0]
        original = proposal.source_refs[0]
        quote = '乙' + original.quote[1:]
        ref = original.model_copy(update={'quote':quote, 'quote_sha256':sha256(quote.encode()).hexdigest()})
        proposal = proposal.model_copy(update={'source_refs':(ref,)})
        patch = patch.model_copy(update={'changes':(proposal,)})
    reply = reply.model_copy(update={'output':reply.output.model_copy(update={'profile_patch':patch})})
    with database.session() as db:
        attempts.settle(actor, first.id, token, reply, db, runtime)
    no_archive(database)
    with database.session() as db:
        result = attempts.read_attempt(actor, first.id, db)
        assert result.output is None and result.receipt.usage.total_tokens == 42
        assert result.receipt.error_code == 'MODEL_OUTPUT_INVALID'


@pytest.mark.parametrize('count,adopted', [(20,True), (21,True), (22,False), (60,False)])
@looped
def test_expanded_profile_is_either_readable_or_rejected_without_business_writes(profile_world, count, adopted):
    from cn_contract.assistant.model_integrity import validate_model_records
    database, actor, _, _ = profile_world
    runtime, first, token, _ = ready(profile_world)
    with database.session() as db:
        row = attempts._row(first.id, db)
        prepared = attempts._input(row)
        config = attempts._model(d.MainModelConfig, row['config_json'])
    candidate = wire_candidate()
    proposal = candidate['profile_changes'][0]
    proposal['quotes'] *= 40
    candidate['profile_changes'] *= count
    raw = response(prepared.request, candidate)
    assert len(raw) < config.max_response_bytes
    reply = profile_codec.decode_response(raw, prepared.request, config, KEY)
    assert reply.output is not None
    with database.session() as db:
        attempts.settle(actor, first.id, token, reply, db, runtime)
    with database.session() as db:
        result = attempts.read_attempt(actor, first.id, db)
        assert (result.output is not None) is adopted
        assert result.receipt.usage.total_tokens == 42
        if adopted:
            assert len(result.output.model_dump_json().encode()) <= 262144
        else:
            assert result.receipt.error_code == 'MODEL_OUTPUT_INVALID'
            assert db.scalar(text('SELECT count(*) FROM assistant_profile_handlers')) == 0
            assert db.scalar(text('SELECT count(*) FROM assistant_profile_receipts')) == 0
        validate_model_records(db)
