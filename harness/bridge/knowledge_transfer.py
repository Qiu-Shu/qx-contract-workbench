"""Versioned ZIP transfer of validated records, never a replacement SQLite database.

Archives are integrity checked, not signed: import only backups from a trusted owner.
Handled failures roll back; an OS crash can leave unregistered UUID directories, which
later imports refuse to overwrite. Originals and the database are separate resources.
"""
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import struct
import tempfile
from uuid import UUID
import zipfile

from store import SUPPORTED

MAX_FILE_BYTES = 512 * 1024 * 1024
MAX_TOTAL_BYTES = 2 * 1024 * 1024 * 1024
MAX_MANIFEST_BYTES = 64 * 1024 * 1024
MAX_ARCHIVE_BYTES = MAX_TOTAL_BYTES + 16 * 1024 * 1024
MAX_DOCUMENTS = 10000
MAX_CHUNKS = 200000
MAX_CHUNK_TEXT = 16000
BLOCK = 1024 * 1024
STATES = {'pending', 'indexing', 'partial', 'ready', 'no_text', 'error'}
DOC_FIELDS = {'id', 'path', 'title', 'category', 'sha256', 'created_at', 'state', 'error', 'archived'}
MATERIAL_FIELDS = {'path', 'size', 'mtime', 'sha256', 'status', 'page_count', 'warnings'}
CHUNK_FIELDS = {'path', 'ordinal', 'page', 'location', 'text'}


def _require(condition, message='备份记录格式无效。'):
    if not condition:
        raise ValueError(message)


def _text(value, maximum, minimum=0):
    _require(isinstance(value, str) and minimum <= len(value) <= maximum and '\0' not in value)


def _integer(value, minimum=0, maximum=2**63-1):
    _require(type(value) is int and minimum <= value <= maximum)


def _keys(value, expected):
    _require(isinstance(value, dict) and set(value) == expected)


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        _require(key not in result, '备份 JSON 含重复字段。')
        result[key] = value
    return result


def _json(data):
    try:
        return json.loads(data, object_pairs_hook=_pairs,
                          parse_constant=lambda _: _require(False))
    except (UnicodeError, json.JSONDecodeError, RecursionError):
        raise ValueError('备份 JSON 无效。') from None


def _filename(value):
    _text(value, 180, 1)
    _require(not re.search(r'[<>:"/\\|?*\x00-\x1f]', value)
             and not value.endswith(('.', ' '))
             and not re.match(r'^(con|prn|aux|nul|com[0-9¹²³]|lpt[0-9¹²³])(?:\.|$)', value, re.I),
             '备份中的原件文件名无效。')
    _require(Path(value).suffix.lower() in SUPPORTED, '备份含不支持的原件格式。')


