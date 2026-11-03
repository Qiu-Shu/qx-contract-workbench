"""只读知识服务客户端（服务端专用）。

浏览器永远拿不到服务凭据：凭据只在本进程读环境变量，请求由后端发起，
前端只跟工作台自己的 `/api/knowledge/*` 说话。
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

from ... import domain as d


class KnowledgeServiceError(Exception):
    """稳定错误码，供 HTTP 层映射；不携带上游原始报文，避免把服务内部细节带到界面。"""

    def __init__(self, code: str, message: str = ''):
        super().__init__(code)
        self.code = code
        self.message = message


STATUS_BY_CODE = {
    'KB_SERVICE_NOT_CONFIGURED': 503,
    'KB_SERVICE_UNAVAILABLE': 503,
    'KB_SERVICE_DEGRADED': 503,
    'KB_SERVICE_UNAUTHORIZED': 502,
    'KNOWLEDGE_QUERY_INVALID': 422,
    'KNOWLEDGE_ID_INVALID': 422,
    'KNOWLEDGE_SOURCE_NOT_FOUND': 404,
    'KNOWLEDGE_SOURCE_STALE': 409,
    'KNOWLEDGE_RANGE_INVALID': 409,
    'KNOWLEDGE_CONTRACT_INVALID': 502,
}

MESSAGES = {
    'KB_SERVICE_NOT_CONFIGURED': '知识服务未配置，当前试用本地资料库或普通对话。',
    'KB_SERVICE_UNAVAILABLE': '知识服务不可达或超时，请稍后重试；已输入的检索词会保留。',
    # 与"没有命中"必须分开说：库结构/IO 出问题时给出空结果，等于把故障报成"查无此文"。
    'KB_SERVICE_DEGRADED': '知识服务的数据源出现故障（库结构或读取异常），本次没有拿到结果；'
                           '这不等于"没有命中"，请稍后重试或联系管理员。',
    'KB_SERVICE_UNAUTHORIZED': '知识服务凭据无效，请联系管理员检查配置。',
    'KNOWLEDGE_QUERY_INVALID': '检索词不合法：请使用 1–200 字、不含控制字符的普通文本。',
    'KNOWLEDGE_ID_INVALID': '来源标识不正确，请从检索结果打开。',
    'KNOWLEDGE_SOURCE_NOT_FOUND': '未找到这条来源，可能不在已登记范围内。',
    'KNOWLEDGE_SOURCE_STALE': '来源版本已变化（原文哈希不符），已阻断引用，请重新检索。',
    'KNOWLEDGE_RANGE_INVALID': '请求的原文范围超出该来源，已拒绝越界读取。',
    'KNOWLEDGE_CONTRACT_INVALID': '知识服务返回的数据不符合约定，已拒绝展示。',
}

# 上游错误码 → 工作台错误码
_UPSTREAM = {
    'UNAUTHORIZED': 'KB_SERVICE_UNAUTHORIZED',
    'QUERY_INVALID': 'KNOWLEDGE_QUERY_INVALID',
    'BAD_REQUEST': 'KNOWLEDGE_QUERY_INVALID',
    'SOURCE_NOT_FOUND': 'KNOWLEDGE_SOURCE_NOT_FOUND',
    'SOURCE_STALE': 'KNOWLEDGE_SOURCE_STALE',
    'RANGE_INVALID': 'KNOWLEDGE_RANGE_INVALID',
    'SERVICE_DEGRADED': 'KB_SERVICE_DEGRADED',
}


@dataclass(frozen=True)
class KnowledgeServiceConfig:
    url: str
    token: str
    timeout: float = 5.0

    @classmethod
    def from_env(cls, environ=None):
        environ = os.environ if environ is None else environ
        url = (environ.get('KB_SERVICE_URL') or '').strip().rstrip('/')
        token = environ.get('KB_SERVICE_TOKEN') or ''
        if not url:
            return None
        parsed = urllib.parse.urlsplit(url)
        # 只接受本机回环：服务本身也绑 127.0.0.1，配置成远端地址直接拒绝而不是试着连
        if parsed.scheme != 'http' or parsed.hostname not in ('127.0.0.1', 'localhost', '::1'):
            raise ValueError('KB_SERVICE_URL 必须是本机回环 http 地址')
        if len(token) < 16:
            raise ValueError('KB_SERVICE_TOKEN 缺失或短于 16 字符')
        try:
            timeout = float(environ.get('KB_SERVICE_TIMEOUT', '5'))
        except ValueError:
            timeout = 5.0
        return cls(url=url, token=token, timeout=min(max(timeout, 0.5), 30.0))


class KnowledgeServiceClient:
    def __init__(self, config: KnowledgeServiceConfig):
        self.config = config
        # 本机回环请求绝不能走环境里的 http_proxy：一旦机器设了代理而没有
        # no_proxy=127.0.0.1，urllib 会把 localhost 请求交给代理，表现为
        # "服务明明在监听却不可达"。这里显式清空代理表。
        self._opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    # ---- 传输 -------------------------------------------------------------
    def _call(self, method: str, path: str, payload: dict | None = None) -> dict:
        data = json.dumps(payload).encode('utf-8') if payload is not None else None
        request = urllib.request.Request(self.config.url + path, data=data, method=method)
        request.add_header('X-KB-Token', self.config.token)
        if data is not None:
            request.add_header('Content-Type', 'application/json')
        try:
            with self._opener.open(request, timeout=self.config.timeout) as response:
                raw = response.read()
        except urllib.error.HTTPError as error:
            raw = error.read()
            try:
                body = json.loads(raw.decode('utf-8'))
            except (ValueError, UnicodeDecodeError):
                body = {}
            code = _UPSTREAM.get(body.get('code', ''), 'KB_SERVICE_UNAVAILABLE')
            raise KnowledgeServiceError(code) from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise KnowledgeServiceError('KB_SERVICE_UNAVAILABLE') from None
        try:
            return json.loads(raw.decode('utf-8'))
        except (ValueError, UnicodeDecodeError):
            raise KnowledgeServiceError('KNOWLEDGE_CONTRACT_INVALID') from None

    # ---- 能力 -------------------------------------------------------------
    def status(self) -> dict:
        return self._call('GET', '/v1/status')

    def search(self, request: d.KnowledgeSearchRequest) -> d.KnowledgeSearchPage:
        body = self._call('POST', '/v1/search', {
            'query': request.query, 'kinds': list(request.kinds), 'limit': request.limit})
        try:
            return d.KnowledgeSearchPage.model_validate(body)
        except ValueError:
            raise KnowledgeServiceError('KNOWLEDGE_CONTRACT_INVALID') from None

    def source(self, source_id: str, start: int | None = None, end: int | None = None,
               version: str | None = None) -> d.KnowledgeSourceView:
        """回读来源。

        `version` 是检索那一刻看到的 `source_version.sha256`。带上它，服务端会把
        "预期版本"和"本次实际读到的登记版本"比一遍——只比 source_id 挡不住
        "原文换了、重新登记了，但 ID 一个字都没变"这种情况。
        """
        parts = []
        if start is not None:
            parts.append(f'start={int(start)}')
        if end is not None:
            parts.append(f'end={int(end)}')
        if version is not None:
            parts.append('version=' + urllib.parse.quote(str(version), safe=''))
        query = ('?' + '&'.join(parts)) if parts else ''
        body = self._call('GET', '/v1/sources/' + urllib.parse.quote(source_id, safe='') + query)
        try:
            return d.KnowledgeSourceView.model_validate(body)
        except ValueError:
            raise KnowledgeServiceError('KNOWLEDGE_CONTRACT_INVALID') from None
