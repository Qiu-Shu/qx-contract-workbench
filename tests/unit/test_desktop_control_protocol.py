"""Private pipe framing; no application credentials or external endpoints."""
import asyncio
from io import BytesIO
import json
from threading import Thread

import pytest

from cn_contract.desktop_control import ParentControlChannel, parse_control_line, PROTOCOL

NONCE = 'a' * 32


def line(**changes):
    value = dict(event='model-control', protocol=PROTOCOL, nonce=NONCE,
                 sequence=1, operation='disable', payload={})
    value.update(changes)
    return json.dumps(value, separators=(',', ':'))+'\n'


def test_valid_frame_and_exact_sequence():
    assert parse_control_line(line(), NONCE, 1) == ('disable', {})


@pytest.mark.parametrize('raw', [
    line(nonce='b'*32), line(sequence=True), line(sequence=2), line(sequence=1.0),
    line(sequence=9007199254740992), line(operation='shell'), line(payload=[]),
    line(extra='not allowed'), line().replace('"sequence":1', '"sequence":1,"sequence":1'),
    line()[:-1], line(payload={'x':'字'*12000}), line(payload={'x':float('nan')}),
], ids=['nonce','bool-sequence','order','float-sequence','unsafe-sequence','operation',
        'payload-type','extra-key','duplicate-key','partial','oversize','nonfinite'])
def test_invalid_frames_never_dispatch(raw):
    with pytest.raises(ValueError):
        parse_control_line(raw, NONCE, 1)


def test_early_command_is_fatal_without_ack_or_handler():
    emitted, exits = [], []
    channel = ParentControlChannel(BytesIO(line().encode()), NONCE, lambda **v:emitted.append(v),
                                  lambda:None, fatal=exits.append)
    channel.watch()
    assert exits == [2] and emitted == []


def test_command_runs_on_bound_loop_and_eof_closes_configuration():
    async def scenario():
        outputs, exits, loops, stopped = [], [], [], []
        class Handler:
            def disable(self):
                loops.append(asyncio.get_running_loop())
                return {'status':'disabled'}
        channel = ParentControlChannel(BytesIO(line().encode()), NONCE, lambda **v:outputs.append(v),
                                      lambda:stopped.append(True), fatal=exits.append)
        channel.bind(Handler())
        worker = Thread(target=channel.watch)
        worker.start()
        while worker.is_alive():
            await asyncio.sleep(.001)
        worker.join()
        await asyncio.sleep(0)
        assert exits == [] and stopped == [True]
        assert loops and all(loop is asyncio.get_running_loop() for loop in loops)
        assert outputs == [dict(event='model-control-result', protocol=PROTOCOL,
            nonce=NONCE, sequence=1, ok=True, status='disabled')]
    asyncio.run(scenario())
