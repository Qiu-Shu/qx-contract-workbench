"""Private pipe framing; no application credentials or external endpoints."""
import asyncio
from io import BytesIO
import json
from threading import Thread
from uuid import uuid4

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


@pytest.mark.parametrize('operation', ['configure_judge', 'disable_judge'])
def test_fixed_judge_operations_share_the_existing_frame(operation):
    assert parse_control_line(line(operation=operation), NONCE, 1) == (operation, {})


@pytest.mark.parametrize('raw', [
    line(nonce='b'*32), line(sequence=True), line(sequence=2), line(sequence=1.0),
    line(sequence=9007199254740992), line(operation='shell'), line(payload=[]),
    line(extra='not allowed'), line().replace('"sequence":1', '"sequence":1,"sequence":1'),
    line()[:-1], line(payload={'x':'字'*12000}), line(payload={'x':float('nan')}),
    line(operation='authorize_judge'), line(operation='revoke_judge'), line(operation='disable_all'),
    line(protocol='qx-judge-control-v1'),
], ids=['nonce','bool-sequence','order','float-sequence','unsafe-sequence','operation',
        'payload-type','extra-key','duplicate-key','partial','oversize','nonfinite',
        'no-judge-authorize','no-judge-revoke','no-public-disable-all','capability-not-frame-version'])
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


class LocalControl:
    def __init__(self):
        self.configured = False
        self.loops = []

    def configure(self, payload):
        self.loops.append(asyncio.get_running_loop())
        if payload.get('crash'):
            raise RuntimeError('SYNTHETIC_SECRET_MUST_NOT_ESCAPE')
        self.configured = True
        result = {'status': 'configured', 'config_sha256': 'a'*64, 'config_version': str(uuid4())}
        if payload.get('bad_ack'):
            result['secret'] = 'SYNTHETIC_SECRET_MUST_NOT_ESCAPE'
        return result

    def disable(self):
        self.loops.append(asyncio.get_running_loop())
        self.configured = False
        return {'status': 'disabled'}

    def authorize(self, payload):
        return {'status': 'authorized'}

    def revoke(self, payload):
        return {'status': 'revoked'}


def test_single_service_disable_is_isolated_and_close_disables_both():
    from cn_contract.desktop_control import NativeControlHandler
    async def scenario():
        main, judge = LocalControl(), LocalControl()
        handler = NativeControlHandler(main, judge)
        handler.configure({}); handler.configure_judge({})
        handler.disable()
        assert not main.configured and judge.configured
        handler.configure({}); handler.disable_judge()
        assert main.configured and not judge.configured
        handler.configure_judge({})
        channel = ParentControlChannel(BytesIO(), NONCE, lambda **v:None, lambda:None)
        channel.bind(handler); channel.close()
        assert not main.configured and not judge.configured
    asyncio.run(scenario())


def test_both_cleanup_paths_are_attempted_if_main_cleanup_raises():
    from cn_contract.desktop_control import NativeControlHandler
    async def scenario():
        main, judge = LocalControl(), LocalControl()
        def broken_disable():
            raise RuntimeError('SYNTHETIC_CLEANUP_FAILURE')
        main.disable = broken_disable
        handler = NativeControlHandler(main, judge)
        handler.configure_judge({})
        with pytest.raises(RuntimeError): handler.disable_all()
        assert not judge.configured
    asyncio.run(scenario())


@pytest.mark.parametrize('operation', ['disable', 'disable_judge'])
def test_disable_requires_empty_payload_without_side_effects(operation):
    from cn_contract.desktop_control import NativeControlHandler
    async def scenario():
        main, judge = LocalControl(), LocalControl()
        handler = NativeControlHandler(main, judge)
        handler.configure({}); handler.configure_judge({})
        outputs = []
        # Inspect the public acknowledgement before EOF performs the final cleanup.
        def emit(**value):
            outputs.append(value)
            assert main.configured and judge.configured
        channel = ParentControlChannel(BytesIO(line(operation=operation, payload={'extra': True}).encode()),
            NONCE, emit, lambda:None, fatal=lambda code:pytest.fail('unexpected fatal exit'))
        channel.bind(handler)
        worker = Thread(target=channel.watch)
        worker.start()
        while worker.is_alive(): await asyncio.sleep(.001)
        worker.join()
        assert len(outputs) == 1 and outputs[0]['ok'] is False and outputs[0]['code'] == 'BLOCKED_LIVE'
        assert not main.configured and not judge.configured
    asyncio.run(scenario())


@pytest.mark.parametrize('ending', ['eof', 'bad-frame', 'bad-ack', 'unexpected-error'])
def test_pipe_failure_or_eof_clears_both_on_the_application_loop(ending):
    from cn_contract.desktop_control import NativeControlHandler
    async def scenario():
        main, judge = LocalControl(), LocalControl()
        outputs, exits, stopped = [], [], []
        frames = line(operation='configure') + line(sequence=2, operation='configure_judge')
        if ending == 'bad-frame': frames += 'not-json\n'
        if ending == 'bad-ack': frames += line(sequence=3, operation='configure_judge', payload={'bad_ack': True})
        if ending == 'unexpected-error': frames += line(sequence=3, operation='configure_judge', payload={'crash': True})
        channel = ParentControlChannel(BytesIO(frames.encode()), NONCE, lambda **v:outputs.append(v),
            lambda:stopped.append(True), fatal=exits.append, timeout=1)
        channel.bind(NativeControlHandler(main, judge))
        worker = Thread(target=channel.watch)
        worker.start()
        while worker.is_alive(): await asyncio.sleep(.001)
        worker.join()
        assert not main.configured and not judge.configured
        assert all(loop is asyncio.get_running_loop() for loop in main.loops + judge.loops)
        assert [item['sequence'] for item in outputs] == ([1, 2, 3] if ending == 'unexpected-error' else [1, 2])
        assert exits == ([2] if ending in ('bad-frame', 'bad-ack') else [])
        if ending == 'unexpected-error':
            assert outputs[-1]['ok'] is False and outputs[-1]['code'] == 'BLOCKED_LIVE'
        assert 'SYNTHETIC_SECRET' not in repr(outputs)
    asyncio.run(scenario())
