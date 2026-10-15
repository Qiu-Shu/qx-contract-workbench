"""Ranking sharing must remain bounded and retain timeout/error distinctions."""
from concurrent.futures import Future, ThreadPoolExecutor
from threading import Event
import sqlite3
import time

import pytest

from cn_contract.library import service


class RankingDatabase:
    def __init__(self, action=None):
        self.calls = 0
        self.action = action

    def execute(self, sql, args):
        self.calls += 1
        if self.action:
            return self.action()
        return [(args[0],)]


def test_owner_deadline_interrupt_is_shared_as_timeout(tmp_path, monkeypatch):
    path = tmp_path / 'synthetic-index'
    path.write_bytes(b'fiction')
    entered, release, waiting = Event(), Event(), Event()
    class ObservedFuture(Future):
        def result(self, timeout=None):
            waiting.set()
            return super().result(timeout)
    monkeypatch.setattr(service, 'Future', ObservedFuture)
    def interrupted():
        entered.set()
        assert release.wait(2)
        raise sqlite3.OperationalError('interrupted')
    db = RankingDatabase(interrupted)
    with ThreadPoolExecutor(max_workers=2) as pool:
        owner = pool.submit(service._candidate_rows, db, path, 'ranking', ('fiction',), time.monotonic() - 1)
        assert entered.wait(1)
        waiter = pool.submit(service._candidate_rows, db, path, 'ranking', ('fiction',), time.monotonic() + 2)
        assert waiting.wait(1)
        release.set()
        for result in (owner, waiter):
            with pytest.raises(TimeoutError):
                result.result()
    # A failed computation cannot poison the next request.
    db.action = None
    assert service._candidate_rows(db, path, 'ranking', ('fiction',), time.monotonic() + 2) == (('fiction',),)
    assert db.calls == 2


def test_database_fault_is_not_relabelled_timeout(tmp_path):
    path = tmp_path / 'synthetic-index'
    path.write_bytes(b'fiction')
    def broken():
        raise sqlite3.OperationalError('malformed synthetic database')
    with pytest.raises(sqlite3.OperationalError, match='malformed'):
        service._candidate_rows(RankingDatabase(broken), path, 'ranking', (), time.monotonic() + 2)


def test_concurrent_identical_rankings_compute_once(tmp_path):
    path = tmp_path / 'synthetic-index'
    path.write_bytes(b'fiction')
    entered, release = Event(), Event()
    def slow():
        entered.set()
        assert release.wait(2)
        return [('fiction',)]
    db = RankingDatabase(slow)
    def fetch():
        return service._candidate_rows(db, path, 'ranking', ('same',), time.monotonic() + 2)
    with ThreadPoolExecutor(max_workers=3) as pool:
        first = pool.submit(fetch)
        assert entered.wait(1)
        followers = [pool.submit(fetch) for _ in range(2)]
        release.set()
        assert first.result() == (('fiction',),)
        assert all(future.result() == first.result() for future in followers)
    assert db.calls == 1


def test_rank_cache_evicts_and_invalidates_changed_index(tmp_path, monkeypatch):
    path = tmp_path / 'synthetic-index'
    path.write_bytes(b'fiction')
    monkeypatch.setattr(service, '_RANK_CACHE_BYTES', 500)
    db = RankingDatabase()
    def fetch(word):
        return service._candidate_rows(db, path, 'ranking', (word,), time.monotonic() + 2)
    fetch('a' * 200)
    fetch('b' * 200)
    fetch('a' * 200)
    assert db.calls == 3
    fetch('a' * 200)
    assert db.calls == 3
    path.write_bytes(b'new fiction index')
    fetch('a' * 200)
    assert db.calls == 4
