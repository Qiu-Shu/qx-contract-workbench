"""Development MCP launch guard for audited code; not an OS/native-code sandbox."""
import contextvars
import json
import os
from pathlib import Path
import runpy
import socket
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SERVERS = {ROOT / 'bridge/server.py', ROOT / 'bridge/business_server.py'}
READER = ROOT / 'bridge/reader.py'
ENTRIES = {HERE / 'relay.py', READER, *SERVERS}


def install(log):
    log = Path(log)
    if not log.is_absolute():
        raise ValueError('Absolute network audit path required')
    pair = contextvars.ContextVar('local_event_loop_socketpair', default=False)
    launching = contextvars.ContextVar('guarded_mcp_launch', default=None)
    def record(event, operation):
        with log.open('a', encoding='utf-8') as output:
            output.write(json.dumps(dict(event=event, operation=operation, pid=os.getpid(), runtime='python')) + '\n')
    def denied(operation):
        record('denied', operation)
        raise PermissionError('EVAL_NETWORK_DENIED: ' + operation)
    original_pair = socket.socketpair
    def socketpair(*args, **kwargs):
        token = pair.set(True)
        try:
            return original_pair(*args, **kwargs)
        finally:
            pair.reset(token)
    socket.socketpair = socketpair
    original_popen = subprocess.Popen
    class GuardedPopen(original_popen):
        def __init__(self, args, *positional, **options):
            if (positional or not isinstance(args, (list, tuple)) or len(args) not in {2, 4}
                    or Path(args[0]).resolve() != Path(sys.executable).resolve()
                    or options.get('shell') or options.get('executable')):
                denied('subprocess.Popen')
            entry = Path(args[1]).resolve()
            if entry in SERVERS and len(args) == 4 and args[2] == '--workspace':
                if not Path(args[3]).resolve().is_relative_to(ROOT / '.local/quality-baseline'):
                    denied('subprocess.workspace')
            elif entry != READER or len(args) != 2:
                denied('subprocess.entry')
            options['env'] = {**(options.get('env') or os.environ), 'QX_EVAL_NETWORK_LOG': str(log),
                              'PYTHONINSPECT': '', 'PYTHONSTARTUP': '', 'DEEPSEEK_API_KEY': '',
                              'OPENAI_API_KEY': '', 'ANTHROPIC_API_KEY': ''}
            command = [args[0], str(Path(__file__).resolve()), *args[1:]]
            token = launching.set(command)
            try:
                super().__init__(command, executable=args[0], **options)
            finally:
                launching.reset(token)
    subprocess.Popen = GuardedPopen
    def audit(event, args):
        if event in {'socket.connect', 'socket.bind'}:
            # Windows asyncio uses stdlib socketpair internally, restricted to its own loopback pair.
            if not pair.get():
                denied(event)
        elif event.startswith('socket.get') or event in {'socket.sendto', 'socket.sendmsg'}:
            denied(event)
        elif event == 'subprocess.Popen':
            command = launching.get()
            if (command is None or Path(args[0]).resolve() != Path(sys.executable).resolve()
                    or args[1] not in (command, subprocess.list2cmdline(command))):
                denied(event)
        elif event == '_winapi.CreateProcess' and launching.get() is None:
            denied(event)
        elif event in {'os.system', 'os.posix_spawn', 'os.spawn', 'os.exec', 'os.fork', 'os.startfile', 'os.startfile/2'}:
            denied(event)
    sys.addaudithook(audit)
    record('guard_ready', 'default_deny')


if __name__ == '__main__':
    install(os.environ['QX_EVAL_NETWORK_LOG'])
    entry = Path(sys.argv[1]).resolve()
    if entry not in ENTRIES:
        raise ValueError('Entry outside evaluation allowlist')
    sys.argv = sys.argv[1:]
    sys.path.insert(0, str(entry.parent))
    runpy.run_path(str(entry), run_name='__main__')
