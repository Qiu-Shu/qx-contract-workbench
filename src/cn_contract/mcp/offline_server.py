"""Two synthetic-only tools over the installed SDK's local STDIO transport.

Run with ``python -X utf8 -m cn_contract.mcp.offline_server``. This controlled
local process has no established transport-frame or OS CPU/memory hard limits.
It does not invoke providers or the review workflow, access case databases,
or read settings or credentials. Existing package imports still occur normally.
"""

from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import stat
from uuid import NAMESPACE_URL, UUID, uuid5
from zipfile import ZipFile

import anyio
from defusedxml import ElementTree
from mcp.server.lowlevel import Server
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.tools import Tool
from mcp.server.stdio import stdio_server
from mcp.shared.exceptions import MCPError
from mcp.shared.message import SessionMessage
from mcp_types import (INVALID_PARAMS, ErrorData, JSONRPCError, ListToolsResult,
                       ToolAnnotations)

from ..domain import (DeepSeekModelId, DeepSeekOperation, McpOfflineExample,
    McpOfflineExampleArguments, McpOfflineFixture, McpOfflineStatus,
    ModelRequest, ModelUsageLimit, ReviewContext)
from ..review.deepseek_codec import build_chat_request, decode_chat_response


_FIXTURE_DIRECTORY = Path(__file__).resolve().parents[3] / 'tests' / 'fixtures' / 'synthetic'
# The existing T06 independent fixture registry, read once as inert metadata.
# Importing it does not call its writer or selector and does not start a review.
from ..review.synthetic import EXPECTED_HASHES, FIXTURES

_REJECTED = 'OFFLINE_REQUEST_REJECTED'
_UNAVAILABLE = 'OFFLINE_EXAMPLE_UNAVAILABLE'
_W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
_MAX_FIXTURE_BYTES = 16384
_MAX_XML_BYTES = 8192
_MAX_OUTPUT_TOKENS = 128


def workbench_status() -> McpOfflineStatus:
    """本机虚构离线能力状态；无案件读取，非法律审查或ChatGPT连接验收。"""
    return McpOfflineStatus()


