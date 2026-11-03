"""Canonical library ledger snapshots, shared by execution and backup validation."""
import hashlib
import json
import re

from .. import domain as d
from ..config import canonical_json
from .citation_identity import citation_identity

_SHA256 = re.compile(r'[0-9a-f]{64}')


def _check_knowledge_citation(value):
    """知识服务引用的自洽约束：片段哈希、版本哈希、字符窗口。

    这一层不判断法律效力，也不重算原文——它只回答"这条引用描述的是它自己吗"。
    与 `CitationRef` 的 `citation_id` 自洽同等强度：少一项就等于给篡改留了口子。
    """
    snippet, location = value.snippet, value.location
    if hashlib.sha256(snippet.text.encode('utf-8')).hexdigest() != snippet.sha256:
        raise ValueError('LIBRARY_RECORD_INVALID')
    version = value.source_version.get('sha256')
    if not isinstance(version, str) or not _SHA256.fullmatch(version):
        raise ValueError('LIBRARY_RECORD_INVALID')
    if not location.char_start <= snippet.start <= snippet.end <= location.char_end:
        raise ValueError('LIBRARY_RECORD_INVALID')
    if snippet.match_start is not None and not (
            snippet.start <= snippet.match_start <= snippet.match_end <= snippet.end):
        raise ValueError('LIBRARY_RECORD_INVALID')


def _check_citations(value):
    if isinstance(value, d.CitationRef):
        if citation_identity(value.model_dump(mode='json')) != value.citation_id:
            raise ValueError('LIBRARY_RECORD_INVALID')
    elif isinstance(value, d.KnowledgeCitation):
        _check_knowledge_citation(value)
        for name in type(value).model_fields:
            _check_citations(getattr(value, name))
    elif isinstance(value, d.DomainModel):
        for name in type(value).model_fields:
            _check_citations(getattr(value, name))
    elif isinstance(value, dict):
        for item in value.values():
            _check_citations(item)
    elif isinstance(value, (tuple, list)):
        for item in value:
            _check_citations(item)


def encoded(value):
    checked = type(value).model_validate(value.model_dump(mode='python', warnings=False))
    _check_citations(checked)
    return canonical_json(checked.model_dump(mode='json'))


def sha(raw):
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def model(kind, raw):
    try:
        value = kind.model_validate(json.loads(raw))
        _check_citations(value)
        # 模型会随着能力增长新增可选字段（knowledge_page / knowledge_citation）。
        # 历史记录里当然没有这些键，若只按"全字段规范化"比较，旧回执会被判成
        # 非规范、进而让整库完整性校验和备份校验一起失败——记录没坏，是模型长大了。
        # 因此再接受一种等价形式：只规范化原文里出现过的字段。model_validate 之后
        # 未出现的键恰好是 unset，exclude_unset 精确还原原文的键集合。
        if raw not in (encoded(value),
                       canonical_json(value.model_dump(mode='json', exclude_unset=True))):
            raise ValueError('noncanonical record')
        return value
    except (ValueError, TypeError, RecursionError):
        raise ValueError('LIBRARY_RECORD_INVALID') from None


def result_citations(result):
    if result.page is not None:
        return result.page.citations
    if result.knowledge_page is not None:
        # 知识服务按来源分组（法条在前、案例在后），保存顺序必须与展示顺序一致，
        # 否则前端拿 citation_ids[index] 会配错引用。
        groups = result.knowledge_page.groups
        return (*groups.get('law', ()), *groups.get('case', ()))
    return (result.citation,)


def citation_body(result):
    """回执里保存的那条引用体：本地资料库放在 citation，只读知识服务放在 knowledge_citation。

    两种来源各有各的契约，互不冒充，所以这里按实际存在的那个取值，不做类型转换。
    检索结果模型只有 `citation` 字段，没有 `knowledge_citation`——用 getattr 取值，
    不为兼容而在两种模型之间加字段。
    """
    body = getattr(result, 'citation', None)
    return body if body is not None else getattr(result, 'knowledge_citation', None)


def receipt_view(row):
    try:
        if sha(row['result_json']) != row['result_sha256']:
            raise ValueError('result hash mismatch')
        return d.LibraryHandlerReceiptView(id=row['id'], run_id=row['run_id'],
            event_seq=row['event_seq'], handler_id=row['handler_id'], handler_version=row['handler_version'],
            request=model(d.LibraryHandlerRequest, row['request_json']),
            scope=model(d.ScopeSnapshot, row['scope_json']),
            result=model(d.LibraryHandlerResult, row['result_json']), created_at=row['created_at'])
    except (ValueError, TypeError, KeyError):
        raise ValueError('LIBRARY_RECORD_INVALID') from None
