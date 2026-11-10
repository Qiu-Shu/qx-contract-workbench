"""T03 document service; all entry points require a configured authorized Session."""
from .ingest import ingest, parse_document, resolve_anchor

__all__ = ['ingest', 'parse_document', 'resolve_anchor']
