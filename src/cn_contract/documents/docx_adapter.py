"""Bounded OOXML extraction; archive bytes never get extracted onto the filesystem."""
from io import BytesIO
from pathlib import PurePosixPath
import posixpath
import re
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
from .docx_styles import EffectiveStyles, StyleDependencyError, W14, text_fill_supported

W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
R = 'http://schemas.openxmlformats.org/package/2006/relationships'
CT = 'http://schemas.openxmlformats.org/package/2006/content-types'
MAIN_TYPE = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml'
O = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/'
A = 'http://schemas.openxmlformats.org/drawingml/2006/main'
B = 'http://schemas.openxmlformats.org/officeDocument/2006/bibliography'
C = 'http://schemas.openxmlformats.org/officeDocument/2006/customXml'
MC = 'http://schemas.openxmlformats.org/markup-compatibility/2006'
WPS_DATA = 'http://www.wps.cn/officeDocument/2013/wpsCustomData'

# A deliberately finite structural subset. Unknown elements remain unread even
# in a correctly named, declared and related Office auxiliary part.
STYLE_TAGS = set(('styles style docDefaults pPrDefault rPrDefault latentStyles lsdException '
                 'basedOn name next link qFormat uiPriority semiHidden unhideWhenUsed rsid '
                 'rPr pPr b bCs i iCs color contextualSpacing keepLines keepNext kern lang '
                 'rFonts sz szCs smallCaps u spacing ind outlineLvl numPr numId ilvl '
                 'pBdr top bottom left right insideH insideV shd tab tabs tblPr tblBorders '
                 'tblCellMar tblInd tblStyleColBandSize tblStyleRowBandSize tblStylePr tcPr '
                 'tcBorders vanish webHidden').split())
SETTINGS_TAGS = set(('settings zoom proofState defaultTabStop characterSpacingControl '
                    'savePreviewPicture doNotAutoCompressPictures compat compatSetting rsids '
                    'rsidRoot rsid themeFontLang clrSchemeMapping decimalSymbol listSeparator '
                    'shapeDefaults useFELayout documentProtection footnotePr footnote endnotePr endnote').split())
THEME_TAGS = set(('theme themeElements clrScheme dk1 dk2 lt1 lt2 accent1 accent2 accent3 '
                 'accent4 accent5 accent6 hlink folHlink sysClr srgbClr fontScheme majorFont '
                 'minorFont latin ea cs font fmtScheme fillStyleLst solidFill schemeClr '
                 'gradFill gsLst gs tint shade satMod alpha lin path fillToRect lnStyleLst '
                 'ln prstDash effectStyleLst effectStyle effectLst outerShdw scene3d camera '
                 'lightRig rot sp3d bevelT bgFillStyleLst objectDefaults spDef spPr bodyPr '
                 'lstStyle style lnRef fillRef effectRef fontRef lnDef extraClrSchemeLst').split())
NUMBERING_TAGS = set(('numbering abstractNum abstractNumId num numId lvl ilvl start numFmt '
                     'lvlText lvlJc multiLevelType nsid tmpl pStyle pPr rPr tabs tab ind '
                     'rFonts lvlOverride startOverride numStyleLink styleLink suff isLgl '
                     'lvlRestart b i color sz vanish webHidden').split())


def _tags(root, namespace, names):
    permitted = {f'{{{namespace}}}{name}' for name in names}
    return root is not None and all(node.tag in permitted and not (node.text or '').strip()
                                    and not (node.tail or '').strip() for node in root.iter())


