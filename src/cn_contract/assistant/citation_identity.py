"""Content identity for a citation snapshot; this does not verify its legal source."""
from ..library.catalog import canonical, digest


def citation_identity(fields):
    payload = {name: value for name, value in fields.items() if name != 'citation_id'}
    return digest(canonical(['qx-library-citation-v1', payload]).encode('utf-8'))
