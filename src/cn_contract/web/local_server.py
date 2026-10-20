"""Persistent loopback workbench; local accounts, registered fiction only."""
import argparse
from contextlib import asynccontextmanager, closing, contextmanager
import getpass
import hashlib
import json
import os
import sqlite3
from pathlib import Path
import sys
from unicodedata import category
from uuid import UUID, uuid4

from sqlalchemy import select

from ..config import PROJECT_ROOT, load_settings
from ..domain import Role
from ..ops.backup import redirected
from ..persistence import Database, UserRow
from ..security import ServiceError, provision_user
from ..storage_bootstrap import initialize_storage, mark_storage_initialized
from ..storage_schema import CURRENT_VERSION, identify_schema
from ..schema_migrations import database_rows
from .app import create_app
from .assisted_demo_server import load_seed_policy, SEED_MANIFEST_SHA256
from .demo_server import attach_job_worker


def _workspace_path(directory, *, data_parent=None):
    path = Path(directory).absolute()
    for item in (path, *path.parents):
        if (item.exists() or item.is_symlink()) and redirected(item):
            raise ValueError('REDIRECTED_WORKSPACE')
    path = path.resolve()
    # Only trusted native entry points may supply a parent; HTTP never does.
    parent = Path(data_parent).resolve() if data_parent is not None else (PROJECT_ROOT / '.local').resolve()
    if not path.is_relative_to(parent) or path == parent:
        raise ValueError('PROJECT_LOCAL_DIRECTORY_REQUIRED')
    return path


def _credentials(username, password):
    if (type(username) is not str or not 1 <= len(username) <= 128 or username != username.strip()
            or any(category(c) in ('Cc', 'Cf') for c in username)
            or type(password) is not str or not 6 <= len(password) <= 12):
        raise ValueError('LOCAL_CREDENTIALS_INVALID')


def _marker():
    load_seed_policy()  # Recheck registered material bytes on every startup.
    return {'format': 1, 'purpose': 'assisted_draft', 'material_manifest_sha256': SEED_MANIFEST_SHA256,
            'config_sha256': load_settings().config_sha256}


def _safe_file(path):
    if path.exists() or path.is_symlink():
        if redirected(path) or (path.is_file() and path.stat().st_nlink != 1):
            raise ValueError('REDIRECTED_WORKSPACE')


def _open_workspace(directory, *, data_parent=None):
    root = _workspace_path(directory, data_parent=data_parent)
    for name in ('workspace.json', 'workbench.db', 'workbench.db-wal', 'workbench.db-shm',
                 'workbench.db-journal', 'protected', 'worker.lock'):
        _safe_file(root / name)
    marker = root / 'workspace.json'
    if (not marker.is_file() or marker.stat().st_size > 4096
            or not (root / 'workbench.db').is_file() or not (root / 'protected').is_dir()):
        raise ValueError('WORKSPACE_NOT_INITIALIZED')
    payload = json.loads(marker.read_text(encoding='utf-8'))
    expected = _marker()
    if (type(payload) is not dict or set(payload) != set(expected) | {'workspace_id', 'schema_sha256'}
            or any(payload[k] != v for k, v in expected.items())):
        raise ValueError('WORKSPACE_POLICY_MISMATCH')
    try:
        if str(UUID(payload['workspace_id'])) != payload['workspace_id']:
            raise ValueError('WORKSPACE_ID_INVALID')
        # Read-only validation precedes any create_all/trigger initialization.
        with closing(sqlite3.connect((root / 'workbench.db').as_uri() + '?mode=ro', uri=True)) as db:
            from .workspace_upgrade import pending_matches
            try:
                identify_schema(database_rows(db), native=True)
            except ValueError:
                raise ValueError('WORKSPACE_DATABASE_MISMATCH') from None
            if (db.execute('PRAGMA quick_check').fetchall() != [('ok',)]
                    or db.execute('PRAGMA foreign_key_check').fetchall()
                    or db.execute('SELECT id FROM local_workspace_identity').fetchall() != [(payload['workspace_id'],)]
                    or (_schema_hash(db) != payload['schema_sha256'] and not pending_matches(db,root,payload))):
                raise ValueError('WORKSPACE_DATABASE_MISMATCH')
    except (sqlite3.Error, TypeError, AttributeError):
        raise ValueError('WORKSPACE_DATABASE_INVALID') from None
    return root