def _validate(manifest):
    _keys(manifest, {'format', 'version', 'documents'})
    _require(manifest['format'] == 'qx-knowledge' and type(manifest['version']) is int
             and manifest['version'] == 1, '不支持此知识库备份版本。')
    records = manifest['documents']
    _require(isinstance(records, list) and len(records) <= MAX_DOCUMENTS,
             f'备份资料数量上限为 {MAX_DOCUMENTS} 份。')
    ids, members, chunk_count, total = set(), set(), 0, 0
    for record in records:
        _keys(record, {'document', 'material', 'chunks', 'member'})
        doc, material, chunks = record['document'], record['material'], record['chunks']
        _keys(doc, DOC_FIELDS)
        _keys(material, MATERIAL_FIELDS)
        _text(doc['id'], 36, 36)
        try:
            _require(str(UUID(doc['id'])) == doc['id'])
        except (ValueError, AttributeError):
            raise ValueError('备份资料标识必须是规范 UUID。') from None
        _require(doc['id'] not in ids, '备份包含重复资料 UUID。')
        ids.add(doc['id'])
        _text(doc['path'], 250, 1)
        parts = doc['path'].split('/')
        _require(len(parts) == 3 and parts[:2] == ['documents', doc['id']], '备份原件路径无效。')
        _filename(parts[2])
        expected = 'originals/' + doc['id'] + Path(parts[2]).suffix.lower()
        _require(record['member'] == expected and expected not in members, '备份原件须使用 UUID 文件名。')
        members.add(expected)
        _text(doc['title'], 240, 1)
        _text(doc['category'], 80, 1)
        _text(doc['error'], 500)
        _text(doc['created_at'], 64, 1)
        try:
            _require(datetime.fromisoformat(doc['created_at']).tzinfo is not None)
        except ValueError:
            raise ValueError('备份资料时间无效。') from None
        _require(isinstance(doc['sha256'], str) and re.fullmatch(r'[0-9a-f]{64}', doc['sha256']))
        _require(isinstance(doc['state'], str) and doc['state'] in STATES)
        _integer(doc['archived'], 0, 1)
        _require(material['path'] == doc['path'] and material['sha256'] == doc['sha256'])
        _integer(material['size'])
        _require(material['size'] <= MAX_FILE_BYTES, f'单份原件上限为 {MAX_FILE_BYTES} 字节（默认 512 MiB）。')
        total += material['size']
        _require(total <= MAX_TOTAL_BYTES, f'备份展开总量上限为 {MAX_TOTAL_BYTES} 字节（默认 2 GiB）。')
        _integer(material['mtime'])
        _require(isinstance(material['status'], str) and material['status'] in STATES)
        if material['page_count'] is not None:
            _integer(material['page_count'], 1)
        _text(material['warnings'], MAX_MANIFEST_BYTES)
        warning_list = _json(material['warnings'])
        _require(isinstance(warning_list, list))
        for warning in warning_list:
            _text(warning, MAX_MANIFEST_BYTES)
        _require(isinstance(chunks, list))
        chunk_count += len(chunks)
        _require(chunk_count <= MAX_CHUNKS, f'备份片段数量上限为 {MAX_CHUNKS} 条。')
        ordinals = set()
        for chunk in chunks:
            _keys(chunk, CHUNK_FIELDS)
            _require(chunk['path'] == doc['path'])
            _integer(chunk['ordinal'])
            _require(chunk['ordinal'] not in ordinals, '备份包含重复引用片段编号。')
            ordinals.add(chunk['ordinal'])
            if chunk['page'] is not None:
                _integer(chunk['page'], 1)
                _require(material['page_count'] is None or chunk['page'] <= material['page_count'])
            _text(chunk['location'], MAX_CHUNK_TEXT)
            _text(chunk['text'], MAX_CHUNK_TEXT)
    return records, members, chunk_count, total


def _copy_verified(source, target, expected_size, expected_sha):
    digest, size = hashlib.sha256(), 0
    while data := source.read(BLOCK):
        size += len(data)
        _require(size <= expected_size and size <= MAX_FILE_BYTES, '备份原件大小不符或超过上限。')
        target.write(data)
        digest.update(data)
    _require(size == expected_size and digest.hexdigest() == expected_sha, '备份原件 SHA-256 校验失败。')


def export_backup(kb, destination):
    """Export every registered document, including archived ones; never overwrite."""
    destination = Path(destination)
    _require(not destination.exists() and not destination.is_symlink(), '备份目标已存在，请使用新的文件名。')
    records = []
    with kb.store.db() as db:
        db.execute('BEGIN')
        _require(db.execute('SELECT count(*) FROM kb_documents').fetchone()[0] <= MAX_DOCUMENTS,
                 f'备份资料数量上限为 {MAX_DOCUMENTS} 份。')
        count, text_bytes, max_text, max_location = db.execute('''SELECT count(*),
            coalesce(sum(length(cast(c.text AS BLOB))+length(cast(c.location AS BLOB))),0),
            coalesce(max(length(c.text)),0),coalesce(max(length(c.location)),0)
            FROM chunks c JOIN kb_documents d ON d.path=c.path''').fetchone()
        _require(count <= MAX_CHUNKS, f'备份片段数量上限为 {MAX_CHUNKS} 条。')
        _require(max_text <= MAX_CHUNK_TEXT and max_location <= MAX_CHUNK_TEXT,
                 f'备份单个片段或位置说明上限为 {MAX_CHUNK_TEXT} 字。')
        metadata_bytes = db.execute('''SELECT coalesce(sum(
            length(cast(d.id AS BLOB))+length(cast(d.path AS BLOB))+length(cast(d.title AS BLOB))+
            length(cast(d.category AS BLOB))+length(cast(d.error AS BLOB))+length(cast(d.created_at AS BLOB))+
            length(cast(m.warnings AS BLOB))),0)
            FROM kb_documents d JOIN materials m ON m.path=d.path''').fetchone()[0]
        _require(text_bytes + metadata_bytes <= MAX_MANIFEST_BYTES,
                 f'备份清单上限为 {MAX_MANIFEST_BYTES} 字节（默认 64 MiB）。')
        # Count serialized bytes incrementally, before retaining the full library.
        manifest_bytes = len(json.dumps({'format': 'qx-knowledge', 'version': 1, 'documents': []}).encode())
        for row in db.execute('SELECT * FROM kb_documents ORDER BY created_at,id'):
            doc = dict(row)
            _, material = kb._current(db, doc)
            record = {'document': doc, 'material': dict(material), 'chunks': [],
                      'member': 'originals/' + doc['id'] + Path(doc['path']).suffix.lower()}
            manifest_bytes += len(json.dumps(record, ensure_ascii=False).encode('utf-8')) + (2 if records else 0)
            _require(manifest_bytes <= MAX_MANIFEST_BYTES, '备份清单超过 64 MiB 上限。')
            for row in db.execute('SELECT * FROM chunks WHERE path=? ORDER BY ordinal', (doc['path'],)):
                chunk = dict(row)
                manifest_bytes += len(json.dumps(chunk, ensure_ascii=False).encode('utf-8')) + (2 if record['chunks'] else 0)
                _require(manifest_bytes <= MAX_MANIFEST_BYTES, '备份清单超过 64 MiB 上限。')
                record['chunks'].append(chunk)
            records.append(record)
        manifest = {'format': 'qx-knowledge', 'version': 1, 'documents': records}
        _, _, chunks, size = _validate(manifest)
        data = json.dumps(manifest, ensure_ascii=False).encode('utf-8')
        _require(len(data) <= MAX_MANIFEST_BYTES, f'备份清单上限为 {MAX_MANIFEST_BYTES} 字节（默认 64 MiB）。')
        _require(size + len(data) <= MAX_TOTAL_BYTES, '备份展开总量超过 2 GiB 上限。')
        # Exclusive creation means a pre-existing file is never truncated.
        output = destination.open('xb')
        try:
            with output, zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
                archive.writestr('manifest.json', data)
                for record in records:
                    doc, material = record['document'], record['material']
                    source = kb.store.safe(doc['path'])
                    before = source.stat()
                    with source.open('rb') as stream, archive.open(record['member'], 'w', force_zip64=True) as saved:
                        _copy_verified(stream, saved, material['size'], doc['sha256'])
                    after = source.stat()
                    _require((before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns), '原件正在变化，备份未完成。')
        except BaseException:
            output.close()
            destination.unlink(missing_ok=True)
            raise
    return {'path': str(destination.absolute()), 'documents': len(records), 'chunks': chunks, 'bytes': size}


