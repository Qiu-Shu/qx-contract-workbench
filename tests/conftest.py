"""Shared test fixtures.

`library_capacity` exists for one narrow reason: the library import/index
fixtures build real (tiny, fictional) corpora through the production entry
points, and those entry points call `cn_contract.library.budget.check_budget()`,
which compares the *host* free space against 40 GiB. On a machine that happens
to sit below that line, dozens of tests about offsets, dedup or ranking fail for
a reason that has nothing to do with what they assert.

Scope is deliberately the whole suite (autouse): the production guard is invoked
from deep inside shared fixtures, so a per-module opt-in would leave most
affected tests still measuring the host. What the fixture replaces is *only* the
host measurement (`budget.shutil.disk_usage`); it is restored on teardown, and
`budget._last` is cleared on both ends so no test inherits another test's
verdict.

The production guard itself is untouched: `check_budget()` still runs, still
compares against `40 GiB + additional_bytes`, still raises `LIBRARY_DISK_BUDGET`,
`LIBRARY_MEMORY_BUDGET` and `LIBRARY_DERIVED_BUDGET` exactly as shipped. The
guard's own boundaries are covered against simulated low capacity in
`tests/unit/test_library_budget_guard.py`, which re-requests this fixture and
drives the real function. "Capacity is simulated here" must never be reported as
"the host really has enough room" — set ``state['free'] = None`` to fall back to
the real probe and observe the actual host.

Child processes do not inherit ``monkeypatch``. Tests that spawn an interpreter
through ``tests/helpers/library_cli.py`` declare the capacity that child measures
via ``CN_TEST_LIBRARY_FREE_BYTES``; the launcher swaps the same single binding and
nothing else, and the child is still refused when the declared capacity is short
(``test_cli_child_rejects_when_declared_capacity_is_short``). A child started
without that declaration — or any other subprocess — still measures the real host,
and the fixture says nothing about it.
"""
from types import SimpleNamespace

import pytest

GIB = 1024 ** 3
_real_disk_usage = None


@pytest.fixture(autouse=True)
def library_capacity(monkeypatch):
    """Replace the host free-space probe with an explicit simulated value.

    Yields a mutable state dict: set ``state['free'] = <bytes>`` to simulate a
    different capacity (``None`` restores the real probe for that test), and
    read ``state['calls']`` to prove the probe really ran — i.e. that the guard
    was not skipped because of the reuse window.
    """
    global _real_disk_usage
    from cn_contract.library import budget

    if _real_disk_usage is None:
        _real_disk_usage = budget.shutil.disk_usage

    state = {'free': 200 * GIB, 'calls': 0}

    def disk_usage(path):
        state['calls'] += 1
        if state['free'] is None:
            return _real_disk_usage(path)
        return SimpleNamespace(total=state['free'], used=0, free=state['free'])

    monkeypatch.setattr(budget, 'shutil', SimpleNamespace(disk_usage=disk_usage))
    budget._last.clear()
    try:
        yield state
    finally:
        budget._last.clear()