def _schema_hash(db):
    rows = db.execute("SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name").fetchall()
    return hashlib.sha256(json.dumps(rows, ensure_ascii=False, separators=(',', ':')).encode('utf-8')).hexdigest()


def _database(root, *, initialize=False):
    if not initialize:
        with closing(sqlite3.connect((root / 'workbench.db').as_uri() + '?mode=ro', uri=True)) as connection:
            if identify_schema(database_rows(connection), native=True) != CURRENT_VERSION:
                raise ValueError('WORKSPACE_DATABASE_MISMATCH')
    database = Database('sqlite:///' + str(root / 'workbench.db'), root / 'protected', load_settings(),
                        initialize_schema=initialize)
    try:
        if initialize:
            initialize_storage(database)
        else:
            mark_storage_initialized(database)
        return database
    except BaseException:
        database.engine.dispose()
        raise


def initialize_workspace(directory, username, password, *, data_parent=None):
    _credentials(username, password)
    root = _workspace_path(directory, data_parent=data_parent)
    marker = _marker()
    if root.exists():
        raise ValueError('WORKSPACE_ALREADY_EXISTS')
    root.mkdir(parents=True, exist_ok=False)
    database = _database(root, initialize=True)
    try:
        with database.session() as db:
            provision_user(username, password, {Role.HANDLING_LAWYER}, db, local_workbench_password=True)
        marker['workspace_id'] = str(uuid4())
        with closing(sqlite3.connect(root / 'workbench.db')) as db:
            with db:
                db.execute('CREATE TABLE local_workspace_identity (id TEXT PRIMARY KEY NOT NULL)')
                db.execute('INSERT INTO local_workspace_identity (id) VALUES (?)', (marker['workspace_id'],))
                marker['schema_sha256'] = _schema_hash(db)
        # A partial initialization is never silently repaired or overwritten.
        with (root / 'workspace.json').open('x', encoding='utf-8') as output:
            json.dump(marker, output, ensure_ascii=False, indent=2)
    finally:
        database.engine.dispose()
    return root


def add_local_user(directory, username, password, role):
    _credentials(username, password)
    role = Role(role)
    root = _open_workspace(directory)
    # Maintenance runs in another process; stop the server so all grants expire.
    with _worker_lock(root):
        from .workspace_upgrade import upgrade
        upgrade(root)
        database = _database(root)
        try:
            with database.session() as db:
                if db.scalar(select(UserRow).where(UserRow.username == username)):
                    raise ValueError('LOCAL_ACCOUNT_EXISTS')
                return provision_user(username, password, {role}, db, local_workbench_password=True)
        finally:
            database.engine.dispose()


@contextmanager
def _worker_lock(root):
    path = root / 'worker.lock'
    _safe_file(path)
    with path.open('a+b') as stream:
        if path.stat().st_size == 0:
            stream.write(b'0'); stream.flush()
        stream.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise ValueError('WORKSPACE_IN_USE') from None
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == 'nt':
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def build_local_app(directory, *, port=8767, library_root=None, data_parent=None, assistant_model_runtime=None):
    root = _open_workspace(directory, data_parent=data_parent)
    with _worker_lock(root):
        from .workspace_upgrade import upgrade
        upgrade(root)
        database = _database(root)
    try:
        app = create_app(load_settings(), database=database, purpose='assisted_draft',
                         assisted_policy=load_seed_policy(), local_materials_enabled=True,
                         assistant_home_enabled=True, assistant_model_runtime=assistant_model_runtime)
        from .recovery import attach_recovery
        attach_recovery(app,database)
        if library_root is not None:
            from .library import attach_library
            attach_library(app, database, library_root)
        bridge = None
        if root == (PROJECT_ROOT / '.local' / 'workbench').resolve() and port == 8767:
            from .case_bridge import attach_case_bridge
            bridge = attach_case_bridge(app, database, root / 'selected-case.json')
        # Hold the OS lock until the worker exits; force-stopping the process
        # releases the OS lock naturally and recovery runs on the next startup.
        attach_job_worker(app, database, shutdown_timeout=None)
    except BaseException:
        database.engine.dispose()
        raise
    worker_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(application):
        try:
            with _worker_lock(root):
                if bridge: bridge.close()
                try:
                    from ..assistant.providers.attempts import recover_attempts
                    from ..assistant.providers.judge_attempts import recover_attempts as recover_judges
                    from ..ops.storage import quarantined
                    with database.session() as db:
                        if not quarantined(db):
                            recover_judges(db)
                            recover_attempts(db)
                    async with worker_lifespan(application):
                        yield
                finally:
                    if bridge: bridge.close()
        finally:
            database.engine.dispose()

    app.router.lifespan_context = lifespan
    return app


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        # Never reflect accidental password arguments into the console or logs.
        self.exit(2, '参数无效；使用 --help，密码仅在本机隐藏输入。\n')


