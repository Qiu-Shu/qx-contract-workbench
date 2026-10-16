"""Owned desktop child. Configuration uses stdin; stdout is a bounded protocol.

No HTTP route accepts workspace paths or provisioning credentials. Closing the
parent pipe requests normal worker shutdown; a stuck worker has a bounded exit.
"""
import json
import logging
import os
from pathlib import Path
import re
import socket
import sys
from threading import Event, Thread


def emit(event, **payload):
    print(json.dumps({'event': event, **payload}, ensure_ascii=True), flush=True)


def read_config():
    line = sys.stdin.readline(16385)
    if len(line) > 16384 or not line.endswith('\n'):
        raise ValueError('INVALID_CONFIG')
    value = json.loads(line)
    if (type(value) is not dict or set(value) - {'data_parent', 'nonce', 'username', 'password', 'library_root',
            'workspace', 'operation', 'archive', 'passphrase'}
            or not isinstance(value.get('nonce'), str) or not re.fullmatch('[0-9a-f]{32}', value['nonce'])
            or not isinstance(value.get('data_parent'), str) or not Path(value['data_parent']).is_absolute()):
        raise ValueError('INVALID_CONFIG')
    if not isinstance(value.get('workspace','main'),str) or not re.fullmatch(
            r'main|recovered/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}',value.get('workspace','main')):
        raise ValueError('INVALID_CONFIG')
    if 'operation' in value:
        if (value['operation'] not in ('backup','restore') or type(value.get('passphrase')) is not str
                or type(value.get('archive')) is not str or not Path(value['archive']).is_absolute()
                or 'username' in value or 'password' in value):
            raise ValueError('INVALID_CONFIG')
    elif 'passphrase' in value or 'archive' in value:
        raise ValueError('INVALID_CONFIG')
    if value.get('library_root') is not None and (not isinstance(value['library_root'], str)
            or not Path(value['library_root']).is_absolute()):
        raise ValueError('INVALID_CONFIG')
    return value


def main():
    # Never render request data, credentials, paths or exception tracebacks.
    logging.disable(logging.CRITICAL)
    if hasattr(sys.stdin, 'reconfigure'): sys.stdin.reconfigure(encoding='utf-8')
    if hasattr(sys.stdout, 'reconfigure'): sys.stdout.reconfigure(encoding='utf-8')
    finished = Event()
    shutdown = Event()
    server_holder = []
    try:
        config = read_config()

        def watch_parent():
            # Cover imports, initialization and validation as well as serving.
            sys.stdin.readline(256)
            shutdown.set()
            if server_holder: server_holder[0].should_exit = True
            if not finished.wait(15): os._exit(2)

        Thread(target=watch_parent, daemon=True).start()
        from .web.local_server import build_local_app, initialize_workspace
        import uvicorn
        parent = Path(config['data_parent'])
        root = parent / 'workspaces' / config.get('workspace','main')
        if 'operation' in config:
            from .ops.workspace_backup import create_workspace_backup, restore_workspace_backup
            if config['operation']=='backup':
                result=create_workspace_backup(root,config['archive'],config['passphrase'],data_parent=parent)
            else:
                result=restore_workspace_backup(config['archive'],parent/'workspaces'/'recovered',config['passphrase'])
            emit('complete',nonce=config['nonce'],report=result)
            return 0
        if not root.exists():
            if config.get('workspace','main')!='main':raise ValueError('WORKSPACE_NOT_INITIALIZED')
            initialize_workspace(root, config.get('username'), config.get('password'), data_parent=parent)
        elif 'username' in config or 'password' in config:
            raise ValueError('WORKSPACE_ALREADY_EXISTS')
        # Do not free and re-bind the selected port: retain the very same socket.
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            if os.name == 'nt': sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            sock.bind(('127.0.0.1', 0))
            sock.listen(128)
            port = sock.getsockname()[1]
            app = build_local_app(root, data_parent=parent, port=port, library_root=config.get('library_root'))
            server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=port,
                workers=1, access_log=False, log_config=None, log_level='critical'))
            server_holder.append(server)
            if shutdown.is_set(): return 0

            def announce_ready():
                while not finished.wait(.05):
                    if server.started:
                        emit('ready', port=port, nonce=config['nonce'])
                        return

            Thread(target=announce_ready, daemon=True).start()
            try:
                server.run(sockets=[sock])
                if not server.started: raise ValueError('START_FAILED')
            finally:
                finished.set()
        return 0
    except BaseException as error:
        allowed={'ARCHIVE_AUTHENTICATION_FAILED','BACKUP_DESTINATION_INVALID','BACKUP_PASSPHRASE_INVALID',
                 'WORKSPACE_IN_USE','ARCHIVE_LIMIT','FILE_LIMIT','FILE_COUNT_LIMIT'}
        code=str(error) if isinstance(error,ValueError) and str(error) in allowed else 'DESKTOP_BACKEND_REJECTED'
        emit('error', code=code)
        return 1
    finally:
        finished.set()


if __name__ == '__main__':
    raise SystemExit(main())
