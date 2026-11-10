"""Small-file snapshots restore into a new, read-only workspace."""
import hashlib
import json
from pathlib import Path
import sqlite3
from contextlib import closing
from tempfile import TemporaryDirectory
from zipfile import ZipFile,ZIP_DEFLATED

from .store import safe,encoded


def backup(store,destination):
    destination=Path(destination)
    if destination.exists(): raise ValueError('DESTINATION_EXISTS')
    with TemporaryDirectory(dir=store.internal) as directory:
        snapshot=Path(directory)/'media.sqlite'
        with store.db() as source,closing(sqlite3.connect(snapshot)) as target: source.backup(target)
        files={'.qx-media/media.sqlite':snapshot.read_bytes(),
               '.qx-media/host-identity.json':encoded(store.actor.model_dump()).encode()}
        with closing(sqlite3.connect(snapshot)) as db:
            for name,sha in db.execute('SELECT relative_name,sha256 FROM media_exports'):
                path=safe(store.root,store.internal/'exports'/name); data=path.read_bytes()
                if hashlib.sha256(data).hexdigest()!=sha: raise ValueError('EXPORT_INTEGRITY')
                files['.qx-media/exports/'+name]=data
        if sum(map(len,files.values()))>100*1024*1024: raise ValueError('BACKUP_TOO_LARGE')
        manifest={name:hashlib.sha256(data).hexdigest() for name,data in files.items()}
        with ZipFile(destination,'x',ZIP_DEFLATED) as archive:
            for name,data in files.items(): archive.writestr(name,data)
            archive.writestr('manifest.json',encoded(manifest))
    return destination


def restore_readonly(archive_path,destination):
    destination=Path(destination).absolute()
    if destination.exists(): raise ValueError('DESTINATION_EXISTS')
    with ZipFile(archive_path) as archive:
        if len(archive.namelist())!=len(set(archive.namelist())) or sum(i.file_size for i in archive.infolist())>100*1024*1024:
            raise ValueError('INVALID_BACKUP')
        manifest=json.loads(archive.read('manifest.json'))
        if set(archive.namelist())!=set(manifest)|{'manifest.json'} or not {'.qx-media/media.sqlite','.qx-media/host-identity.json'}<=set(manifest):
            raise ValueError('INVALID_BACKUP')
        for name,sha in manifest.items():
            parts=Path(name).parts
            if name not in ('.qx-media/media.sqlite','.qx-media/host-identity.json') and not (len(parts)==3 and parts[:2]==('.qx-media','exports') and parts[2].endswith('.zip')):
                raise ValueError('INVALID_BACKUP_PATH')
            if any(p in ('.','..') for p in parts) or ':' in name or '\\' in name: raise ValueError('INVALID_BACKUP_PATH')
            if hashlib.sha256(archive.read(name)).hexdigest()!=sha: raise ValueError('BACKUP_INTEGRITY')
        destination.mkdir()
        for name in manifest:
            path=destination/name; path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(archive.read(name))
        (destination/'.qx-media/RESTORED_READ_ONLY').write_text('Restored snapshot; no approval or external job may be resumed.',encoding='utf-8')
    return destination
