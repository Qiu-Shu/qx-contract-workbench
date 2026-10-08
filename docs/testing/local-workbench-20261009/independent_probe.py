import asyncio
from pathlib import Path
import tempfile
import threading
import sqlite3
from sqlalchemy import select
from cn_contract.web import local_server as local
from cn_contract.web import demo_server as demo
from cn_contract.persistence import UserRow

with tempfile.TemporaryDirectory(prefix='qx-independent-') as d:
    local.PROJECT_ROOT = Path(d)
    root = Path(d)/'.local'/'identity'
    local.initialize_workspace(root, 'independent-lawyer', 'independent-fiction-only-123')
    (root/'workbench.db').write_bytes(b'')
    app = local.build_local_app(root)
    with app.state.database.session() as db:
        users=list(db.scalars(select(UserRow)))
    print('EMPTY_DATABASE_ACCEPTED', len(users)==0, 'bytes_after', (root/'workbench.db').stat().st_size)
    app.state.database.engine.dispose()

    root2 = Path(d)/'.local'/'shutdown'
    local.initialize_workspace(root2, 'independent-lawyer', 'independent-fiction-only-123')
    started=threading.Event(); unblock=threading.Event()
    original=demo.run_next_job
    def blocked(db):
        started.set(); unblock.wait(25); return None
    demo.run_next_job=blocked
    app2=local.build_local_app(root2)
    async def probe():
        try:
            async with app2.router.lifespan_context(app2):
                assert started.wait(5)
        except RuntimeError as exc:
            print('SHUTDOWN_EXCEPTION', str(exc))
        print('OLD_WORKER_ALIVE', app2.state.worker_thread.is_alive())
        with local._worker_lock(root2):
            print('SECOND_LOCK_ACQUIRED_WHILE_OLD_WORKER_ALIVE', app2.state.worker_thread.is_alive())
    try: asyncio.run(probe())
    finally:
        unblock.set(); app2.state.worker_thread.join(5); demo.run_next_job=original
