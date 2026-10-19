"""Test-only child: production framing with a synthetic no-op control handler."""
import asyncio
import sys
from threading import Thread
from uuid import UUID

from cn_contract.desktop_control import ParentControlChannel, PROTOCOL
from cn_contract.desktop_entry import emit, read_config


sys.stdout.reconfigure(encoding='utf-8', newline='\n')
config = read_config(sys.stdin.buffer)


class Handler:
    def configure(self, payload):
        result = {'status': 'configured', 'config_sha256': 'e' * 64,
            'config_version': str(UUID(int=1))}
        if len(sys.argv) > 1:
            result['secret'] = payload['secret']
        return result

    def disable(self):
        return {'status': 'disabled'}

    def revoke(self, payload):
        return {'status': 'revoked'}


async def main():
    loop = asyncio.get_running_loop()
    ended = asyncio.Event()
    channel = ParentControlChannel(sys.stdin.buffer, config['nonce'], emit,
        lambda: loop.call_soon_threadsafe(ended.set))
    channel.bind(Handler())
    Thread(target=channel.watch, daemon=True).start()
    emit('ready', port=19023, nonce=config['nonce'], control_protocol=PROTOCOL)
    await ended.wait()


asyncio.run(main())
