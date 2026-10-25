"""Development-only observation must preserve the actual restore operations."""
import importlib
import importlib.util
import gc
import json
import os
import time
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from cn_contract.ops import workspace_backup
from cn_contract.web import workspace_upgrade


STEPS = (
    (workspace_backup, '_unpack', 1),
    (workspace_backup, '_references', 0),
    (workspace_backup, '_validate_database', 0),
    (workspace_backup, '_fence', 0),
    (workspace_upgrade, 'upgrade', 0),
)


def api():
    name = 'scripts.restore_publish_diagnostics'
    assert importlib.util.find_spec(name) is not None, 'restore publication observation module is required'
    return importlib.import_module(name)


def stage_root(tmp_path, *, parent_name='restores', stage_name='.qx-restore-test'):
    parent = tmp_path/parent_name
    root = parent/stage_name/'workspace'
    root.mkdir(parents=True)
    (root/'workbench.db').write_bytes(b'independent fictional bytes; no live database')
    return parent, root


def patched_functions():
    return [os.rename, *(getattr(module, name) for module, name, _ in STEPS)]


class PrivateError(OSError):
    str_calls = 0

    def __str__(self):
        type(self).str_calls += 1
        return 'PRIVATE-FICTIONAL-CONTRACT-TEXT'


def test_observer_records_one_actual_publication_without_changing_the_operation(tmp_path):
    observer = api()
    parent, root = stage_root(tmp_path)
    destination = parent/'published'
    originals = patched_functions()
    events = []
    handles = [{'path':'workbench.db', 'kind':'synthetic-observed-file'}]
    with observer.observe_restore(parent, events, scan=lambda _:handles):
        assert root.is_dir() and not destination.exists() and events == []
        returned = os.rename(root, destination)
    assert returned is None and patched_functions() == originals
    assert not root.exists() and (destination/'workbench.db').read_bytes() == b'independent fictional bytes; no live database'
    assert [event['phase'] for event in events] == ['publish:before', 'publish:success']
    assert all(event['handles'] == handles and event['scan_status'] == 'OK'
               and event['cwd_inside_stage'] is False for event in events)


def test_default_scanner_is_called_for_the_scoped_stage_only(tmp_path, monkeypatch):
    observer = api()
    parent, root = stage_root(tmp_path)
    calls = []

    def scan(stage):
        calls.append(Path(stage))
        return [{'path':'workbench.db', 'kind':'synthetic-default-scanner'}]

    monkeypatch.setattr(observer, 'own_process_handles', scan)
    events = []
    with observer.observe_restore(parent, events):
        os.rename(root, parent/'published')
    assert len(calls) == 2
    assert all(os.path.normcase(str(value)) == os.path.normcase(str(root)) for value in calls)
    assert all(event['handles'] == [{'path':'workbench.db', 'kind':'synthetic-default-scanner'}]
               and event['scan_status'] == 'OK' for event in events)


@pytest.mark.skipif(os.name != 'nt', reason='native own-process file handles require Windows')
def test_native_default_scanner_observes_only_the_open_relative_stage_file(tmp_path, monkeypatch):
    observer = api()
    parent, root = stage_root(tmp_path)
    returned = object()
    monkeypatch.setattr(workspace_backup, '_validate_database', lambda _:returned)
    events = []
    with observer.observe_restore(parent, events):
        with (root/'workbench.db').open('rb'):
            assert workspace_backup._validate_database(root) is returned
        assert workspace_backup._validate_database(root) is returned
    assert [event['phase'] for event in events] == ['_validate_database:enter', '_validate_database:exit']*2
    assert all(event['scan_status'] == 'OK' for event in events)
    assert all(any(handle['path'] == 'workbench.db' for handle in event['handles'])
               for event in events[:2])
    assert all(not any(handle['path'] == 'workbench.db' for handle in event['handles'])
               for event in events[2:])
    assert all(not Path(handle['path']).is_absolute()
               for event in events for handle in event['handles'])


@pytest.mark.parametrize('module,name,position', [
    pytest.param(module, name, position, id=name) for module, name, position in STEPS
])
@pytest.mark.parametrize('raises', [False, True], ids=['returned', 'raised'])
def test_substep_observation_preserves_arguments_return_and_exception_identity(tmp_path, monkeypatch, module, name, position, raises):
    observer = api()
    parent, root = stage_root(tmp_path)
    arguments = (tmp_path/'archive.zip', root) if position else (root,)
    keywords = {'fictional_forwarded_option':object()}
    returned = object()
    calls = []
    failure = PrivateError(13, 'PRIVATE-FICTIONAL-CONTRACT-TEXT')
    failure.winerror = 5
    PrivateError.str_calls = 0

    def operation(*args, **kwargs):
        calls.append((args, kwargs))
        if raises:
            raise failure
        return returned

    monkeypatch.setattr(module, name, operation)
    originals = patched_functions()
    events = []
    with observer.observe_restore(parent, events, scan=lambda _:[]):
        if raises:
            with pytest.raises(PrivateError) as caught:
                getattr(module, name)(*arguments, **keywords)
            assert caught.value is failure
        else:
            assert getattr(module, name)(*arguments, **keywords) is returned
    assert patched_functions() == originals
    assert calls == [(arguments, keywords)]
    assert [event['phase'] for event in events] == [name+':enter', name+(':error' if raises else ':exit')]
    assert all(event['scan_status'] == 'OK' and event['handles'] == [] for event in events)
    if raises:
        assert events[-1]['exception_type'] == 'PrivateError'
        assert events[-1]['errno'] == 13 and events[-1]['winerror'] == 5
        assert PrivateError.str_calls == 0
        assert 'PRIVATE-FICTIONAL-CONTRACT-TEXT' not in json.dumps(events)


