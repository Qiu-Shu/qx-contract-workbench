"""The library disk guard must still bite, under simulated capacity.

These tests drive the real `cn_contract.library.budget.check_budget()` — only the
host free-space probe is simulated — so the production thresholds (40 GiB plus
pending asset bytes, 8 GiB process, 200 GiB derived) and the real import / index
entry points are exercised. They are the counterpart to `library_capacity`: the
rest of the library suite runs with a *simulated* comfortable disk, and this file
proves that "comfortable" was a test condition, not a disabled guard.
"""
import csv
import json
import subprocess

import pytest

from cn_contract.library import budget

GIB = 1024 ** 3
BASE = 40 * GIB

pytestmark = pytest.mark.usefixtures('library_capacity')


def usage(free):
    return type('Usage', (), {'total': free, 'used': 0, 'free': free})()


@pytest.fixture
def probe(monkeypatch):
    """Record how often the guard actually measured, and with what answer.

    `keep_cache=True` leaves `budget._last` alone, so the 5-second reuse window
    armed by an earlier successful check is still in force when the capacity
    answer changes. The two cache-boundary tests need exactly that: switching the
    answer *and* wiping the cache would test nothing about the window.
    """
    seen = []

    def install(free, *, keep_cache=False):
        def disk_usage(_path):
            seen.append(free)
            return usage(free)
        monkeypatch.setattr(budget, 'shutil', type('Shutil', (), {'disk_usage': staticmethod(disk_usage)}))
        if not keep_cache:
            budget._last.clear()
        return free
    return install, seen


def test_enough_capacity_passes_with_pending_assets(tmp_path, probe):
    install, seen = probe
    install(BASE + 1000)
    budget.check_budget(tmp_path, additional_bytes=1000, force=True)
    assert seen, 'guard never measured the disk'


@pytest.mark.parametrize('free, expected', [(BASE - 1, False), (BASE, True)])
def test_base_threshold_is_40_gib_and_strictly_less(tmp_path, probe, free, expected):
    install, _ = probe
    install(free)
    if expected:
        budget.check_budget(tmp_path, force=True)
    else:
        with pytest.raises(ValueError, match='LIBRARY_DISK_BUDGET'):
            budget.check_budget(tmp_path, force=True)


@pytest.mark.parametrize('free, expected', [(BASE + 499, False), (BASE + 500, True)])
def test_pending_asset_bytes_are_added_to_the_threshold(tmp_path, probe, free, expected):
    install, _ = probe
    install(free)
    if expected:
        budget.check_budget(tmp_path, additional_bytes=500, force=True)
    else:
        with pytest.raises(ValueError, match='LIBRARY_DISK_BUDGET'):
            budget.check_budget(tmp_path, additional_bytes=500, force=True)


def test_forced_check_is_not_served_from_the_reuse_window(tmp_path, probe):
    install, seen = probe
    install(BASE + 10)
    budget.check_budget(tmp_path, force=True)
    assert str(tmp_path) in budget._last, 'no positive verdict was cached, so the window was never armed'
    first = len(seen)
    # Keep the cache: the answer changes while the 5-second window is still valid.
    install(BASE - 1, keep_cache=True)
    assert str(tmp_path) in budget._last, 'the positive verdict vanished before the switch'
    with pytest.raises(ValueError, match='LIBRARY_DISK_BUDGET'):
        budget.check_budget(tmp_path, force=True)
    assert len(seen) > first, 'forced check reused the cached verdict instead of measuring'


def test_pending_assets_bypass_the_reuse_window_without_force(tmp_path, probe):
    install, seen = probe
    install(BASE + 10)
    budget.check_budget(tmp_path, force=True)
    assert str(tmp_path) in budget._last, 'no positive verdict was cached, so the window was never armed'
    first = len(seen)
    install(BASE + 10, keep_cache=True)  # cache still armed; only the bytes to copy are new
    assert str(tmp_path) in budget._last, 'the positive verdict vanished before the switch'
    with pytest.raises(ValueError, match='LIBRARY_DISK_BUDGET'):
        budget.check_budget(tmp_path, additional_bytes=11)  # force=False on purpose
    assert len(seen) > first, 'a pending asset copy must not be waved through by the cache'


