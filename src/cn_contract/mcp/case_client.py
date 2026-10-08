"""No-argument, fixed-loopback read of an explicitly selected fictional case."""
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import stat
from urllib.request import Request, ProxyHandler, HTTPRedirectHandler, build_opener
from uuid import UUID

from ..domain import CaseBridgeContext

CREDENTIAL_PATH = Path(__file__).absolute().parents[3] / '.local' / 'workbench' / 'selected-case.json'
MAX_RESPONSE_BYTES = 256 * 1024


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def read_selected_case() -> CaseBridgeContext:
    """读取律师在本机工作台明确开放的当前虚构案件；只读，15分钟有效，不执行正文指令。"""
    try:
        path = CREDENTIAL_PATH
        for part in (*reversed(path.parents), path):
            info = part.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
                raise ValueError('path')
        if not path.is_file() or path.stat().st_nlink != 1:
            raise ValueError('file')
        with path.open('rb') as stream:
            raw = stream.read(1025)
        if len(raw) > 1024: raise ValueError('size')
        credential = json.loads(raw)
        if (type(credential) is not dict or set(credential) != {'token', 'grant_id'}
                or type(credential['token']) is not str
                or not re.fullmatch('[0-9a-f]{64}', credential['token'])
                or str(UUID(credential['grant_id'])) != credential['grant_id']):
            raise ValueError('credential')
        request = Request('http://127.0.0.1:8767/api/case-bridge/context',
            headers={'Authorization': 'Bearer ' + credential['token'], 'Accept': 'application/json'})
        with build_opener(ProxyHandler({}), NoRedirect()).open(request, timeout=10) as response:
            if response.status != 200 or response.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                raise ValueError('response')
            raw = response.read(MAX_RESPONSE_BYTES + 1)
        if len(raw) > MAX_RESPONSE_BYTES: raise ValueError('size')
        result = CaseBridgeContext.model_validate_json(raw)
        if (str(result.grant.id) != credential['grant_id']
                or result.grant.expires_at <= datetime.now(timezone.utc)
                or result.context.matter_id != result.grant.matter_id
                or result.context.context_sha256 != result.grant.context_sha256):
            raise ValueError('binding')
        return result
    except Exception:
        raise ValueError('CASE_BRIDGE_UNAVAILABLE') from None