@pytest.mark.parametrize('operation_fails', [False, True], ids=['publish-returned', 'publish-raised'])
def test_scan_failure_is_diagnostic_only_and_never_masks_the_original_operation(tmp_path, monkeypatch, operation_fails):
    observer = api()
    parent, root = stage_root(tmp_path)
    destination = parent/'published'
    original_rename = os.rename
    failure = PrivateError(13, 'PRIVATE-FICTIONAL-CONTRACT-TEXT')
    failure.winerror = 5
    PrivateError.str_calls = 0
    calls = []
    scans = []

    def scan(stage):
        scans.append(stage)
        raise RuntimeError('PRIVATE-FICTIONAL-SCAN-TEXT')

    def rename(*args, **kwargs):
        calls.append((args, kwargs))
        if operation_fails:
            raise failure
        return original_rename(*args, **kwargs)

    def forbidden(*args, **kwargs):
        raise AssertionError('observation must not retry, sleep, or collect garbage')

    with monkeypatch.context() as patch:
        patch.setattr(os, 'rename', rename)
        patch.setattr(gc, 'collect', forbidden)
        patch.setattr(time, 'sleep', forbidden)
        events = []
        with observer.observe_restore(parent, events, scan=scan):
            if operation_fails:
                with pytest.raises(PrivateError) as caught:
                    os.rename(root, destination)
                assert caught.value is failure
            else:
                assert os.rename(root, destination) is None
        assert os.rename is rename
    assert len(calls) == 1 and len(scans) == 2
    assert [event['phase'] for event in events] == ['publish:before', 'publish:failure' if operation_fails else 'publish:success']
    assert all(event['scan_status'] == 'ERROR' and event['handles'] == []
               and event['scan_exception_type'] == 'RuntimeError' for event in events)
    assert PrivateError.str_calls == 0
    assert 'PRIVATE-FICTIONAL-' not in json.dumps(events)
    assert root.exists() is operation_fails and destination.exists() is not operation_fails
    assert os.rename is original_rename


def test_calls_outside_the_exact_restore_stage_and_parent_produce_no_events(tmp_path, monkeypatch):
    observer = api()
    parent, root = stage_root(tmp_path)
    calls = []

    def operation(*args, **kwargs):
        calls.append(args)
        return 'original behavior'

    def no_scan(stage):
        raise AssertionError('out-of-scope operation must not be scanned')

    for module, name, _ in STEPS:
        monkeypatch.setattr(module, name, operation)
    monkeypatch.setattr(os, 'rename', operation)
    candidates = [
        tmp_path/'restores-sibling'/'.qx-restore-other'/'workspace',
        parent/'ordinary'/'workspace',
        parent/'.qx-backup-test'/'workspace',
        parent/'.qx-restore-test'/'workspace-other',
        root/'child',
    ]
    events = []
    with observer.observe_restore(parent, events, scan=no_scan):
        for candidate in candidates:
            for module, name, position in STEPS:
                args = (tmp_path/'archive.zip', candidate) if position else (candidate,)
                assert getattr(module, name)(*args) == 'original behavior'
            assert os.rename(candidate, parent/'outside-publish') == 'original behavior'
        assert os.rename(root, tmp_path/'another-parent'/'published') == 'original behavior'
    assert events == [] and len(calls) == len(candidates)*6+1


def test_parent_and_stage_need_not_exist_when_observation_begins(tmp_path, monkeypatch):
    observer = api()
    parent = tmp_path/'future-restores'
    root = parent/'.qx-restore-future'/'workspace'
    scans = []

    def unpack(plain, target):
        assert not parent.exists()
        target.mkdir(parents=True)
        (target/'independent-fiction.txt').write_text('synthetic', encoding='utf-8')
        return 'unpacked'

    monkeypatch.setattr(workspace_backup, '_unpack', unpack)
    events = []
    with observer.observe_restore(parent, events, scan=lambda stage:scans.append(stage) or []):
        assert not parent.exists() and events == []
        assert workspace_backup._unpack(tmp_path/'archive.zip', root) == 'unpacked'
    assert [event['phase'] for event in events] == ['_unpack:enter', '_unpack:exit']
    assert len(scans) == 2 and (root/'independent-fiction.txt').read_text(encoding='utf-8') == 'synthetic'


