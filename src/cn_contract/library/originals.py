"""Bounded original reads with cached handles during bulk indexing."""
from collections import OrderedDict
import csv
import io
import json

from ..domain import LibrarySource
from .assets import asset_path, file_hash
from .catalog import connection, digest, get_source
from .csv_source import read_header


class OriginalReader:
    def __init__(self, root, *, preload=False):
        self.root = root
        self.sources = {}
        self.streams = OrderedDict()
        self.headers = {}
        self.expected_headers = {}
        with connection(root) as db:
            for row in db.execute('SELECT source_id,header_json FROM import_states'):
                self.expected_headers[row[0]] = json.loads(row[1])
            if preload:
                self.sources = {row[0]: LibrarySource.model_validate_json(row[1])
                                for row in db.execute('SELECT source_id,source_json FROM sources')}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        for stream in self.streams.values():
            stream.close()

    def read(self, record):
        source = self.sources.get(record.source_id)
        if source is None:
            source = self.sources[record.source_id] = get_source(self.root, record.source_id)
        if record.byte_end > source.size:
            raise ValueError('ASSET_RANGE_INVALID')
        stream = self.streams.pop(source.source_id, None)
        if stream is None:
            path = asset_path(self.root, source)
            stream = path.open('rb')
            try:
                if source.kind == 'case_csv':
                    header, _ = read_header(stream)
                    expected = self.expected_headers.get(source.source_id)
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
