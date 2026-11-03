"""只读知识服务在「显式检索」路径上的适配器。

为什么要单独一层
----------------
本地资料库的引用是 `CitationRef`：`kind` 只认 `case_csv` / `law_markdown`，七个字段
全是 64 位哈希，还要满足 `citation_identity()` 的摘要自洽。知识服务返回的是
`KnowledgeCitation`：法条带原文哈希与行区间、案例带锚点区间，根本没有 `record_id`。
把后者塞进前者只能靠编造文件类型和假哈希——那样引用就没法回查原文了。

所以这一层**只做来源与错误码的翻译，不做模型互转**：入参仍是既有的
`AssistantLibraryQuery`（同一套会话权限、同一套关键词长度约束），出参是知识服务
自己的 `KnowledgeSearchPage`，两者在 domain 里各有各的位置。
"""
from __future__ import annotations

from ... import domain as d
from .kb_readonly import KnowledgeServiceClient, KnowledgeServiceError

# 上游错误 → 显式检索路径已有的错误码集合（research._ERRORS 白名单内的那些）
_CODES = {
    'KB_SERVICE_NOT_CONFIGURED': 'LIBRARY_NOT_CONFIGURED',
    'KB_SERVICE_UNAVAILABLE': 'LIBRARY_SOURCE_UNAVAILABLE',
    'KB_SERVICE_DEGRADED': 'LIBRARY_SOURCE_UNAVAILABLE',
    'KB_SERVICE_UNAUTHORIZED': 'LIBRARY_SOURCE_UNAVAILABLE',
    'KNOWLEDGE_QUERY_INVALID': 'LIBRARY_QUERY_INVALID',
    'KNOWLEDGE_ID_INVALID': 'LIBRARY_QUERY_INVALID',
    'KNOWLEDGE_SOURCE_NOT_FOUND': 'LIBRARY_SOURCE_UNAVAILABLE',
    'KNOWLEDGE_SOURCE_STALE': 'LIBRARY_GENERATION_STALE',
    'KNOWLEDGE_RANGE_INVALID': 'LIBRARY_CITATION_MISMATCH',
    'KNOWLEDGE_CONTRACT_INVALID': 'LIBRARY_SOURCE_UNAVAILABLE',
}


class KnowledgeLibraryAdapter:
    """把知识服务包装成 `execute_tool` 能调用的形状（只有一个 search）。"""

    # 对话内的引用上限：`LibraryHandlerResult.citation_ids` 最多 8 个。
    # 知识服务是按来源各给 `limit` 条（法条 5 + 案例 5 = 10），超出时必须显式截断，
    # 并把"截断了多少"写进 degraded —— 静默丢结果比截断更糟。
    MAX_CITATIONS = 8

    def __init__(self, client: KnowledgeServiceClient):
        self.client = client

    def search(self, query) -> d.KnowledgeSearchPage:
        try:
            query = d.AssistantLibraryQuery.model_validate(
                query.model_dump(mode='python', warnings=False)
                if isinstance(query, d.AssistantLibraryQuery) else query)
        except (ValueError, TypeError):
            raise ValueError('LIBRARY_QUERY_INVALID') from None
        text = (query.text or '').strip()
        if not text:
            # 只给法院/案号这类筛选条件时，知识服务没有对应的检索面；明确拒绝，
            # 不能退化成"空关键词检索"再把 0 命中报成"库里没有"。
            raise ValueError('LIBRARY_QUERY_INVALID')
        try:
            request = d.KnowledgeSearchRequest(query=text, kinds=('law', 'case'), limit=min(query.limit, 8))
        except (ValueError, TypeError):
            raise ValueError('LIBRARY_QUERY_INVALID') from None
        try:
            return self._bounded(self.client.search(request))
        except KnowledgeServiceError as error:
            raise ValueError(_CODES.get(error.code, 'LIBRARY_SOURCE_UNAVAILABLE')) from None

    def _bounded(self, page: d.KnowledgeSearchPage) -> d.KnowledgeSearchPage:
        groups = page.groups
        law = list(groups.get('law', ()))
        case = list(groups.get('case', ()))
        total = len(law) + len(case)
        if total <= self.MAX_CITATIONS:
            return page
        keep_law = law[:self.MAX_CITATIONS]
        keep_case = case[:max(0, self.MAX_CITATIONS - len(keep_law))]
        dropped = total - len(keep_law) - len(keep_case)
        data = page.model_dump(mode='python', warnings=False)
        data['groups'] = {'law': keep_law, 'case': keep_case}
        data['degraded'] = tuple(page.degraded) + ({
            'kind': 'all', 'code': 'CHAT_TRUNCATED',
            'message': f'共 {total} 条命中，对话内最多保存 {self.MAX_CITATIONS} 条引用，'
                       f'已截断 {dropped} 条；完整结果请在知识服务检索页查看。'},)
        return d.KnowledgeSearchPage.model_validate(data)