def _separator_notes(root, role):
    names = {role, role[:-1], 'p', 'pPr', 'spacing', 'r', 'separator', 'continuationSeparator'}
    if (not _tags(root, W, names) or len(root) != 2
            or not root.attrib.keys() <= {f'{{{MC}}}Ignorable'}):
        return False
    kinds, identifiers = set(), set()
    for note in root:
        kind, identifier = note.get(f'{{{W}}}type'), note.get(f'{{{W}}}id', '')
        if (note.tag != f'{{{W}}}{role[:-1]}' or set(note.attrib) != {f'{{{W}}}type', f'{{{W}}}id'}
                or kind not in {'separator', 'continuationSeparator'} or kind in kinds
                or not re.fullmatch(r'-?[0-9]{1,10}', identifier) or int(identifier) in identifiers
                or len(note) != 1 or note[0].tag != f'{{{W}}}p'):
            return False
        kinds.add(kind); identifiers.add(int(identifier))
        paragraph = note[0]
        if [child.tag for child in paragraph] not in ([f'{{{W}}}r'], [f'{{{W}}}pPr', f'{{{W}}}r']):
            return False
        for node in paragraph.iter():
            if node.tag in {f'{{{W}}}p', f'{{{W}}}r'}:
                if any(name not in {f'{{{W}}}'+key for key in ('rsidR', 'rsidRPr', 'rsidRDefault', 'rsidP')}
                       or not re.fullmatch('[0-9a-fA-F]{8}', value) for name, value in node.attrib.items()):
                    return False
            elif node.tag == f'{{{W}}}pPr':
                if node.attrib or len(node) > 1 or any(child.tag != f'{{{W}}}spacing' for child in node):
                    return False
            elif node.tag == f'{{{W}}}spacing':
                if len(node) or any((value not in {'auto', 'exact', 'atLeast'} if name == f'{{{W}}}lineRule'
                    else name not in {f'{{{W}}}'+key for key in ('before', 'after', 'line')}
                    or not re.fullmatch('[0-9]+', value)) for name, value in node.attrib.items()):
                    return False
            elif node.attrib or len(node):
                return False
        run = paragraph[-1]
        if len(run) != 1 or run[0].tag != f'{{{W}}}{kind}':
            return False
    return True


def _wps_settings_choice(node):
    if (node.attrib or (node.text or '').strip() or (node.tail or '').strip() or len(node) != 1
            or node[0].tag != f'{{{MC}}}Choice'):
        return False
    choice = node[0]
    if (choice.attrib != {'Requires':'wpsCustomData'}
            or len(choice) != 1 or choice[0].tag != f'{{{WPS_DATA}}}typoFeatureVersion'):
        return False
    feature = choice[0]
    return (not len(feature) and feature.attrib == {'val':'0'}
            and all(not (item.text or '').strip() and not (item.tail or '').strip() for item in choice.iter()))


