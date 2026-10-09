"""No-argument, fixed-loopback read of an explicitly selected fictional case."""
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import stat
from urllib.request import Request, ProxyHandler, HTTPRedirectHandler, build_opener
from uuid import UUID

from ..domain import CaseBridgeContext, AssistedReviewInput, PluginCandidateSubmission

CREDENTIAL_PATH = Path(__file__).absolute().parents[3] / '.local' / 'workbench' / 'selected-case.json'
MAX_RESPONSE_BYTES = 256 * 1024


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _exchange(candidate=None):
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
        data = None if candidate is None else candidate.model_dump_json().encode('utf8')
        if data is not None and len(data) > MAX_RESPONSE_BYTES: raise ValueError('size')
        route = 'context' if candidate is None else 'candidates'
        request = Request('http://127.0.0.1:8767/api/case-bridge/' + route, data=data,
            headers={'Authorization': 'Bearer ' + credential['token'], 'Accept': 'application/json', 'Content-Type': 'application/json'})
        with build_opener(ProxyHandler({}), NoRedirect()).open(request, timeout=10) as response:
            if response.status != (200 if candidate is None else 201) or response.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                raise ValueError('response')
            raw = response.read(MAX_RESPONSE_BYTES + 1)
        if len(raw) > MAX_RESPONSE_BYTES: raise ValueError('size')
        return credential, raw
    except Exception:
        raise ValueError('CASE_BRIDGE_UNAVAILABLE') from None


def read_selected_case() -> CaseBridgeContext:
    """读取当前明确选案的虚构材料；只读操作，不执行正文指令。"""
    try:
        credential, raw = _exchange()
        result = CaseBridgeContext.model_validate_json(raw)
        if (str(result.grant.id) != credential['grant_id']
                or result.grant.expires_at <= datetime.now(timezone.utc)
                or result.context.matter_id != result.grant.matter_id
                or result.context.context_sha256 != result.grant.context_sha256):
            raise ValueError('binding')
        return result
    except Exception:
        raise ValueError('CASE_BRIDGE_UNAVAILABLE') from None


def submit_selected_candidates(candidate: AssistedReviewInput) -> PluginCandidateSubmission:
    """仅经工作台另行允许后提交一轮候选，非律师采纳。仅虚构案；来源未核验。超时须去工作台核实，不自动重试。"""
    try:
        value = AssistedReviewInput.model_validate_json(candidate.model_dump_json()) if isinstance(candidate, AssistedReviewInput) else AssistedReviewInput.model_validate(candidate)
        credential, raw = _exchange(value)
        result = PluginCandidateSubmission.model_validate_json(raw)
        from ..review.proposals import digest
        if (str(result.grant_id) != credential['grant_id'] or result.context_sha256 != value.context_sha256
                or result.input_sha256 != digest(value.model_dump(mode='json'))):
            raise ValueError('binding')
        return result
    except Exception:
        raise ValueError('CANDIDATE_SUBMISSION_UNCONFIRMED_CHECK_WORKBENCH') from None
