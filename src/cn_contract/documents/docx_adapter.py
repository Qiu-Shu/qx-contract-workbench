"""Bounded OOXML extraction; archive bytes never get extracted onto the filesystem."""
from io import BytesIO
from pathlib import PurePosixPath
import stat
import struct
import unicodedata
import zipfile
import zlib

from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException
from xml.etree.ElementTree import ParseError

from ..domain import AnchorKind, BaselineView, ParseResult
from ..security import ServiceError
from .anchors import make_anchor

W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
R = 'http://schemas.openxmlformats.org/package/2006/relationships'
CT = 'http://schemas.openxmlformats.org/package/2006/content-types'
MAIN_TYPE = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml'


def _unsupported():
    raise ServiceError('FILE_UNSUPPORTED', 400)


def _xml(data):
    try:
        return ElementTree.fromstring(data, forbid_dtd=True, forbid_entities=True, forbid_external=True)
    except (ParseError, DefusedXmlException, ValueError, RecursionError):
        _unsupported()


def read_package(data, settings):
    """Check local headers, actual deflate output and CRC, not ZipExtFile's size cap.

    Zip64, split archives, nonstandard flags and ambiguous padding are unsupported.
    The 50 MiB input is already bounded by the service; output is bounded as it is
    inflated. Central sizes are only claims, never permission to return truncated XML.
    """
    try:
        archive = zipfile.ZipFile(BytesIO(data))
        infos = archive.infolist()
        if not infos or len(infos) > 10000:
            _unsupported()
        eocd = data.rfind(b'PK\x05\x06')
        if eocd < 0 or len(data) - eocd < 22:
            _unsupported()
        _, disk, cd_disk, disk_count, count, cd_size, cd_offset, comment = struct.unpack_from('<4s4H2IH', data, eocd)
        if (disk or cd_disk or disk_count != count or count != len(infos) or count == 65535
                or cd_offset + cd_size != eocd or eocd + 22 + comment != len(data)
                or archive.start_dir != cd_offset):
            _unsupported()
        ordered = sorted(infos, key=lambda item: item.header_offset)
        if ordered[0].header_offset != 0:
            _unsupported()
        result, seen, total, compressed_total = {}, set(), 0, 0
        for index, info in enumerate(ordered):
            name = info.orig_filename
            normalized = unicodedata.normalize('NFC', str(PurePosixPath(name))).casefold()
            if (not name or name != info.filename or '\\' in name or '\x00' in name
                    or name.startswith('/') or ':' in name or '..' in name.split('/')
                    or normalized in seen or stat.S_ISLNK(info.external_attr >> 16)
                    or info.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}
                    or info.flag_bits & ~(0x800 | 0x8) or info.extract_version > 20
                    or 'vbaproject' in normalized or normalized.endswith('.docm')):
                _unsupported()
            seen.add(normalized)
            if info.file_size > settings.archive_uncompressed_max_mib * 1024 * 1024:
                raise ServiceError('FILE_LIMIT', 413)
            signature, version, flags, compression, _, _, crc, csize, usize, nlen, xlen = struct.unpack_from('<4s5H3I2H', data, info.header_offset)
            if signature != b'PK\x03\x04' or version > 20 or flags != info.flag_bits or compression != info.compress_type:
                _unsupported()
            begin = info.header_offset + 30
            raw_name = data[begin:begin + nlen]
            if raw_name.decode('utf-8' if flags & 0x800 else 'cp437') != name:
                _unsupported()
            payload_start = begin + nlen + xlen
            next_offset = ordered[index + 1].header_offset if index + 1 < len(ordered) else cd_offset
            payload_end = payload_start + info.compress_size
            if payload_start > payload_end or payload_end > next_offset:
                _unsupported()
            if flags & 8:
                descriptor = data[payload_end:next_offset]
                if descriptor.startswith(b'PK\x07\x08'):
                    descriptor = descriptor[4:]
                if len(descriptor) != 12 or struct.unpack('<3I', descriptor) != (info.CRC, info.compress_size, info.file_size):
                    _unsupported()
                if (crc, csize, usize) not in {(0, 0, 0), (info.CRC, info.compress_size, info.file_size)}:
                    _unsupported()
            elif payload_end != next_offset or (crc, csize, usize) != (info.CRC, info.compress_size, info.file_size):
                _unsupported()
            payload = data[payload_start:payload_end]
            compressed_total += len(payload)
            max_output = min(settings.archive_uncompressed_max_mib * 1024 * 1024 - total,
                             max(1, len(payload)) * settings.archive_max_ratio)
            if compression == zipfile.ZIP_DEFLATED:
                decoder = zlib.decompressobj(-15)
                content = decoder.decompress(payload, max_output + 1)
                if len(content) > max_output or decoder.unconsumed_tail:
                    raise ServiceError('FILE_LIMIT', 413)
                if not decoder.eof or decoder.unused_data:
                    _unsupported()
            else:
                content = payload
            total += len(content)
            if total > settings.archive_uncompressed_max_mib * 1024 * 1024 or len(content) > max_output:
                raise ServiceError('FILE_LIMIT', 413)
            if len(content) != info.file_size or zlib.crc32(content) != info.CRC:
                _unsupported()
            if name.endswith('/'):
                if content:
                    _unsupported()
                continue
            result[name] = content
        if total > max(1, compressed_total) * settings.archive_max_ratio:
            raise ServiceError('FILE_LIMIT', 413)
        required = {'[Content_Types].xml', '_rels/.rels', 'word/document.xml'}
        if not required <= result.keys():
            _unsupported()
        xml_parts = {name: _xml(content) for name, content in result.items() if name.endswith(('.xml', '.rels'))}
        types = xml_parts['[Content_Types].xml']
        if (types.tag != f'{{{CT}}}Types' or any('macroenabled' in value.lower() or 'vba' in value.lower()
                                              for node in types.iter() for value in node.attrib.values())
                or not any(node.get('PartName') == '/word/document.xml' and node.get('ContentType') == MAIN_TYPE for node in types)):
            _unsupported()
        root_rels = xml_parts['_rels/.rels']
        mains = [node for node in root_rels if node.get('Type', '').endswith('/officeDocument')]
        if (root_rels.tag != f'{{{R}}}Relationships' or len(mains) != 1
                or mains[0].get('Target') != 'word/document.xml' or mains[0].get('TargetMode') == 'External'):
            _unsupported()
        document = xml_parts['word/document.xml']
        if document.tag != f'{{{W}}}document' or document.find(f'{{{W}}}body') is None:
            _unsupported()
        return result, xml_parts
    except ServiceError:
        raise
    except (zipfile.BadZipFile, UnicodeError, struct.error, zlib.error, OSError, ValueError, RuntimeError):
        _unsupported()