def _prompt_password():
    if not sys.stdin.isatty():
        raise ValueError('INTERACTIVE_PASSWORD_REQUIRED')
    password = getpass.getpass('本机账户密码（6–12位，不显示）：')
    if password != getpass.getpass('再次输入：'):
        raise ValueError('PASSWORD_MISMATCH')
    return password


def main(argv=None):
    parser = _Parser(description='群兴持久工作台：个人本机账户、案件原地保存，本机DOCX须逐份确认')
    commands = parser.add_subparsers(dest='command', required=True)
    for command in ('init', 'add-user', 'serve', 'start'):
        item = commands.add_parser(command)
        item.add_argument('--directory', type=Path, default=PROJECT_ROOT / '.local' / 'workbench')
        if command in ('init', 'add-user'):
            item.add_argument('--username', required=True)
        if command == 'add-user':
            item.add_argument('--role', choices=[r.value for r in Role], required=True)
        if command in ('serve', 'start'):
            item.add_argument('--port', type=int, default=8767)
            item.add_argument('--library-directory', type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command in ('serve', 'start'):
            if not 1024 <= args.port <= 65535:
                raise ValueError('INVALID_PORT')
            if args.command == 'start' and not _workspace_path(args.directory).exists():
                if not sys.stdin.isatty():
                    raise ValueError('INTERACTIVE_PASSWORD_REQUIRED')
                username = input('首次使用，请设置本机用户名：')
                initialize_workspace(args.directory, username, _prompt_password())
            import uvicorn
            app = build_local_app(args.directory, port=args.port, library_root=args.library_directory)
            print(f'本机工作台：http://127.0.0.1:{args.port}/login', flush=True)
            print('案件原地保存；本机DOCX逐份确认后供人工工作稿；真实模型与企查查关闭。', flush=True)
            uvicorn.run(app, host='127.0.0.1', port=args.port, workers=1, access_log=False, log_level='warning')
        else:
            password = _prompt_password()
            if args.command == 'init':
                initialize_workspace(args.directory, args.username, password)
            else:
                add_local_user(args.directory, args.username, password, args.role)
            print('本机账户已建立；密码不保存为明文、不进入日志。')
        return 0
    except (ValueError, OSError, ServiceError) as error:
        # Only fixed messages may be shown; exception text can contain secrets.
        hints = {
            'PASSWORD_MISMATCH': '两次密码不一致，请重新启动后输入相同密码。',
            'LOCAL_CREDENTIALS_INVALID': '密码须为6–12位；用户名须为1–128位，不能有首尾空格或控制字符。',
            'INTERACTIVE_PASSWORD_REQUIRED': '请在本机交互窗口运行启动工作台.cmd，并在隐藏提示中输入密码。',
        }
        hint = hints.get(str(error), '检查目录、账户或密码输入。') if type(error) is ValueError else '检查目录、账户或密码输入。'
        print(f'LOCAL_WORKBENCH_REJECTED：{hint}已有数据不会重置。', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