def _auxiliary_content(role, root, data):
    if role in {'styles', 'stylesWithEffects'}:
        if root is None or any(node.tag not in {f'{{{W}}}style', f'{{{W}}}docDefaults', f'{{{W}}}latentStyles'}
                               for node in root):
            return False
        permitted = {f'{{{W}}}{name}' for name in STYLE_TAGS}
        pending = [(root, None)]
        while pending:
            node, parent_tag = pending.pop()
            if node.tag == f'{{{W14}}}textFill':
                if parent_tag != f'{{{W}}}rPr' or not text_fill_supported(node):
                    return False
                continue
            if (node.tag not in permitted or (node.text or '').strip() or (node.tail or '').strip()
                    or len(node.findall(f'{{{W14}}}textFill')) > 1):
                return False
            pending.extend((child, node.tag) for child in node)
        return True
    if role == 'numbering':
        return _tags(root, W, NUMBERING_TAGS)
    if role in {'footnotes', 'endnotes'}:
        return _separator_notes(root, role)
    if role == 'settings':
        permitted = {f'{{{W}}}{name}' for name in SETTINGS_TAGS}
        permitted |= {f'{{http://schemas.openxmlformats.org/officeDocument/2006/math}}{name}'
                      for name in 'mathPr mathFont brkBin brkBinSub smallFrac dispDef lMargin rMargin defJc wrapIndent intLim naryLim'.split()}
        permitted |= {f'{{http://schemas.microsoft.com/office/word/2010/wordml}}{name}' for name in ('docId', 'defaultImageDpi')}
        permitted |= {f'{{urn:schemas-microsoft-com:office:office}}{name}' for name in ('shapedefaults', 'shapelayout', 'idmap')}
        pending = [(root, None)] if root is not None else []
        while pending:
            node, parent = pending.pop()
            if node.tag == f'{{{MC}}}AlternateContent':
                if parent != f'{{{W}}}settings' or not _wps_settings_choice(node):
                    return False
                continue
            if node.tag not in permitted or (node.text or '').strip() or (node.tail or '').strip():
                return False
            if node.tag in {f'{{{W}}}footnote', f'{{{W}}}endnote'}:
                if (parent != node.tag+'Pr' or len(node) or set(node.attrib) != {f'{{{W}}}id'}
                        or not re.fullmatch(r'-?[0-9]+', node.get(f'{{{W}}}id', ''))):
                    return False
            if node.tag in {f'{{{W}}}documentProtection', f'{{{W}}}footnotePr', f'{{{W}}}endnotePr'}:
                if parent != f'{{{W}}}settings' or node.tag.endswith('documentProtection') and len(node):
                    return False
            pending.extend((child, node.tag) for child in node)
        return root is not None
    if role == 'webSettings':
        return _tags(root, W, {'webSettings', 'allowPNG', 'doNotSaveAsSingleFile'})
    if role == 'fontTable':
        return (_tags(root, W, {'fonts', 'font', 'charset', 'family', 'notTrueType', 'panose1', 'pitch', 'sig', 'altName'})
                and all(child.tag != f'{{{W}}}altName' or (parent.tag == f'{{{W}}}font'
                    and not len(child) and set(child.attrib) == {f'{{{W}}}val'} and child.get(f'{{{W}}}val', '').strip())
                    for parent in root.iter() for child in parent))
    if role == 'theme':
        return _tags(root, A, THEME_TAGS)
    if role == 'customXml':
        # Only the known empty bibliography store is auxiliary in this slice.
        return root is not None and root.tag == f'{{{B}}}Sources' and not len(root) and not (root.text or '').strip()
    if role == 'customXmlProps':
        return (_tags(root, C, {'datastoreItem', 'schemaRefs', 'schemaRef'})
                and all(node.get(f'{{{C}}}uri') == B for node in root.iter(f'{{{C}}}schemaRef')))
    if role == 'core':
        cp = 'http://schemas.openxmlformats.org/package/2006/metadata/core-properties'
        permitted = {f'{{{cp}}}{name}' for name in 'coreProperties category contentStatus contentType keywords lastModifiedBy lastPrinted revision version'.split()}
        permitted |= {f'{{http://purl.org/dc/elements/1.1/}}{name}' for name in 'creator description identifier language subject title'.split()}
        permitted |= {f'{{http://purl.org/dc/terms/}}{name}' for name in ('created', 'modified')}
        return root is not None and all(node.tag in permitted for node in root.iter())
    if role in {'app', 'custom'}:
        ns = f'http://schemas.openxmlformats.org/officeDocument/2006/{"extended-properties" if role == "app" else "custom-properties"}'
        names = 'Properties Template Manager Company Pages Words Characters PresentationFormat Lines Paragraphs Slides Notes TotalTime HiddenSlides MMClips ScaleCrop HeadingPairs TitlesOfParts LinksUpToDate CharactersWithSpaces SharedDoc HyperlinkBase HLinks HyperlinksChanged DigSig Application AppVersion DocSecurity' if role == 'app' else 'Properties property'
        permitted = {f'{{{ns}}}{name}' for name in names.split()}
        permitted |= {f'{{http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes}}{name}' for name in 'vector variant lpstr lpwstr bstr i1 i2 i4 i8 int ui1 ui2 ui4 ui8 uint r4 r8 decimal bool date filetime empty null'.split()}
        return root is not None and all(node.tag in permitted for node in root.iter())
    if role == 'thumbnail':
        end = data.rfind(b'\xff\xd9')
        # The installed Office template has one zero padding byte after EOI.
        if (not data.startswith(b'\xff\xd8\xff') or end < 0
                or len(data[end + 2:]) > 16 or any(data[end + 2:])):
            return False
        # Pillow is already locked by the existing PDF runtime. Verify the
        # declared preview image only; no extraction or visual-equivalence claim.
        from PIL import Image
        try:
            with Image.open(BytesIO(data)) as preview:
                if preview.format != 'JPEG' or max(preview.size) > 4096 or min(preview.size) < 1:
                    return False
                preview.verify()
            return True
        except (OSError, ValueError, Image.DecompressionBombError):
            return False
    return False


