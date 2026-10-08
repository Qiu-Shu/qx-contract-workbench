import asyncio
from contextlib import closing
from pathlib import Path
import tempfile
import threading
import sqlite3
from cn_contract.web import local_server as local
from cn_contract.web import demo_server as demo
from cn_contract.domain import Role

with tempfile.TemporaryDirectory(prefix='qx-independent-fixed-') as d:
    local.PROJECT_ROOT=Path(d)
    for corruption in ('empty','missing-table','other-workspace'):
        root=Path(d)/'.local'/corruption
        local.initialize_workspace(root,'independent-lawyer','independent-fiction-only-123')
        path=root/'workbench.db'
        if corruption=='empty': path.write_bytes(b'')
        elif corruption=='missing-table':
            with closing(sqlite3.connect(path)) as db:
                db.execute('DROP TABLE web_http_writes');db.commit()
        else:
            other=root.with_name('replacement')
            local.initialize_workspace(other,'independent-lawyer','independent-fiction-only-123')
            path.write_bytes((other/'workbench.db').read_bytes())
        before=path.read_bytes()
        for operation in (lambda:local.build_local_app(root), lambda:local.add_local_user(root,'new-assistant','independent-fiction-only-456',Role.ASSISTANT)):
            try: operation()
            except ValueError: pass
            else: raise AssertionError('corruption accepted')
            assert path.read_bytes()==before
        print('REJECTED_BEFORE_WRITE',corruption,'serve_and_add_user')

    root=Path(d)/'.local'/'shutdown'
    local.initialize_workspace(root,'independent-lawyer','independent-fiction-only-123')
    running=threading.Event();release=threading.Event();results=[]
    original=demo.run_next_job
    def blocked(db):
        running.set();release.wait(20);return None
    demo.run_next_job=blocked
    app=local.build_local_app(root)
    def observer():
        assert running.wait(3)
        threading.Event().wait(10.5)
        try:
            with local._worker_lock(root): results.append('EARLY_UNLOCK')
        except ValueError as exc: results.append(str(exc))
        finally: release.set()
    monitor=threading.Thread(target=observer)
    monitor.start()
    async def probe():
        async with app.router.lifespan_context(app):
            assert running.wait(3)
    try:
        asyncio.run(probe())
        monitor.join(3)
        assert results==['WORKSPACE_IN_USE'],results
        assert not app.state.worker_thread.is_alive()
        with local._worker_lock(root): pass
        print('SHUTDOWN_LOCK_RETAINED_PAST_10_SECONDS_AND_RELEASED_AFTER_WORKER_EXIT',True)
    finally:
        release.set();monitor.join(3);demo.run_next_job=original
