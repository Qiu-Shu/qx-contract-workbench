"""Private, hash-bound reference text; plugin instructions are never executed."""
from datetime import datetime, timezone
import hashlib
from io import BytesIO
import json
from pathlib import Path
import re
import stat
from zipfile import ZipFile

from defusedxml import ElementTree

from .. import domain as d
from ..ops.backup import checked_file, checked_root, safe_relative, strict_json
from ..security import ServiceError

MAX_ARCHIVE = 20 * 1024 * 1024
MAX_EXPANDED = 64 * 1024 * 1024
MAX_TEXT = 1024 * 1024
NS = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
LIMITATIONS = ('仅检索正文及表格文字；图片、页眉页脚、脚注等未纳入。',
               '片段按正文顺序编号；长段按1200字切分。',
               '用户提供资料，身份、经历、案例及联系方式均待核实。')


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')


def inventory(archive):
    members = archive.infolist()
    if len(members) > 256 or sum(i.file_size for i in members) > MAX_EXPANDED:
        raise ValueError('ARCHIVE_LIMIT')
    names = set()
    for item in members:
        safe_relative(item.filename.rstrip('/'))
        if item.filename in names or stat.S_ISLNK(item.external_attr >> 16):
            raise ValueError('ARCHIVE_MEMBER_INVALID')
        names.add(item.filename)
        if item.flag_bits & 1 or item.file_size > MAX_ARCHIVE:
            raise ValueError('ARCHIVE_LIMIT')
    return names


def paragraphs(raw):
    with ZipFile(BytesIO(raw)) as archive:
        inventory(archive)
        xml = archive.read('word/document.xml')
        if len(xml) > MAX_TEXT:
            raise ValueError('DOCUMENT_TEXT_LIMIT')
        root = ElementTree.fromstring(xml)
    result = []
    for paragraph in root.findall('.//w:p', NS):
        text = ''.join(t.text or '' for t in paragraph.findall('.//w:t', NS)).strip()
        # Each displayed passage has an exact position and bounded byte-bound quote.
        for start in range(0, len(text), 1200):
            result.append(text[start:start + 1200])
    if len(encoded(result)) > MAX_TEXT:
        raise ValueError('DOCUMENT_TEXT_LIMIT')
    return result


def import_plugin(source, destination):
    source, destination = Path(source), Path(destination)
    if destination.exists():
        raise ValueError('KNOWLEDGE_ALREADY_EXISTS')
    if source.stat().st_size > MAX_ARCHIVE:
        raise ValueError('ARCHIVE_LIMIT')
    raw = source.read_bytes()
    sources, contents, originals = {}, {}, {}
    count = 0
    with ZipFile(BytesIO(raw)) as archive:
        names = inventory(archive)
        for name in sorted(names):
            if not name.startswith('skills/instructions/references/') or not name.endswith('.docx'):
                continue
            data = archive.read(name)
            identifier = digest(data)
            count += 1
            if identifier in sources:
                sources[identifier]['aliases'].append(Path(name).name)
                continue
            text = paragraphs(data)
            body = encoded(text)
            record = d.ReceptionSource(id=identifier, title=Path(name).stem,
                aliases=(Path(name).name,), text_sha256=digest(body), paragraph_count=len(text),
                limitations=LIMITATIONS).model_dump(mode='json')
            sources[identifier] = record
            contents[identifier] = body
            originals[identifier] = data
    if not sources:
        raise ValueError('KNOWLEDGE_DOCUMENTS_REQUIRED')
    manifest = {'format':'qx-reception-knowledge-v1', 'archive_sha256':digest(raw),
                'imported_at':datetime.now(timezone.utc).isoformat(), 'original_documents':count,
                'sources':list(sources.values())}
    # Validate the complete import before creating a new private directory.
    for source_record in manifest['sources']:
        d.ReceptionSource.model_validate(source_record)
    destination.mkdir(parents=True, mode=0o700, exist_ok=False)
    (destination / 'documents').mkdir(mode=0o700)
    (destination / 'originals').mkdir(mode=0o700)
    for identifier, data in contents.items():
        (destination / 'documents' / (identifier + '.json')).write_bytes(data)
        (destination / 'originals' / (identifier + '.docx')).write_bytes(originals[identifier])
    (destination / 'plugin-original.zip').write_bytes(raw)
    (destination / 'manifest.json').write_bytes(encoded(manifest))
    return manifest