def _classify_auxiliaries(package, xml_parts):
    defaults, overrides = {}, {}
    for node in xml_parts['[Content_Types].xml']:
        if node.tag == f'{{{CT}}}Default':
            key, target = node.get('Extension'), defaults
        elif node.tag == f'{{{CT}}}Override':
            key, target = node.get('PartName'), overrides
        else:
            _unsupported()
        if not key or key in target or not node.get('ContentType'):
            _unsupported()
        target[key] = node.get('ContentType')

    def content_type(name):
        return overrides.get('/' + name, defaults.get(name.rsplit('.', 1)[-1]))

    # role, relationship type, content type, root, source. Names are derived
    # from validated relationship targets, never used as an auxiliary allowlist.
    prefix = 'application/vnd.openxmlformats-officedocument.'
    roles = [
        ('styles', O + 'styles', prefix + 'wordprocessingml.styles+xml', f'{{{W}}}styles', 'word/document.xml'),
        ('stylesWithEffects', 'http://schemas.microsoft.com/office/2007/relationships/stylesWithEffects', 'application/vnd.ms-word.stylesWithEffects+xml', f'{{{W}}}styles', 'word/document.xml'),
        ('footnotes', O + 'footnotes', prefix + 'wordprocessingml.footnotes+xml', f'{{{W}}}footnotes', 'word/document.xml'),
        ('endnotes', O + 'endnotes', prefix + 'wordprocessingml.endnotes+xml', f'{{{W}}}endnotes', 'word/document.xml'),
        ('settings', O + 'settings', prefix + 'wordprocessingml.settings+xml', f'{{{W}}}settings', 'word/document.xml'),
        ('webSettings', O + 'webSettings', prefix + 'wordprocessingml.webSettings+xml', f'{{{W}}}webSettings', 'word/document.xml'),
        ('fontTable', O + 'fontTable', prefix + 'wordprocessingml.fontTable+xml', f'{{{W}}}fonts', 'word/document.xml'),
        ('theme', O + 'theme', prefix + 'theme+xml', f'{{{A}}}theme', 'word/document.xml'),
        ('numbering', O + 'numbering', prefix + 'wordprocessingml.numbering+xml', f'{{{W}}}numbering', 'word/document.xml'),
        ('customXml', O + 'customXml', 'application/xml', f'{{{B}}}Sources', 'word/document.xml'),
        ('customXmlProps', O + 'customXmlProps', prefix + 'customXmlProperties+xml', f'{{{C}}}datastoreItem', None),
        ('core', R + '/metadata/core-properties', 'application/vnd.openxmlformats-package.core-properties+xml', '{http://schemas.openxmlformats.org/package/2006/metadata/core-properties}coreProperties', ''),
        ('app', O + 'extended-properties', prefix + 'extended-properties+xml', '{http://schemas.openxmlformats.org/officeDocument/2006/extended-properties}Properties', ''),
        ('custom', O + 'custom-properties', prefix + 'custom-properties+xml', '{http://schemas.openxmlformats.org/officeDocument/2006/custom-properties}Properties', ''),
        ('thumbnail', R + '/metadata/thumbnail', 'image/jpeg', None, ''),
    ]
    binding = any(node.tag == f'{{{W}}}dataBinding' for root in xml_parts.values() for node in root.iter())
    safe = {'[Content_Types].xml'}
    edges, rels, identified = [], {}, {}
    for name, root in xml_parts.items():
        if not name.endswith('.rels'):
            continue
        path = PurePosixPath(name)
        source = '' if name == '_rels/.rels' else str(path.parent.parent / path.name[:-5])
        valid = (content_type(name) == 'application/vnd.openxmlformats-package.relationships+xml'
                 and root.tag == f'{{{R}}}Relationships' and (source == '' or source in package))
        seen = set()
        for node in root:
            identifier, target = node.get('Id'), node.get('Target', '')
            if (node.tag != f'{{{R}}}Relationship' or not identifier or identifier in seen
                    or not node.get('Type') or not target or node.get('TargetMode') not in {None, 'Internal', 'External'}):
                valid = False
            seen.add(identifier)
            if node.get('TargetMode') == 'External' or any(char in target for char in '\\:%?#'):
                valid = False
                continue
            destination = posixpath.normpath(posixpath.join(posixpath.dirname(source), target))
            if destination.startswith('/') or destination not in package:
                valid = False
                continue
            edges.append((name, source, destination, node.get('Type')))
        rels[name] = valid
    for name, source, target, relationship in edges:
        if source == '' and target == 'word/document.xml' and relationship == O + 'officeDocument':
            continue
        root = xml_parts.get(target)
        matched = False
        for role, relation_type, mime, expected_root, expected_source in roles:
            if relationship != relation_type or content_type(target) != mime:
                continue
            if expected_source is not None and source != expected_source:
                continue
            if role == 'customXmlProps' and not any(edge[1] == 'word/document.xml' and edge[2] == source and edge[3] == O + 'customXml' for edge in edges):
                continue
            if expected_root is not None and (root is None or root.tag != expected_root):
                continue
            if role in {'customXml', 'customXmlProps'} and binding:
                continue
            if _auxiliary_content(role, root, package[target]):
                safe.add(target)
                identified.setdefault(role, []).append(target)
                matched = True
                break
        if not matched:
            rels[name] = False
    safe.update(name for name, valid in rels.items() if valid)
    return safe, identified