def _fixture_anchors(fixture: McpOfflineFixture) -> tuple[str, str, list[dict[str, str]]]:
    filename, position, _ = FIXTURES[fixture]
    path = (_FIXTURE_DIRECTORY / filename).absolute()
    # Check nominal ancestry root-first before any content open. Resolving both
    # sides of a link would hide a linked registry root or an NTFS junction.
    for candidate in (*reversed(path.parents), path):
        metadata = candidate.lstat()
        if (stat.S_ISLNK(metadata.st_mode)
                or getattr(metadata, 'st_file_attributes', 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT):
            raise ValueError('unavailable registered fixture')
    if path.is_symlink() or not path.resolve().is_relative_to(_FIXTURE_DIRECTORY.resolve()):
        raise ValueError('unavailable registered fixture')
    with path.open('rb') as source:
        data = source.read(_MAX_FIXTURE_BYTES + 1)
    digest = sha256(data).hexdigest()
    if len(data) > _MAX_FIXTURE_BYTES or digest != EXPECTED_HASHES[fixture]:
        raise ValueError('unavailable registered fixture')
    # Only the hash-verified fixed DOCX is inspected; nothing is extracted to disk.
    with ZipFile(BytesIO(data)) as archive:
        info = archive.getinfo('word/document.xml')
        if info.file_size > _MAX_XML_BYTES:
            raise ValueError('unavailable registered fixture')
        document = ElementTree.fromstring(archive.read(info))
    paragraphs = [''.join(node.itertext()) for node in document.iter(f'{{{_W}}}p')]
    if not 1 <= len(paragraphs) <= 32 or any(not text.strip() for text in paragraphs):
        raise ValueError('unavailable registered fixture')
    anchors = [{'id': str(uuid5(NAMESPACE_URL, f'qx-synthetic:{fixture}:{index}')), 'quote': text}
               for index, text in enumerate(paragraphs)]
    return digest, position, anchors


def _request(arguments: McpOfflineExampleArguments, position: str,
             anchors: list[dict[str, str]]) -> ModelRequest:
    # An ephemeral synthetic context satisfies the existing codec's DTO contract.
    # These IDs are never queried, persisted, authorized or registered as a case.
    identifier = '11111111-1111-4111-8111-111111111111'
    context = ReviewContext.model_validate({
        'matter': {'id': identifier, 'client_ref': 'SYNTHETIC-OFFLINE',
            'title': '人工虚构离线协议示例', 'jurisdiction': 'CN',
            'contract_type': arguments.fixture, 'review_mode': 'pre_sign', 'position': position,
            'objectives': [], 'member_ids': [], 'status': 'intake',
            'active_fact_version': None, 'active_policy_version': None, 'gate_issues': []},
        'document_versions': [], 'fact_snapshot': {'version': 1, 'facts': [], 'sha256': '0' * 64},
        'position': position, 'rules': [], 'policy': {'client_ref': 'SYNTHETIC-OFFLINE',
            'version': 1, 'sha256': '0' * 64, 'preferences': [], 'approved_by': None,
            'approved_at': None}, 'authority_ids': [], 'allowed_scope': []})
    return ModelRequest(operation=arguments.operation, context=context,
        schema={'type': 'object', 'x-input': {'anchors': anchors}}, budget_approval_id=None,
        usage_limit=ModelUsageLimit(max_input_tokens=4096, max_output_tokens=_MAX_OUTPUT_TOKENS,
                                   max_cost='0', unit='USD'))


def deepseek_offline_example(fixture: McpOfflineFixture, operation: DeepSeekOperation,
                            model: DeepSeekModelId) -> McpOfflineExample:
    """固定登记虚构DOCX的纯codec示例；响应及token人工构造，非供应商或法律意见。"""
    try:
        arguments = McpOfflineExampleArguments(fixture=fixture, operation=operation, model=model)
    except ValueError:
        raise MCPError(code=INVALID_PARAMS, message=_REJECTED) from None
    try:
        digest, position, anchors = _fixture_anchors(arguments.fixture)
        request = _request(arguments, position, anchors)
        wire = build_chat_request(request, model=arguments.model, max_tokens=_MAX_OUTPUT_TOKENS)
        payload = {'synthetic': True, 'operation': arguments.operation, 'legal_opinion': False,
                   'example_kind': 'manual_protocol_example', 'note': '人工固定示例，无事实确认或法律结论。'}
        envelope = {'id': 'manual-synthetic-offline-example', 'object': 'chat.completion',
            'created': 1791024000, 'model': arguments.model,
            'choices': [{'index': 0, 'message': {'role': 'assistant',
                'content': json.dumps(payload, ensure_ascii=False)}, 'finish_reason': 'stop'}],
            'usage': {'prompt_tokens': 100, 'prompt_cache_hit_tokens': 40,
                'prompt_cache_miss_tokens': 60, 'completion_tokens': 20, 'total_tokens': 120}}
        reply = decode_chat_response(json.dumps(envelope, ensure_ascii=False), request,
                                     model=arguments.model, max_tokens=_MAX_OUTPUT_TOKENS)
        return McpOfflineExample(fixture=arguments.fixture, fixture_sha256=digest,
                                 request=wire, reply=reply)
    except Exception:
        # No exception detail, file path, caller content or SDK validation output.
        raise MCPError(code=INVALID_PARAMS, message=_UNAVAILABLE) from None


def _finite_tool_metadata(metadata, *, allow_thread_id=False) -> bool:
    """Local profile: bounded progress token and call-only canonical thread UUID.

    The low-level callbacks never pass metadata to a business handler or emit
    progress notifications. A thread UUID is inert host metadata, not identity
    or approval. String progress tokens and other MCP metadata stay closed.
    """
    if type(metadata) is not dict:
        return False
    allowed = {'progressToken', 'threadId'} if allow_thread_id else {'progressToken'}
    if metadata.keys() - allowed:
        return False
    if 'progressToken' in metadata:
        token = metadata['progressToken']
        if type(token) is not int or not 0 <= token <= 2**63 - 1:
            return False
    if 'threadId' in metadata:
        thread_id = metadata['threadId']
        if type(thread_id) is not str or len(thread_id) != 36:
            return False
        try:
            if str(UUID(thread_id)) != thread_id:
                return False
        except ValueError:
            return False
    return True


async def _offline_boundary(ctx, call_next):
    """Validate exact raw inbound arguments before any SDK coercion or handler."""
    if ctx.request_id is None:
        # Unknown notifications are dropped without passing caller names to SDK logs.
        if ctx.method == 'notifications/initialized':
            try:
                await call_next(ctx)
            except Exception:
                pass
        return None
    try:
        if ctx.method == 'tools/call':
            params = ctx.params
            if (type(params) is not dict or not {'name'} <= params.keys()
                    or params.keys() - {'name', 'arguments', '_meta'}
                    or ('_meta' in params and not _finite_tool_metadata(params['_meta'], allow_thread_id=True))):
                raise ValueError('rejected')
            name = params['name']
            arguments = params.get('arguments', {})
            if type(name) is not str or type(arguments) is not dict:
                raise ValueError('rejected')
            if name == 'workbench_status':
                if arguments:
                    raise ValueError('rejected')
            elif name == 'deepseek_offline_example':
                McpOfflineExampleArguments.model_validate(arguments)
            else:
                raise ValueError('rejected')
        elif ctx.method in ('tools/list', 'ping'):
            params = ctx.params
            if params is not None:
                if type(params) is not dict or params.keys() - {'_meta'}:
                    raise ValueError('rejected')
                if '_meta' in params:
                    metadata = params['_meta']
                    valid = (_finite_tool_metadata(metadata) if ctx.method == 'tools/list'
                             else type(metadata) is dict and not metadata)
                    if not valid:
                        raise ValueError('rejected')
        elif ctx.method != 'initialize':
            # Resource, prompt, subscriptions, HTTP and custom methods are not exposed.
            raise ValueError('rejected')
        result = await call_next(ctx)
        if isinstance(result, dict) and result.get('isError'):
            raise ValueError('rejected')
        return result
    except Exception:
        raise MCPError(code=INVALID_PARAMS, message=_REJECTED) from None


def create_server() -> MCPServer:
    """Build the finite offline surface; only STDIO is started by this module."""
    tools = []
    for function in (workbench_status, deepseek_offline_example):
        tool = Tool.from_function(function, structured_output=True,
            annotations=ToolAnnotations(read_only_hint=True, destructive_hint=False,
                                        idempotent_hint=True, open_world_hint=False))
        tool.parameters['additionalProperties'] = False
        tools.append(tool)
    server = MCPServer('qx-contract-offline', version='0.1.0', tools=tools,
        instructions='OFFLINE_ONLY：仅受控本机虚构示例；未连接ChatGPT，不作法律审查或正式签发。',
        log_level='ERROR')
    # The documented public list controls the complete chain. This tiny surface
    # supports no requestState or trace metadata, so neither SDK OTel nor its
    # request-state middleware is retained; no private manager is patched.
    server.middleware[:] = [_offline_boundary]
    return server


class _SanitizedWriteStream:
    """SDK message-stream adapter, after SDK parsing/dispatch and before encoding.

    SDK era classification precedes middleware. All protocol errors, including
    that layer's errors, therefore receive the same fixed body here. SDK STDIO
    remains responsible for the JSON parser, framing and stream lifecycle.
    """

    def __init__(self, stream):
        self._stream = stream

    async def send(self, item: SessionMessage) -> None:
        if isinstance(item.message, JSONRPCError):
            item = SessionMessage(JSONRPCError(jsonrpc='2.0', id=item.message.id,
                error=ErrorData(code=INVALID_PARAMS, message=_REJECTED)), metadata=item.metadata)
        await self._stream.send(item)

    async def aclose(self) -> None:
        await self._stream.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.aclose()


def _stdio_protocol_server(tools_server: MCPServer) -> Server:
    """Compose public SDK APIs; no access to MCPServer's private server/managers."""
    async def list_tools(ctx, params):
        return ListToolsResult(tools=await tools_server.list_tools())

    async def call_tool(ctx, params):
        return await tools_server.call_tool(params.name, params.arguments or {})

    protocol = Server(tools_server.name, version=tools_server.version,
        instructions=tools_server.instructions, on_list_tools=list_tools, on_call_tool=call_tool)
    # The low-level SDK also has default OTel: keep exactly the same validated
    # tool boundary as the high-level registry, with neither default OTel chain.
    protocol.middleware[:] = tools_server.middleware
    return protocol


async def _run_stdio() -> None:
    protocol = _stdio_protocol_server(create_server())
    async with stdio_server() as (read_stream, write_stream):
        await protocol.run(read_stream, _SanitizedWriteStream(write_stream),
                           protocol.create_initialization_options())


def main() -> None:
    anyio.run(_run_stdio)


if __name__ == '__main__':
    main()