class KnowledgeStore:
    def __init__(self, root):
        self.root = Path(root)

    def catalog(self):
        if not self.root.exists():
            return d.ReceptionKnowledgeCatalog(state='not_configured')
        try:
            root = checked_root(self.root)
            raw = checked_file(root / 'manifest.json', root, limit=MAX_TEXT)
            value = strict_json(raw)
            if value['format'] != 'qx-reception-knowledge-v1' or len(value['sources']) > 128:
                raise ValueError('KNOWLEDGE_MANIFEST_INVALID')
            result = d.ReceptionKnowledgeCatalog(state='ready', archive_sha256=value['archive_sha256'],
                original_documents=value['original_documents'], sources=value['sources'])
            if len({s.id for s in result.sources}) != len(result.sources):
                raise ValueError('KNOWLEDGE_MANIFEST_INVALID')
            return result
        except (OSError, ValueError, KeyError, TypeError):
            raise ServiceError('DATA_POLICY_UNAPPROVED', 409) from None

    def document(self, identifier):
        source = next((s for s in self.catalog().sources if s.id == identifier), None)
        if source is None:
            raise ServiceError('NOT_SUPPORTED', 404)
        try:
            root = checked_root(self.root)
            original = checked_file(root / 'originals' / (source.id + '.docx'), root, limit=MAX_ARCHIVE)
            path = checked_file(root / 'documents' / (source.id + '.json'), root, limit=MAX_TEXT)
            raw = path
            if digest(original) != source.id or digest(raw) != source.text_sha256:
                raise ValueError('KNOWLEDGE_HASH_MISMATCH')
            text = strict_json(raw)
            if (not isinstance(text, list) or len(text) != source.paragraph_count
                    or any(not isinstance(p, str) or not 1 <= len(p) <= 1200 for p in text)):
                raise ValueError('KNOWLEDGE_TEXT_INVALID')
            return source, text
        except (OSError, ValueError, TypeError):
            raise ServiceError('DATA_POLICY_UNAPPROVED', 409) from None

    @staticmethod
    def passage(source, index, text):
        return d.ReceptionPassage(source_id=source.id, title=source.title, paragraph=index + 1,
            text=text, quote_sha256=digest(text.encode('utf-8')), source_sha256=source.id)

    def page(self, identifier, start=0):
        source, text = self.document(identifier)
        end = min(start + 12, len(text))
        return d.ReceptionSourcePage(source=source,
            items=tuple(self.passage(source, i, text[i]) for i in range(start, end)),
            next_start=end if end < len(text) else None)

    def search(self, query):
        terms = re.findall(r'\S+', query.strip().casefold())
        if not terms:
            return d.ReceptionSearchResult()
        ranked = []
        for source in self.catalog().sources:
            _, text = self.document(source.id)
            for index, paragraph in enumerate(text):
                score = sum(term in paragraph.casefold() for term in terms)
                if score:
                    ranked.append((score, self.passage(source, index, paragraph)))
        ranked.sort(key=lambda row: -row[0])
        return d.ReceptionSearchResult(items=tuple(p for _, p in ranked[:12]))

    def resolve(self, reference):
        source, text = self.document(reference.source_id)
        if reference.paragraph > len(text):
            raise ServiceError('VERSION_CONFLICT', 409)
        passage = self.passage(source, reference.paragraph - 1, text[reference.paragraph - 1])
        if passage.quote_sha256 != reference.quote_sha256:
            raise ServiceError('VERSION_CONFLICT', 409)
        return passage
