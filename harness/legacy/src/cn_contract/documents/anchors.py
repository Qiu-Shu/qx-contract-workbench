"""Exact, version-bound extraction anchors. No text normalization or fuzzy search."""
import hashlib
from uuid import UUID, uuid5

from ..domain import Anchor, AnchorKind


def make_anchor(version, part, path, quote, kind=AnchorKind.BODY_PARAGRAPH, *,
                table=None, row=None, cell=None, page=None, bbox=None):
    version_id = version if isinstance(version, UUID) else version.id
    return Anchor(id=uuid5(version_id, f'{part}:{path}'), document_version_id=version_id,
                  part_name=part, element_id=path, kind=kind, quote=quote,
                  quote_sha256=hashlib.sha256(quote.encode('utf-8')).hexdigest(),
                  start=0, end=len(quote), table=table, row=row, cell=cell, page=page, bbox=bbox)
