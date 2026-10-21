"""Context transport groundwork; not registered with application sending.

The trusted assembler owns current permission and source revalidation. A basis
alone never authorizes this adapter; an omitted preflight always denies egress.
"""
from ... import domain as d
from .context_codec import build_request, decode_response
from .deepseek_transport import DeepSeekTransport


class DeepSeekContextProvider(DeepSeekTransport):
    async def generate(self, request, *, expected_config=None, preflight=None):
        return await self._generate(request, expected_config=expected_config,
            builder=build_request, decoder=decode_response, reply_type=d.MainContextReply,
            preflight=preflight if preflight is not None else lambda: False)