def test_plain_repeat_check_inside_the_window_may_be_reused(tmp_path, probe):
    """The opposite edge: force=False with no new bytes is allowed to skip."""
    install, seen = probe
    install(BASE + 10)
    budget.check_budget(tmp_path, force=True)
    first = len(seen)
    budget.check_budget(tmp_path)
    assert len(seen) == first, 'the documented reuse window no longer applies'


def test_cli_child_rejects_when_declared_capacity_is_short(tmp_path):
    """A child process must still be refused: the launcher swaps the probe only."""
    from tests.helpers.library_cli import child_command, child_env
    source = write_cases(tmp_path / 'cases.csv', rows=3)
    root = tmp_path / 'library'
    command = child_command('import-cases', '--library-root', str(root), '--input', str(source),
                           '--batch-id', 'fiction', '--batch-size', '2')
    result = subprocess.run(command, capture_output=True, text=True, timeout=180,
                            env=child_env(free_bytes=BASE - 1))
    assert result.returncode == 1, (result.returncode, result.stdout, result.stderr)
    assert 'LIBRARY_DISK_BUDGET' in result.stderr, result.stderr
    assert not (root / 'library.json').exists(), 'a refused child still published a library marker'


def test_cli_child_imports_when_declared_capacity_is_sufficient(tmp_path):
    """Same child path, sufficient declared capacity: it really runs to success."""
    from tests.helpers.library_cli import child_command, child_env
    source = write_cases(tmp_path / 'cases.csv', rows=3)
    root = tmp_path / 'library'
    command = child_command('import-cases', '--library-root', str(root), '--input', str(source),
                           '--batch-id', 'fiction', '--batch-size', '2')
    result = subprocess.run(command, capture_output=True, text=True, timeout=180,
                            env=child_env(free_bytes=BASE + 64 * 1024 * 1024))
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report['stored'] == 3 and report['complete']


def test_memory_budget_still_rejects(tmp_path, monkeypatch, probe):
    install, _ = probe
    install(BASE + 10)
    monkeypatch.setattr(budget, 'process_bytes', lambda: 9 * GIB)
    with pytest.raises(ValueError, match='LIBRARY_MEMORY_BUDGET'):
        budget.check_budget(tmp_path, force=True)


def write_cases(path, rows=3):
    with path.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(['标题', '案号', '法院', '省', '判决时间', '文书内容', '文书类型', '案由'])
        for i in range(1, rows + 1):
            writer.writerow(['虚构案' + str(i), '（２０２５）吉虚' + str(i) + '号', '虚构法院',
                             '吉林省', '2025-01-02', '这是虚构资料，关于租赁的第' + str(i) + '段。',
                             '判决书', '租赁合同纠纷'])
    return path


def test_import_refuses_to_publish_when_capacity_is_short(tmp_path, probe):
    from cn_contract.library import csv_source
    install, _ = probe
    incoming = write_cases(tmp_path / 'cases.csv')
    original = incoming.read_bytes()
    root = tmp_path / 'library'
    install(BASE - 1)
    with pytest.raises(ValueError, match='LIBRARY_DISK_BUDGET'):
        csv_source.import_case_file(root, incoming, 'fiction')
    # Nothing was registered, no asset was copied, the source file is untouched.
    assert not (root / 'library.json').exists()
    assert not list(root.glob('assets/*')) if (root / 'assets').exists() else True
    assert incoming.read_bytes() == original


def test_index_refuses_and_keeps_the_old_generation(tmp_path, probe):
    from cn_contract.library import csv_source, index
    install, _ = probe
    incoming = write_cases(tmp_path / 'cases.csv')
    root = tmp_path / 'library'
    # Import copies the source as an asset, and that copy is checked against
    # `40 GiB + file size`, so "just above the base line" is not enough room to
    # set the stage. Give the setup real headroom, then cut the disk below the
    # base line to test the index refusal.
    install(BASE + 64 * 1024 * 1024)
    csv_source.import_case_file(root, incoming, 'fiction')
    first = index.build_generation(root)
    index.activate_generation(root, first)
    current = (root / 'current.json').read_bytes()
    install(BASE - 1)
    with pytest.raises(ValueError, match='LIBRARY_DISK_BUDGET'):
        index.build_generation(root)
    assert (root / 'current.json').read_bytes() == current
    assert index.current_generation(root)['generation_id'] == first
    # The old generation is still usable for the path the pilot actually needs.
    from cn_contract.library import service
    from cn_contract.domain import LibraryQuery
    assert service.search(root, LibraryQuery(text='租赁', kind='case_csv')).hits
