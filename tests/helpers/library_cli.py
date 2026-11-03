"""Launch the library CLI in a child process under a *declared* capacity.

Why this exists
---------------
`tests/conftest.py::library_capacity` isolates the host free-space probe for the
test process. A child process does not inherit `monkeypatch`, so a test that
spawns `python -m cn_contract.library ...` would otherwise measure whatever free
space the machine happens to have, and fail for a reason unrelated to what it
asserts (batch durability across a kill).

This launcher applies the same narrow substitution inside the child: it replaces
the *module-level* `budget.shutil` binding only, and only when
`CN_TEST_LIBRARY_FREE_BYTES` is set. Nothing in `src/` is modified, no threshold
is lowered, and `check_budget()` still runs its real comparison — the child is
still refused when the declared capacity is below 40 GiB + pending bytes (see
`test_cli_child_rejects_when_declared_capacity_is_short`, and the `no override`
case which falls back to the real host probe).

"Declared capacity" is a test condition. It is never reported as real host
capacity; the host is measured separately and reported separately.
"""
import os
from pathlib import Path
import runpy
import sys
from types import SimpleNamespace

GIB = 1024 ** 3
DEFAULT_DECLARED_BYTES = 200 * GIB
SRC = Path(__file__).resolve().parents[2] / 'src'


def declared_free_bytes():
    raw = os.environ.get('CN_TEST_LIBRARY_FREE_BYTES')
    return int(raw) if raw else None


def apply_declared_capacity(free):
    from cn_contract.library import budget
    budget.shutil = SimpleNamespace(
        disk_usage=lambda path: SimpleNamespace(total=free, used=0, free=free))
    budget._last.clear()


def child_command(*args):
    """argv that runs this launcher as a script, so no import-time side effects."""
    return [sys.executable, '-X', 'utf8', str(Path(__file__).resolve()), *args]


def child_env(free_bytes=DEFAULT_DECLARED_BYTES, **extra):
    env = dict(os.environ)
    env.setdefault('PYTHONPATH', os.environ.get('PYTHONPATH') or str(SRC))
    if free_bytes is not None:
        env['CN_TEST_LIBRARY_FREE_BYTES'] = str(free_bytes)
    env.update({key: str(value) for key, value in extra.items()})
    return env


def main(argv):
    free = declared_free_bytes()
    if free is not None:
        apply_declared_capacity(free)
    sys.argv = ['cn_contract.library'] + list(argv)
    runpy.run_module('cn_contract.library', run_name='__main__', alter_sys=True)


if __name__ == '__main__':
    main(sys.argv[1:])
