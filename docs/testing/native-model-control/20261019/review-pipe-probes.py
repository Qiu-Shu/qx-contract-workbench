"""Independent pipe probes: real local byte pipe, synthetic synchronous handlers."""
import asyncio
import io
import json
import os
from threading import Thread
from uuid import uuid4

import pytest

from cn_contract.desktop_control import ParentControlChannel, MAX_BYTES, PROTOCOL, parse_control_line

NONCE = 'd' * 32


def frame(operation='disable', payload=None, sequence=1):
    return json.dumps(dict(event='model-control', protocol=PROTOCOL, nonce=NONCE,
        sequence=sequence, operation=operation, payload=payload or {}),
        ensure_ascii=False, separators=(',', ':')) + '\n'


def pipe():
    read, write = os.pipe()
    return os.fdopen(read, 'rb', buffering=0), os.fdopen(write, 'wb', buffering=0)


async def joined(worker):
    await asyncio.to_thread(worker.join, 2)
    assert not worker.is_alive()


def test_oversized_utf8_partial_frame_is_rejected_at_the_byte_limit():
    async def scenario():
        reader, writer = pipe()
        exits, emitted = [], []
        class Handler:
            def disable(self):
                return {'status': 'disabled'}
        channel = ParentControlChannel(reader, NONCE, lambda **v: emitted.append(v), lambda: None,
            fatal=exits.append, timeout=.1)
        channel.bind(Handler())
        worker = Thread(target=channel.watch, daemon=True)
        worker.start()
        raw = frame('configure', {'sentinel': '界' * 12000})[:-1].encode('utf-8')
        assert len(raw) > MAX_BYTES and len(raw.decode('utf-8')) < MAX_BYTES
        try:
            await asyncio.to_thread(writer.write, raw)
            await asyncio.sleep(.05)
            before_eof = list(exits)
        finally:
            writer.close()
            await joined(worker)
            reader.close()
        assert emitted == []
        assert before_eof == [2], 'over-limit byte frame remained pending until EOF/newline'
    asyncio.run(scenario())


@pytest.mark.parametrize('fault', ['secret-result', 'invalid-version', 'unknown-status'])
def test_ack_validation_never_projects_unexpected_handler_data(fault):
    async def scenario():
        exits, emitted = [], []
        class Handler:
            def configure(self, payload):
                value = {'status': 'configured', 'config_sha256': 'f' * 64, 'config_version': str(uuid4())}
                if fault == 'secret-result': value['secret'] = 'SYNTHETIC-ACK-PRIVATE'
                elif fault == 'invalid-version': value['config_version'] = 'SYNTHETIC-ACK-PRIVATE'
                else: value['status'] = 'SYNTHETIC-ACK-PRIVATE'
                return value
            def disable(self):
                return {'status': 'disabled'}
        channel = ParentControlChannel(io.BytesIO(frame('configure').encode('utf-8')), NONCE,
            lambda **v: emitted.append(v), lambda: None, fatal=exits.append)
        channel.bind(Handler())
        worker = Thread(target=channel.watch, daemon=True)
        worker.start()
        await joined(worker)
        assert exits == [2] and emitted == []
    asyncio.run(scenario())


def test_eof_disables_on_the_bound_loop_and_blocks_later_dispatch():
    async def scenario():
        closed, emitted, calls, exits = [], [], [], []
        class Handler:
            def disable(self):
                calls.append(asyncio.get_running_loop())
                return {'status': 'disabled'}
        channel = ParentControlChannel(io.BytesIO(b''), NONCE, lambda **v: emitted.append(v),
            lambda: closed.append(True), fatal=exits.append)
        channel.bind(Handler())
        worker = Thread(target=channel.watch, daemon=True)
        worker.start()
        await joined(worker)
        await asyncio.sleep(0)
        assert closed == [True] and calls == [asyncio.get_running_loop()]
        assert exits == [] and emitted == []
        with pytest.raises(ValueError, match='CONTROL_REJECTED'):
            await channel._dispatch('disable', {})
    asyncio.run(scenario())


def test_nested_duplicate_keys_and_depth_limit_never_dispatch():
    nested = '0'
    for _ in range(18): nested = '[' + nested + ']'
    for raw in [frame('configure').replace('"payload":{}', '"payload":{"x":1,"x":2}'),
                frame('configure').replace('"payload":{}', '"payload":{"x":' + nested + '}'),
                frame('configure').replace('"payload":{}', '"payload":{"x":1e999}'),
                frame(sequence=9007199254740992)]:
        with pytest.raises(ValueError, match='CONTROL_REJECTED'):
            parse_control_line(raw.encode('utf-8'), NONCE, 1)
