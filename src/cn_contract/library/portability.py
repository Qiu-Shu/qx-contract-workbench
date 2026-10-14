"""Portable inventory, with full asset verification and no original path aliases."""
from datetime import datetime, timezone
from pathlib import Path

from ..domain import LibrarySource
from .assets import asset_path, file_hash
from .catalog import canonical, checked_path, connection, writer_lock
from .index import current_generation, validate_generation


def _verified_inventory(root):
    sources = []
    checked = set()
    with connection(root) as db:
        for row in db.execute('SELECT source_json FROM sources ORDER BY source_id'):
            source = LibrarySource.model_validate_json(row[0])
            path = asset_path(root, source)
            if source.sha256 not in checked and file_hash(path) != source.sha256:
                raise ValueError('ASSET_HASH_MISMATCH')
            checked.add(source.sha256)
            sources.append(source.model_dump(mode='json', exclude={'aliases'}))
        records = db.execute('SELECT count(*) FROM records').fetchone()[0]
        fragments = db.execute('SELECT count(*) FROM fragments').fetchone()[0]
        reviews = [dict(row) for row in db.execute('SELECT seq,event_hash,previous_hash FROM reviews ORDER BY seq')]
        states = [dict(row) for row in db.execute('SELECT source_id,next_ordinal,next_byte,state FROM import_states ORDER BY source_id')]
    current = current_generation(root)
    if current:
        validate_generation(root, current['generation_id'])
    return {'format': 'qx-legal-library-manifest', 'version': 1,
            'created_at': datetime.now(timezone.utc).isoformat(), 'sources': sources,
            'records': records, 'fragments': fragments, 'reviews': reviews, 'import_states': states,
            'generation': current, 'scope': 'inventory_only_not_a_data_archive'}


def export_manifest(root, destination):
    destination = checked_path(destination)
    if destination.exists():
        raise FileExistsError('MANIFEST_DESTINATION_EXISTS')
    with writer_lock(root) as root:
        manifest = _verified_inventory(root)
        with destination.open('x', encoding='utf-8') as stream:
            stream.write(canonical(manifest))
    return destination


def relocate_library(root):
    """Validate a copied library; never move, delete or rebase original aliases."""
    with writer_lock(root) as root:
        manifest = _verified_inventory(root)
    return {'ok': True, 'sources': len(manifest['sources']), 'records': manifest['records'],
            'generation_id': manifest['generation']['generation_id'] if manifest['generation'] else None}
