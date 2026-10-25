"""Opt-in observation for one independent development restore process.

No restore is initiated here. Global wrappers are temporary and unsuitable for
the application server; observations cannot prove absence of external locks.
"""
from contextlib import contextmanager
from functools import wraps
import os
from pathlib import Path

if __package__:
    from .restore_handles import _absolute, own_process_handles
else:
    from restore_handles import _absolute, own_process_handles

_observing = False


@contextmanager
def observe_restore(parent, events, *, scan=None):
    """Observe only parent/.qx-restore-*/workspace and restore every wrapper."""
    global _observing
    if _observing:
        raise RuntimeError('Nested restore observation is unsupported')
    _observing = True
    saved = []
    try:
        from cn_contract.ops import workspace_backup
        from cn_contract.web import workspace_upgrade
        parent = _absolute(parent)
        scanner = own_process_handles if scan is None else scan

        def stage(path):
            try:
                root = _absolute(path)
                if (os.path.normcase(root.name) == os.path.normcase('workspace')
                        and os.path.normcase(root.parent.name).startswith(os.path.normcase('.qx-restore-'))
                        and root.parent.parent == parent):
                    return root
            except (TypeError, ValueError, OSError):
                pass
            return None

        def record(phase, root, error=None):
            event = dict(phase=phase, handles=[], scan_status='OK', cwd_inside_stage=False,
                stage_path_length=len(str(root)))
            try:
                event['handles'] = list(scanner(root))
                event['cwd_inside_stage'] = _absolute(Path.cwd()).is_relative_to(root)
            except BaseException as failure:
                event.update(scan_status='ERROR', scan_exception_type=type(failure).__name__)
            if error is not None:
                event.update(exception_type=type(error).__name__, errno=getattr(error, 'errno', None),
                    winerror=getattr(error, 'winerror', None))
            events.append(event)

        def patch(module, name, function):
            saved.append((module, name, getattr(module, name)))
            setattr(module, name, function)

        def wrap(module, name, position):
            original = getattr(module, name)

            @wraps(original)
            def observed(*args, **kwargs):
                root = stage(args[position] if len(args) > position else kwargs.get('root'))
                if root is None:
                    return original(*args, **kwargs)
                record(name+':enter', root)
                try:
                    value = original(*args, **kwargs)
                except BaseException as error:
                    record(name+':error', root, error)
                    raise
                record(name+':exit', root)
                return value

            patch(module, name, observed)

        for name, position in (('_unpack', 1), ('_references', 0), ('_validate_database', 0), ('_fence', 0)):
            wrap(workspace_backup, name, position)
        wrap(workspace_upgrade, 'upgrade', 0)
        original_rename = os.rename

        @wraps(original_rename)
        def rename(*args, **kwargs):
            root = stage(args[0] if args else kwargs.get('src'))
            try:
                target = _absolute(args[1] if len(args) > 1 else kwargs.get('dst'))
                publish_target = target.parent == parent
            except (TypeError, ValueError, OSError):
                publish_target = False
            if root is None or not publish_target:
                return original_rename(*args, **kwargs)
            record('publish:before', root)
            try:
                value = original_rename(*args, **kwargs)
            except BaseException as error:
                record('publish:failure', root, error)
                raise
            record('publish:success', root)
            return value

        patch(os, 'rename', rename)
        yield
    finally:
        for module, name, original in reversed(saved):
            setattr(module, name, original)
        _observing = False
