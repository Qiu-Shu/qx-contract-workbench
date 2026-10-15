"""Bounded original reads with cached handles during bulk indexing."""
from collections import OrderedDict
import csv
import io
import json
from pathlib import Path
import sys

from ..domain import LibrarySource
from .assets import _asset_path_in_root, file_hash
from .catalog import connection, digest, _get_source, _get_record
from .csv_source import read_header


class OriginalReader:
    def __init__(self, root, *, preload=False):
        self.root = Path(root)
        self.sources = {}
        self.streams = OrderedDict()
        self.headers = {}
        self.preload = preload

    def __enter__(self):
        self._catalog = connection(self.root)
        self.db = self._catalog.__enter__()
        try:
            if self.preload:
                self.sources = {row[0]: LibrarySource.model_validate_json(row[1])
                                for row in self.db.execute('SELECT source_id,source_json FROM sources')}
        except BaseException:
            self._catalog.__exit__(*sys.exc_info())
            raise
        return self

    def __exit__(self, *args):
        try:
            for stream in self.streams.values():
                stream.close()
        finally:
            self._catalog.__exit__(*args)

    def get_record(self, record_id):
        return _get_record(self.db, record_id)

    def read(self, record):
        source = self.sources.get(record.source_id)
        if source is None:
            source = self.sources[record.source_id] = _get_source(self.db, record.source_id)
        if record.byte_end > source.size:
            raise ValueError('ASSET_RANGE_INVALID')
        stream = self.streams.pop(source.source_id, None)
        if stream is None:
            path = _asset_path_in_root(self.root, source)
            stream = path.open('rb')
            try:
                if source.kind == 'case_csv':
                    header, _ = read_header(stream)
                    state = self.db.execute('SELECT header_json FROM import_states WHERE source_id=?', (source.source_id,)).fetchone()
                    expected = json.loads(state[0]) if state else None
                    if expected is None:
                        if file_hash(path) != source.sha256:
                            raise ValueError('ASSET_HASH_MISMATCH')
                    elif expected != header:
                        raise ValueError('SOURCE_CHANGED_HEADER')
                    self.headers[source.source_id] = header
            except BaseException:
                stream.close()
                raise
        self.streams[source.source_id] = stream
        if len(self.streams) > 32:
            _, old = self.streams.popitem(last=False)
            old.close()
        stream.seek(record.byte_start)
        raw = stream.read(record.byte_end - record.byte_start)
        if digest(raw) != record.raw_sha256:
            raise ValueError('ASSET_HASH_MISMATCH')
        if source.kind == 'case_csv':
            parsed = list(csv.reader(io.StringIO(raw.decode('utf-8'), newline=''), strict=True))
            if len(parsed) != 1:
                raise ValueError('SOURCE_RECORD_INVALID')
            header = self.headers[source.source_id]
            fields = dict(zip(header, parsed[0])) if len(header) == len(parsed[0]) else {'_header': header, '_values': parsed[0]}
            text = fields.get('文书内容', '')
            body_hash = digest(text.encode('utf-8')) if text else None
        else:
            text = raw.decode('utf-8-sig')
            fields = {'原文件名': record.fields.get('filename')}
            body_hash = digest(text.encode('utf-8'))
        if body_hash != record.body_sha256:
            raise ValueError('BODY_HASH_MISMATCH')
        return text, fields, source