def _entries(archive):
    entries, total = {}, 0
    _require(len(archive.infolist()) <= MAX_DOCUMENTS + 1, '备份 ZIP 条目数量超过上限。')
    aliases = set()
    for item in archive.infolist():
        name = item.filename
        parts = name.split('/')
        _require(name == item.orig_filename and '\\' not in name and ':' not in name
                 and not PurePosixPath(name).is_absolute()
                 and all(p and p not in {'.', '..'} and not p.endswith(('.', ' ')) for p in parts),
                 '备份 ZIP 路径无效。')
        _require(name.casefold() not in aliases, '备份 ZIP 含重复条目。')
        aliases.add(name.casefold())
        mode = item.external_attr >> 16
        _require(stat.S_IFMT(mode) in {0, stat.S_IFREG} and not item.is_dir()
                 and not item.external_attr & 0x400 and not item.flag_bits & 1,
                 '备份不接受链接、目录、特殊文件或加密条目。')
        _require(item.compress_type in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}, '备份 ZIP 压缩格式不受支持。')
        maximum = MAX_MANIFEST_BYTES if name == 'manifest.json' else MAX_FILE_BYTES
        _require(item.file_size <= maximum, f'备份 ZIP 单项大小超过 {maximum} 字节上限。')
        total += item.file_size
        _require(total <= MAX_TOTAL_BYTES, '备份 ZIP 展开总量超过 2 GiB 上限。')
        entries[name] = item
    _require('manifest.json' in entries, '备份缺少 manifest.json。')
    return entries


def _preflight(stream):
    """Bound the central directory before ZipFile allocates its member objects."""
    size = os.fstat(stream.fileno()).st_size
    _require(size <= MAX_ARCHIVE_BYTES, f'ZIP 文件大小超过 {MAX_ARCHIVE_BYTES} 字节上限。')
    stream.seek(max(0, size - 65557))
    tail_start = stream.tell()
    tail = stream.read(65557)
    end = tail.rfind(b'PK\x05\x06')
    _require(end >= 0 and end + 22 <= len(tail), 'ZIP 备份目录无效。')
    _, disk, directory_disk, on_disk, count, directory_size, offset, comment = struct.unpack_from('<4s4H2LH', tail, end)
    _require(count <= MAX_DOCUMENTS + 1 and directory_size <= 8 * 1024 * 1024,
             'ZIP 目录条目数量或目录大小超过上限。')
    # Our <2 GiB / 10k-document format never needs ZIP64 end records or split disks.
    _require(disk == directory_disk == 0 and on_disk == count
             and offset + directory_size == tail_start + end
             and end + 22 + comment == len(tail), 'ZIP 备份目录无效；不支持分卷备份。')
    stream.seek(0)