def _unsupported():
    raise ServiceError('FILE_UNSUPPORTED', 400)


def _xml(data):
    try:
        return ElementTree.fromstring(data, forbid_dtd=True, forbid_entities=True, forbid_external=True)
    except (ParseError, DefusedXmlException, ValueError, RecursionError):
        _unsupported()


def _empty_metadata_records(root, namespace, name, records):
    """OPC manifests/relations contain attributes and empty direct records only."""
    if (root.tag != f'{{{namespace}}}{name}' or root.attrib
            or (root.text or '').strip() or (root.tail or '').strip()):
        return False
    for node in root:
        schema = records.get(node.tag)
        if (schema is None or len(node) or (node.text or '').strip()
                or (node.tail or '').strip()):
            return False
        required, optional = schema
        if (not required <= node.attrib.keys() or not node.attrib.keys() <= required | optional
                or any(not value for value in node.attrib.values())):
            return False
    return True


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
        if not _empty_metadata_records(types, CT, 'Types', {
                f'{{{CT}}}Default': ({'Extension', 'ContentType'}, set()),
                f'{{{CT}}}Override': ({'PartName', 'ContentType'}, set())}):
            _unsupported()
        for name, root in xml_parts.items():
            if name.endswith('.rels') and not _empty_metadata_records(root, R, 'Relationships', {
                    f'{{{R}}}Relationship': ({'Id', 'Type', 'Target'}, {'TargetMode'})}):
                _unsupported()
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
    safe_metadata, identified = _classify_auxiliaries(package, xml_parts)
    style_names = identified.get('styles', [])
    effect_names = identified.get('stylesWithEffects', [])
    style_parts_present = any(root.tag == f'{{{W}}}styles' for root in xml_parts.values())
    style_unavailable = (len(style_names) > 1 or len(effect_names) > 1
                         or (style_parts_present and not style_names))
    # Untrusted declared style dependencies cannot safely supply default
    # visibility merely because the remaining paragraphs have no pStyle tag.
    style_unavailable |= any(root.tag == f'{{{W}}}styles' and name not in safe_metadata
                             for name, root in xml_parts.items())
    styles = [EffectiveStyles(xml_parts[style_names[0]] if style_names else None,
                              unavailable=style_unavailable)]
    styles.extend(EffectiveStyles(xml_parts[name], fallback=styles[0]) for name in effect_names)
    numbering_roots = [root for root in xml_parts.values() if root.tag == f'{{{W}}}numbering']
    inventory = []
    for name in package:
        if name == part:
            inventory.append(f'{name}:read')
        elif name in safe_metadata:
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
    parents = {child: parent for parent in document.iter() for child in parent}
    for child in document:
        if child is not body:
            unsupported.add(f'{part}:unknown_objects:{child.tag}:manual_required')
    if version.baseline_view == BaselineView.CONFIRMED_CUSTOM:
        unsupported.add(f'{part}:custom_baseline')
        quality.append('CUSTOM_BASELINE_ARTIFACT_REQUIRED')
        return ParseResult(version_id=version.id, anchors=(), pages=(), parts=tuple(inventory),
                           unsupported_parts=tuple(sorted(unsupported)), quality_issues=tuple(quality))

    def style_gap(path):
        unsupported.add(f'{part}:style_dependency:{path}:manual_required')
        issue = f'STYLE_DEPENDENCY_REQUIRES_CONFIRMATION:{path}'
        if issue not in quality:
            quality.append(issue)

    def text(node, paragraph, path):
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
        if local == 'r':
            try:
                hidden = any(style.run_hidden(paragraph, node) for style in styles)
            except StyleDependencyError:
                style_gap(path)
                return ''
            if hidden:
                unsupported.add(f'{part}:hidden:{path}:manual_required')
                return ''
            backgrounds = [document.find(f'{{{W}}}background')]
            table_color_uncertain = False
            ancestor = parents.get(paragraph)
            while ancestor is not None:
                if ancestor.tag in {f'{{{W}}}tc', f'{{{W}}}tbl'}:
                    name = 'tcPr' if ancestor.tag == f'{{{W}}}tc' else 'tblPr'
                    backgrounds.insert(1, ancestor.find(f'{{{W}}}{name}'))
                    if ancestor.tag == f'{{{W}}}tbl':
                        # Explicit and default conditional table colors are unresolved.
                        try:
                            chains = [n for style in styles for n in style.table_chain(ancestor)]
                            if any(n.tag in {f'{{{W}}}color', f'{{{W}}}shd'} or not n.tag.startswith(f'{{{W}}}')
                                   for root in chains for n in root.iter()):
                                table_color_uncertain = True
                        except StyleDependencyError:
                            style_gap(path)
                ancestor = parents.get(ancestor)
            if table_color_uncertain or any(style.color_uncertain(paragraph, node, backgrounds) for style in styles):
                issue = f'DOCX_VISIBILITY_UNCERTAIN:{path}'
                if issue not in quality: quality.append(issue)
                unsupported.add(f'{part}:visibility:{path}:manual_required')
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
        return ''.join(text(child, paragraph, path) for child in node)

    table_count = 0

    def blocks(parent, path, coords=None):
        nonlocal table_count
        counts = {}
        for child in parent:
            local = child.tag.removeprefix(f'{{{W}}}')
            counts[local] = counts.get(local, 0) + 1
            child_path = f'{path}/{local}[{counts[local]}]'
            if child.tag == f'{{{W}}}p':
                try:
                    if any(style.numbering_used(child, numbering_roots) for style in styles):
                        unsupported.add(f'{part}:numbering:{child_path}:manual_required')
                        quality.append(f'NUMBERING_NOT_SUPPORTED:{child_path}')
                except StyleDependencyError:
                    style_gap(child_path)
                    continue
                quote = text(child, child, child_path)
                if quote:
                    kwargs = {} if coords is None else dict(zip(('table', 'row', 'cell'), coords))
                    anchors.append(make_anchor(version, part, child_path, quote,
                                               AnchorKind.BODY_PARAGRAPH if coords is None else AnchorKind.TABLE_CELL, **kwargs))
            elif child.tag == f'{{{W}}}tbl':
                table = table_count
                table_count += 1
                try:
                    table_hidden = any(style.table_hidden(child) for style in styles)
                except StyleDependencyError:
                    style_gap(child_path)
                    continue
                if table_hidden:
                    unsupported.add(f'{part}:hidden:{child_path}:manual_required')
                    continue
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