def has_revisions(xml_parts):
    revision_names = {'ins', 'del', 'moveFrom', 'moveTo', 'pPrChange', 'rPrChange', 'tblPrChange', 'trPrChange', 'tcPrChange', 'sectPrChange', 'numberingChange', 'cellIns', 'cellDel', 'cellMerge'}
    return any(node.tag in {f'{{{W}}}{name}' for name in revision_names}
               for root in xml_parts.values() for node in root.iter())


def parse_docx(data, version, settings):
    package, xml_parts = read_package(data, settings)
    body = xml_parts['word/document.xml'].find(f'{{{W}}}body')
    part, unsupported, quality, anchors = 'word/document.xml', set(), [], []
    inventory = []
    for name in package:
        if name == part:
            inventory.append(f'{name}:read')
        elif name in {'[Content_Types].xml', '_rels/.rels', 'word/_rels/document.xml.rels',
                      'docProps/core.xml', 'docProps/app.xml', 'docProps/custom.xml'}:
            inventory.append(f'{name}:metadata_read')
        else:
            inventory.append(f'{name}:unsupported')
            unsupported.add(name)
        if name.endswith('.rels'):
            for rel in xml_parts[name]:
                if rel.get('TargetMode') == 'External':
                    unsupported.add(f'{name}:external_relationship:{rel.get("Id", "unknown")}')
    if has_revisions(xml_parts):
        unsupported.add(f'{part}:revisions:manual_required')
    document = xml_parts[part]
    for child in document:
        if child is not body:
            unsupported.add(f'{part}:unknown_objects:{child.tag}:manual_required')
    if version.baseline_view == BaselineView.CONFIRMED_CUSTOM:
        unsupported.add(f'{part}:custom_baseline')
        quality.append('CUSTOM_BASELINE_ARTIFACT_REQUIRED')
        return ParseResult(version_id=version.id, anchors=(), pages=(), parts=tuple(inventory),
                           unsupported_parts=tuple(sorted(unsupported)), quality_issues=tuple(quality))

    def text(node):
        local = node.tag.removeprefix(f'{{{W}}}')
        if node.tag == f'{{{W}}}ins' and version.baseline_view != BaselineView.ACCEPTED_VIEW:
            return ''
        if node.tag == f'{{{W}}}del' and version.baseline_view == BaselineView.ACCEPTED_VIEW:
            return ''
        if local in {'txbxContent', 'drawing', 'pict'}:
            unsupported.add(f'{part}:textboxes_or_drawing:manual_required')
            return ''
        if local == 'object':
            unsupported.add(f'{part}:embedded_objects:manual_required')
            return ''
        if local == 'r' and any(prop.tag in {f'{{{W}}}vanish', f'{{{W}}}webHidden'} and prop.get(f'{{{W}}}val', 'true') not in {'0', 'false', 'off'}
                                for prop in node.findall(f'{{{W}}}rPr/*')):
            unsupported.add(f'{part}:hidden:manual_required')
            return ''
        if local in {'t', 'delText'}:
            return node.text or ''
        if local == 'tab':
            return '\t'
        if local in {'br', 'cr'}:
            return '\n'
        if local in {'rPr', 'pPr', 'tblPr', 'trPr', 'tcPr', 'sectPr', 'tblGrid', 'bookmarkStart', 'bookmarkEnd', 'proofErr', 'lastRenderedPageBreak'}:
            return ''
        if local not in {'p', 'r', 'hyperlink', 'ins', 'del'}:
            unsupported.add(f'{part}:unknown_objects:{local}:manual_required')
            return ''
        return ''.join(text(child) for child in node)

    table_count = 0

    def blocks(parent, path, coords=None):
        nonlocal table_count
        counts = {}
        for child in parent:
            local = child.tag.removeprefix(f'{{{W}}}')
            counts[local] = counts.get(local, 0) + 1
            child_path = f'{path}/{local}[{counts[local]}]'
            if child.tag == f'{{{W}}}p':
                quote = text(child)
                if quote:
                    kwargs = {} if coords is None else dict(zip(('table', 'row', 'cell'), coords))
                    anchors.append(make_anchor(version, part, child_path, quote,
                                               AnchorKind.BODY_PARAGRAPH if coords is None else AnchorKind.TABLE_CELL, **kwargs))
            elif child.tag == f'{{{W}}}tbl':
                table = table_count
                table_count += 1
                for row, tr in enumerate(child.findall(f'{{{W}}}tr')):
                    for item in tr:
                        if item.tag not in {f'{{{W}}}tc', f'{{{W}}}trPr'}:
                            unsupported.add(f'{part}:unknown_objects:{item.tag.removeprefix(f"{{{W}}}")}:manual_required')
                    for cell, tc in enumerate(tr.findall(f'{{{W}}}tc')):
                        blocks(tc, f'{child_path}/tr[{row + 1}]/tc[{cell + 1}]', (table, row, cell))
                unknown = [item for item in child if item.tag not in {f'{{{W}}}tr', f'{{{W}}}tblPr', f'{{{W}}}tblGrid'}]
                if unknown:
                    unsupported.add(f'{part}:unknown_objects:table_structure')
            elif local in {'ins', 'del'}:
                if (local == 'ins') == (version.baseline_view == BaselineView.ACCEPTED_VIEW):
                    blocks(child, child_path, coords)
            elif local != 'sectPr' and local not in {'tcPr'}:
                unsupported.add(f'{part}:unknown_objects:{local}:manual_required')
    try:
        blocks(body, 'body')
    except RecursionError:
        _unsupported()
    return ParseResult(version_id=version.id, anchors=tuple(anchors), pages=(), parts=tuple(inventory),
                       unsupported_parts=tuple(sorted(unsupported)), quality_issues=tuple(quality))