def _remove_owned(kb, directory):
    # Only paths created by this operation are passed here, never archive paths.
    directory = kb.store.safe(directory, internal=True)
    _require(directory.is_dir())
    shutil.rmtree(directory)


def restore_backup(kb, archive):
    """Validate and stage everything, then merge under one SQLite write transaction."""
    internal = kb.store.safe(kb.store.internal, internal=True)
    stage = Path(tempfile.mkdtemp(prefix='kb-restore-', dir=internal))
    created = []
    try:
        try:
            with Path(archive).open('rb') as archive_stream:
                _preflight(archive_stream)
                source = zipfile.ZipFile(archive_stream)
                with source:
                    entries = _entries(source)
                    manifest = _json(source.read(entries['manifest.json']))
                    records, members, _, _ = _validate(manifest)
                    _require(set(entries) == members | {'manifest.json'}, '备份含未登记或缺失的原件。')
                    for record in records:
                        doc, material = record['document'], record['material']
                        _require(entries[record['member']].file_size == material['size'], '备份原件大小与清单不符。')
                        directory = stage / doc['id']
                        directory.mkdir()
                        with source.open(entries[record['member']]) as stream, (directory / Path(doc['path']).name).open('xb') as saved:
                            _copy_verified(stream, saved, material['size'], doc['sha256'])
        except (zipfile.BadZipFile, EOFError, NotImplementedError):
            raise ValueError('ZIP 备份损坏或格式不受支持。') from None

        imported, skipped, chunks = 0, 0, 0
        try:
            with kb.store.db() as db:
                db.execute('BEGIN IMMEDIATE')
                pending = []
                for record in records:
                    doc = record['document']
                    old = db.execute('SELECT * FROM kb_documents WHERE id=?', (doc['id'],)).fetchone()
                    if old is not None:
                        _require(old['sha256'] == doc['sha256'], '资料 UUID 与现有原件版本冲突；未导入任何资料。')
                        existing, _ = kb._current(db, old)
                        with existing.open('rb') as stream:
                            _require(hashlib.file_digest(stream, 'sha256').hexdigest() == old['sha256'], '现有原件校验冲突；未导入任何资料。')
                        skipped += 1
                        continue
                    directory = kb.store.safe(kb.store.root / 'documents' / doc['id'], internal=True, must_exist=False)
                    _require(not directory.exists() and not directory.is_symlink(), '原件目录已存在且未登记，不能覆盖；导入冲突。')
                    _require(db.execute('SELECT 1 FROM materials WHERE path=?', (doc['path'],)).fetchone() is None
                             and db.execute('SELECT 1 FROM chunks WHERE path=?', (doc['path'],)).fetchone() is None,
                             '原件路径已有索引记录，导入冲突。')
                    pending.append((record, directory))
                documents = kb.store.safe(kb.store.root / 'documents', internal=True, must_exist=False)
                if pending:
                    documents.mkdir(exist_ok=True)
                for record, directory in pending:
                    doc, material = record['document'], record['material']
                    # Reserve exclusively; rename only into this newly created directory.
                    directory.mkdir()
                    created.append(directory)
                    destination = kb.store.safe(directory / Path(doc['path']).name, must_exist=False)
                    os.rename(stage / doc['id'] / destination.name, destination)
                    info = destination.stat()
                    db.execute('INSERT INTO materials(path,size,mtime,sha256,status,page_count,warnings) VALUES(?,?,?,?,?,?,?)',
                               (doc['path'], info.st_size, info.st_mtime_ns, doc['sha256'], material['status'], material['page_count'], material['warnings']))
                    db.execute('INSERT INTO kb_documents(id,path,title,category,sha256,created_at,state,error,archived) VALUES(?,?,?,?,?,?,?,?,?)',
                               tuple(doc[key] for key in ('id', 'path', 'title', 'category', 'sha256', 'created_at', 'state', 'error', 'archived')))
                    db.executemany('INSERT INTO chunks(path,ordinal,page,location,text) VALUES(?,?,?,?,?)',
                                   [tuple(c[key] for key in ('path', 'ordinal', 'page', 'location', 'text')) for c in record['chunks']])
                    imported += 1
                    chunks += len(record['chunks'])
        except BaseException:
            for directory in reversed(created):
                _remove_owned(kb, directory)
            raise
        return {'imported': imported, 'skipped': skipped, 'chunks': chunks}
    finally:
        _remove_owned(kb, stage)
