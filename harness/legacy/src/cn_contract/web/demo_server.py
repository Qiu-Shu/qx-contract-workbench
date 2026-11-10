"""Explicit loopback-only independent synthetic demo startup, no real accounts."""
from contextlib import asynccontextmanager
from pathlib import Path
from threading import Event, Thread
from uuid import uuid4

from ..config import PROJECT_ROOT, load_settings
from ..domain import Role
from ..persistence import Database
from ..security import provision_user
from ..storage_bootstrap import initialize_storage
from .app import create_app
from .jobs import recover_jobs, run_next_job

DEMO_PASSWORD='synthetic-only-12345'


def build_demo(directory=None,*,purpose='mock_demo',assisted_policy=None):
    root=Path(directory).resolve() if directory else (PROJECT_ROOT/'.local/http-demo'/uuid4().hex).resolve()
    approved=(PROJECT_ROOT/'.local').resolve()
    if not root.is_relative_to(approved) or root==approved or root.exists():
        raise ValueError('a new directory within project .local is required')
    root.mkdir(parents=True,exist_ok=False)
    database=Database('sqlite:///'+str(root/'workbench.db'),root/'protected',load_settings())
    initialize_storage(database)
    with database.session() as db:
        users={}
        for name,role in [('lawyer',Role.HANDLING_LAWYER),('reviewer',Role.REVIEWING_LAWYER),
                          ('assistant',Role.ASSISTANT),('admin',Role.ADMIN)]:
            users[name]=provision_user(name,DEMO_PASSWORD,{role},db)
    app=create_app(load_settings(),database=database,synthetic_signing_user_ids={users['reviewer']},
        purpose=purpose,assisted_policy=assisted_policy)
    attach_job_worker(app,database)
    return app,root


def attach_job_worker(app,database,*,shutdown_timeout=10):
    """Shared single worker lifecycle for explicit local startup paths."""
    stop=Event()
    previous=app.router.lifespan_context

    def worker():
        while not stop.is_set():
            if run_next_job(database) is None:stop.wait(.2)

    @asynccontextmanager
    async def lifespan(application):
        try:
            recover_jobs(database)
            stop.clear()
            thread=Thread(target=worker,name='synthetic-single-worker',daemon=True)
            application.state.worker_thread=thread;thread.start()
            try:
                async with previous(application):yield
            finally:
                stop.set();thread.join(timeout=shutdown_timeout)
                if thread.is_alive():raise RuntimeError('worker still running; shutdown incomplete')
        finally:
            database.engine.dispose()
    app.router.lifespan_context=lifespan


def serve(*,port=8765,directory=None):
    if type(port) is not int or not 1024<=port<=65535:raise ValueError('local unprivileged port required')
    import uvicorn
    app,root=build_demo(directory)
    print('仅本机独立虚构演示；真实模型/QCC关闭；mock不能正式签发。',flush=True)
    print(f'http://127.0.0.1:{port}/login',flush=True)
    print('演示用户名：lawyer / reviewer / assistant / admin；演示密码：'+DEMO_PASSWORD,flush=True)
    print('建立案件时可明确填写复核用户名 reviewer；不自动邀请所有用户。',flush=True)
    uvicorn.run(app,host='127.0.0.1',port=port,workers=1,access_log=False,log_level='warning')