@pytest.mark.parametrize('alias', ['case', 'extended'])
def test_windows_path_aliases_match_the_same_scope_without_changing_forwarded_arguments(tmp_path, monkeypatch, alias):
    observer = api()
    parent, root = stage_root(tmp_path)
    candidate = Path(str(root).swapcase()) if alias == 'case' else Path('\\\\?\\'+str(root))
    passed = []

    def operation(target):
        passed.append(target)
        return 'kept original path'

    monkeypatch.setattr(workspace_backup, '_validate_database', operation)
    events = []
    with observer.observe_restore(parent, events, scan=lambda _:[]):
        assert workspace_backup._validate_database(candidate) == 'kept original path'
    assert passed == [candidate]
    assert [event['phase'] for event in events] == (['_validate_database:enter', '_validate_database:exit'] if os.name == 'nt' else [])


def test_snapshot_reports_cwd_containment_without_changing_it(tmp_path, monkeypatch):
    observer = api()
    parent, root = stage_root(tmp_path)
    monkeypatch.setattr(workspace_backup, '_validate_database', lambda _:None)
    monkeypatch.chdir(root)
    events = []
    before = Path.cwd()
    with observer.observe_restore(parent, events, scan=lambda _:[]):
        workspace_backup._validate_database(root)
    assert Path.cwd() == before
    assert [event['cwd_inside_stage'] for event in events] == [True, True]


def test_nested_observer_is_rejected_without_disabling_the_active_observer(tmp_path):
    observer = api()
    parent, root = stage_root(tmp_path)
    originals = patched_functions()
    events = []
    with observer.observe_restore(parent, events, scan=lambda _:[]):
        for _ in range(2):
            with pytest.raises(RuntimeError):
                with observer.observe_restore(tmp_path/'different-parent', [], scan=lambda _:[]):
                    raise AssertionError('same-process nested observer must not enter')
        assert os.rename(root, parent/'published') is None
    assert [event['phase'] for event in events] == ['publish:before', 'publish:success']
    assert patched_functions() == originals
    with observer.observe_restore(parent, [], scan=lambda _:[]):
        pass


def test_observer_restores_every_patch_when_the_context_body_raises(tmp_path):
    observer = api()
    parent, _ = stage_root(tmp_path)
    originals = patched_functions()
    failure = RuntimeError('independent synthetic caller failure')
    with pytest.raises(RuntimeError) as caught:
        with observer.observe_restore(parent, [], scan=lambda _:[]):
            raise failure
    assert caught.value is failure and patched_functions() == originals
    with observer.observe_restore(parent, [], scan=lambda _:[]):
        pass


def test_cleanup_failure_after_actual_publish_preserves_success_event_and_original_error(tmp_path, monkeypatch):
    observer = api()
    parent = tmp_path/'restores'
    parent.mkdir()
    temporary = TemporaryDirectory(prefix='.qx-restore-', dir=parent)
    root = Path(temporary.name)/'workspace'
    root.mkdir()
    (root/'independent-fiction.txt').write_text('synthetic retained publication', encoding='utf-8')
    destination = parent/'published'
    cleanup = temporary.cleanup
    failure = OSError(13, 'independent synthetic temporary cleanup failure')
    originals = patched_functions()

    def fail_cleanup():
        raise failure

    monkeypatch.setattr(temporary, 'cleanup', fail_cleanup)
    events = []
    try:
        with pytest.raises(OSError) as caught:
            with observer.observe_restore(parent, events, scan=lambda _:[]):
                with temporary:
                    os.rename(root, destination)
        assert caught.value is failure
    finally:
        cleanup()
    assert [event['phase'] for event in events] == ['publish:before', 'publish:success']
    assert (destination/'independent-fiction.txt').read_text(encoding='utf-8') == 'synthetic retained publication'
    assert patched_functions() == originals


def test_idle_observer_never_calls_operations_scans_sleep_or_gc(tmp_path, monkeypatch):
    observer = api()
    parent = tmp_path/'uncreated-restores'

    def forbidden(*args, **kwargs):
        raise AssertionError('observation must not initiate work')

    with monkeypatch.context() as patch:
        for module, name, _ in STEPS:
            patch.setattr(module, name, forbidden)
        patch.setattr(os, 'rename', forbidden)
        patch.setattr(gc, 'collect', forbidden)
        patch.setattr(time, 'sleep', forbidden)
        originals = patched_functions()
        events = []
        with observer.observe_restore(parent, events, scan=forbidden):
            assert not parent.exists()
        assert events == [] and patched_functions() == originals


def test_renaming_a_stage_child_is_not_misreported_as_workspace_publication(tmp_path):
    observer = api()
    parent, root = stage_root(tmp_path)
    events = []
    with observer.observe_restore(parent, events, scan=lambda _:[]):
        os.rename(root/'workbench.db', parent/'moved-independent-fiction.db')
    assert events == [] and (parent/'moved-independent-fiction.db').is_file() and root.is_dir()
