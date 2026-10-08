"""Bridge client cannot select cases or route through external infrastructure."""
import importlib
import importlib.util
import json
from pathlib import Path
from uuid import uuid4

import pytest


def implementation():
    assert importlib.util.find_spec('cn_contract.mcp.case_client'), 'selected case MCP client is missing'
    return importlib.import_module('cn_contract.mcp.case_client')


def credential(tmp_path, monkeypatch, payload=None):
    module = implementation()
    path = tmp_path / 'selected-case.json'
    path.write_text(json.dumps(payload or {'token': 'a' * 64, 'grant_id': str(uuid4())}), encoding='utf-8')
    monkeypatch.setattr(module, 'CREDENTIAL_PATH', path)
    return module, path


def test_missing_selection_is_not_network_request(tmp_path, monkeypatch):
    module = implementation()
    monkeypatch.setattr(module, 'CREDENTIAL_PATH', tmp_path / 'missing')
    monkeypatch.setattr(module, 'build_opener', lambda *_: pytest.fail('must not connect'))
    with pytest.raises(ValueError, match='CASE_BRIDGE_UNAVAILABLE'): module.read_selected_case()


@pytest.mark.parametrize('payload', [{'token': 'x', 'grant_id': str(uuid4())},
    {'token': 'a'*64, 'grant_id': str(uuid4()), 'url': 'https://untrusted.invalid'},
    {'token': 'a'*64, 'grant_id': '../other'}, {'token': 'a'*64+'\r\nSecret: x', 'grant_id': str(uuid4())}])
def test_invalid_credential_never_connects(tmp_path, monkeypatch, payload):
    module, _ = credential(tmp_path, monkeypatch, payload)
    monkeypatch.setattr(module, 'build_opener', lambda *_: pytest.fail('must not connect'))
    with pytest.raises(ValueError, match='CASE_BRIDGE_UNAVAILABLE'): module.read_selected_case()


@pytest.mark.parametrize('content', [b'{}', b'x' * (256 * 1024 + 1), b'private material is not JSON'], ids=['schema', 'oversize', 'non-json'])
def test_fixed_route_no_proxy_redirect_and_sanitized_response(tmp_path, monkeypatch, content):
    module, _ = credential(tmp_path, monkeypatch)
    class Reply:
        status = 200
        headers = {'Content-Type': 'application/json'}
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self, size):
            assert size == 256 * 1024 + 1
            return content
    class Opener:
        def open(self, request, timeout):
            assert request.full_url == 'http://127.0.0.1:8767/api/case-bridge/context'
            assert request.get_header('Authorization') == 'Bearer ' + 'a'*64
            assert request.data is None and timeout <= 10
            return Reply()
    def opener(*handlers):
        from urllib.request import ProxyHandler, HTTPRedirectHandler
        proxy = next(h for h in handlers if isinstance(h, ProxyHandler))
        assert proxy.proxies == {}
        redirect = next(h for h in handlers if isinstance(h, HTTPRedirectHandler))
        assert redirect.redirect_request(None, None, 302, '', {}, 'https://untrusted.invalid') is None
        return Opener()
    monkeypatch.setattr(module, 'build_opener', opener)
    with pytest.raises(ValueError, match='^CASE_BRIDGE_UNAVAILABLE$'): module.read_selected_case()


def test_credential_hardlink_rejected(tmp_path, monkeypatch):
    module, path = credential(tmp_path, monkeypatch)
    (tmp_path / 'alias').hardlink_to(path)
    monkeypatch.setattr(module, 'build_opener', lambda *_: pytest.fail('must not connect'))
    with pytest.raises(ValueError, match='CASE_BRIDGE_UNAVAILABLE'): module.read_selected_case()


@pytest.mark.anyio
async def test_mcp_new_tool_is_no_argument_read_only():
    from cn_contract.mcp.offline_server import create_server
    server = create_server()
    selected = [tool for tool in await server.list_tools() if tool.name == 'read_selected_case']
    assert len(selected) == 1, 'MCP selected-case tool is missing'
    schema = selected[0].model_dump(by_alias=True)
    assert schema['inputSchema']['properties'] == {}
    assert schema['inputSchema']['additionalProperties'] is False
    assert schema['annotations']['readOnlyHint'] is True
