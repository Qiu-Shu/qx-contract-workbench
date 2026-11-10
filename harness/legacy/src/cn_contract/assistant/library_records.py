"""Canonical library ledger snapshots, shared by execution and backup validation."""
import hashlib
import json

from .. import domain as d
from ..config import canonical_json
from .citation_identity import citation_identity


def _check_citations(value):
    if isinstance(value, d.CitationRef):
        if citation_identity(value.model_dump(mode='json')) != value.citation_id:
            raise ValueError('LIBRARY_RECORD_INVALID')
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
        if encoded(value) != raw:
            raise ValueError('noncanonical record')
        return value
    except (ValueError, TypeError, RecursionError):
        raise ValueError('LIBRARY_RECORD_INVALID') from None


def result_citations(result):
    return result.page.citations if result.page is not None else (result.citation,)


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
