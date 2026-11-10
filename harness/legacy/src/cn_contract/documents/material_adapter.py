"""Local attachment text readers. Extractors never evaluate macros or follow links."""
from io import BytesIO
from pathlib import Path, PurePath
from tempfile import TemporaryDirectory
import zipfile

from ..domain import AnchorKind, ParseResult
from ..security import ServiceError
from .anchors import make_anchor

TEXT_KINDS = {'txt', 'md', 'csv', 'tsv', 'json', 'html', 'htm', 'rtf'}
IMAGE_KINDS = {'png', 'jpg', 'jpeg', 'webp', 'gif', 'bmp', 'tif', 'tiff'}
ZIP_PARTS = {'docx': 'word/document.xml', 'xlsx': 'xl/workbook.xml',
             'pptx': 'ppt/presentation.xml', 'odt': 'content.xml',
             'ods': 'content.xml', 'odp': 'content.xml'}
OLE_PARTS = {'doc': 'WordDocument', 'xls': 'Workbook', 'ppt': 'PowerPoint Document'}


def decode_text(data):
    encodings = ['utf-8-sig', 'gb18030']
    if data.startswith((b'\xff\xfe', b'\xfe\xff')):
        encodings.insert(0, 'utf-16')
    for encoding in encodings:
        try:
            value = data.decode(encoding)
            if any(ord(c) < 32 and c not in '\n\r\t\f' for c in value):
                continue
            return value
        except UnicodeDecodeError:
            continue
    raise ServiceError('FILE_UNSUPPORTED', 400)


def material_type(data, name, mime):
    from ..domain import ASSISTANT_MATERIAL_MIME_EXT
    kind = PurePath(name).suffix.lower().lstrip('.')
    if '.' + kind not in ASSISTANT_MATERIAL_MIME_EXT.get(mime, ()):
        raise ServiceError('FILE_UNSUPPORTED', 400)
    try:
        if kind in TEXT_KINDS:
            value = decode_text(data)
            if kind == 'rtf' and not value.lstrip().startswith('{\\rtf'):
                raise ValueError('rtf signature')
        elif kind in ZIP_PARTS:
            with zipfile.ZipFile(BytesIO(data)) as archive:
                if ZIP_PARTS[kind] not in archive.namelist():
                    raise ValueError('package type')
                if kind in {'odt', 'ods', 'odp'}:
                    if archive.getinfo('mimetype').file_size > 256 or archive.read('mimetype').decode() != mime:
                        raise ValueError('package type')
        elif kind in OLE_PARTS:
            import olefile
            with olefile.OleFileIO(BytesIO(data)) as document:
                if not document.exists(OLE_PARTS[kind]) and not (kind == 'xls' and document.exists('Book')):
                    raise ValueError('compound file type')
        elif kind == 'pdf':
            if not data.startswith(b'%PDF-'):
                raise ValueError('pdf signature')
        elif kind in IMAGE_KINDS:
            from PIL import Image
            with Image.open(BytesIO(data)) as image:
                expected = {'jpg': 'JPEG', 'jpeg': 'JPEG', 'tif': 'TIFF', 'tiff': 'TIFF'}.get(kind, kind.upper())
                if image.format != expected:
                    raise ValueError('image type')
                image.verify()
        else:
            raise ValueError('unknown format')
    except ServiceError:
        raise
    except Exception:
        raise ServiceError('FILE_UNSUPPORTED', 400) from None
    return kind


def _check_package(data, settings):
    # Third-party readers only receive bounded archives; none extracts paths to disk.
    with zipfile.ZipFile(BytesIO(data)) as archive:
        entries = archive.infolist()
        if len(entries) > 20000 or sum(i.file_size for i in entries) > settings.archive_uncompressed_max_mib * 1024**2:
            raise ServiceError('FILE_LIMIT', 413)
        if any(i.flag_bits & 1 for i in entries):
            raise ServiceError('FILE_UNSUPPORTED', 400)


def parse_material(data, name, version, settings):
    kind = PurePath(name).suffix.lower().lstrip('.')
    if kind == 'pdf':
        return parse_pdf_with_ocr(data, version, settings)
    if kind in IMAGE_KINDS:
        return parse_image(data, version, settings)
    if kind in ZIP_PARTS:
        _check_package(data, settings)
    anchors, parts, quality = [], [], []

    def add(part, value, path=None):
        if value and value.strip():
            anchors.append(make_anchor(version, part, path or f'text[{len(anchors)}]', value, AnchorKind.OTHER))
            if part not in parts:
                parts.append(part)

    if kind in TEXT_KINDS:
        value = decode_text(data)
        if kind == 'html' or kind == 'htm':
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(value, 'html.parser')
            for node in soup(['script', 'style', 'template', 'noscript']):
                node.decompose()
            value = soup.get_text('\n')
        elif kind == 'rtf':
            from striprtf.striprtf import rtf_to_text
            value = rtf_to_text(value)
        for number, line in enumerate(value.splitlines(), 1):
            add('text', line, f'line[{number}]')
    elif kind in {'xls', 'xlsx', 'ods'}:
        from python_calamine import CalamineWorkbook
        with CalamineWorkbook.from_filelike(BytesIO(data)) as book:
            for index, name in enumerate(book.sheet_names):
                sheet = book.get_sheet_by_name(name)
                add(f'sheet:{index + 1}', name, 'name')
                for row_number, row in enumerate(sheet.iter_rows(), 1):
                    values = ['' if cell is None else str(cell) for cell in row]
                    if any(values):
                        add(f'sheet:{index + 1}', '\t'.join(values), f'row[{row_number}]')
        quality.append('SPREADSHEET_VALUES_ONLY_FORMULAS_NOT_EXECUTED')
    elif kind in {'ppt', 'pptx'}:
        if kind == 'ppt':
            from ppt2pptx import convert
            with TemporaryDirectory(prefix='qx-ppt-') as directory:
                source, target = Path(directory) / 'input.ppt', Path(directory) / 'output.pptx'
                source.write_bytes(data)
                convert(str(source), str(target))
                data = target.read_bytes()
                _check_package(data, settings)
            quality.append('LEGACY_PRESENTATION_TEXT_EXTRACTION')
        from pptx import Presentation
        presentation = Presentation(BytesIO(data))
        if len(presentation.slides) > settings.parse_max_pages_per_file:
            raise ServiceError('FILE_LIMIT', 413)

        def shapes_text(shapes, part):
            for shape in shapes:
                if shape.has_text_frame:
                    add(part, shape.text)
                if shape.has_table:
                    for row in shape.table.rows:
                        add(part, '\t'.join(cell.text for cell in row.cells))
                if hasattr(shape, 'shapes'):
                    shapes_text(shape.shapes, part)

        for index, slide in enumerate(presentation.slides, 1):
            shapes_text(slide.shapes, f'slide:{index}')
            if slide.has_notes_slide:
                frame = slide.notes_slide.notes_text_frame
                if frame:
                    add(f'slide:{index}:notes', frame.text)
        quality.append('PRESENTATION_TEXT_ONLY')
    elif kind in {'odt', 'odp'}:
        from odf.opendocument import load
        from odf import teletype
        from odf.namespaces import TEXTNS
        document = load(BytesIO(data))
        # getElementsByType for both tags separately would reorder headings and paragraphs.
        def walk(node):
            if getattr(node, 'qname', None) in {(TEXTNS, 'p'), (TEXTNS, 'h')}:
                add('content.xml', teletype.extractText(node))
            else:
                for child in getattr(node, 'childNodes', ()):
                    walk(child)
        walk(document.body)
        quality.append('OPENDOCUMENT_TEXT_ONLY')
    elif kind == 'doc':
        from legacy_doc import extract_text, ExtractionOptions
        result = extract_text(data, options=ExtractionOptions(
            max_file_bytes=settings.upload_max_file_mib * 1024**2))
        for index, line in enumerate(result.text.splitlines(), 1):
            add('WordDocument', line, f'paragraph[{index}]')
        quality.append('LEGACY_WORD_TEXT_ONLY_REVISIONS_NOT_RESOLVED')
    else:
        raise ServiceError('FILE_UNSUPPORTED', 400)
    if not anchors:
        quality.append('NO_READABLE_TEXT')
    return ParseResult(version_id=version, anchors=tuple(anchors), pages=(), parts=tuple(parts),
                       unsupported_parts=(), quality_issues=tuple(quality))


def parse_image(data, version, settings):
    from PIL import Image, ImageOps
    from .material_ocr import recognize
    anchors, parts, quality = [], [], ['OCR_IS_UNVERIFIED']
    with Image.open(BytesIO(data)) as image:
        count = getattr(image, 'n_frames', 1)
        if count > settings.parse_max_pages_per_file:
            raise ServiceError('FILE_LIMIT', 413)
        for index in range(count):
            image.seek(index)
            frame = ImageOps.exif_transpose(image).convert('RGB')
            frame.thumbnail((2400, 2400))
            blocks = recognize(frame)
            part = f'image:{index + 1}'
            parts.append(part)
            for number, (_, value, _) in enumerate(blocks):
                anchors.append(make_anchor(version, part, f'ocr[{number}]', value, AnchorKind.OTHER))
    if not anchors:
        quality.append('NO_READABLE_TEXT')
    return ParseResult(version_id=version, anchors=tuple(anchors), pages=(), parts=tuple(parts),
                       unsupported_parts=(), quality_issues=tuple(quality))


def parse_pdf_with_ocr(data, version, settings):
    from .pdf_adapter import parse_pdf
    from .material_ocr import recognize
    result = parse_pdf(data, version, settings)
    missing = [page for page in result.pages if not any(a.page == page for a in result.anchors)
               or f'VISIBLE_IMAGE_TEXT_NOT_VERIFIED:page:{page}' in result.quality_issues]
    if not missing:
        return result
    import pypdfium2 as pdfium
    anchors, parts = list(result.anchors), list(result.parts)
    unsupported, quality = list(result.unsupported_parts), list(result.quality_issues)
    with pdfium.PdfDocument(data) as document:
        for number in missing:
            page = document[number - 1]
            try:
                width, height = page.get_size()
                scale = min(2, 2400 / max(width, height))
                bitmap = page.render(scale=scale)
                try:
                    image = bitmap.to_pil().convert('RGB')
                    blocks = recognize(image)
                    for index, (box, value, _) in enumerate(blocks):
                        xs, ys = [p[0] for p in box], [p[1] for p in box]
                        bbox = (max(0, min(xs) * width / image.width), max(0, min(ys) * height / image.height),
                                max(xs) * width / image.width, max(ys) * height / image.height)
                        anchors.append(make_anchor(version, f'page:{number}', f'page[{number}]/ocr[{index}]',
                            value, AnchorKind.PDF_SPAN, page=number, bbox=bbox))
                finally:
                    bitmap.close()
            finally:
                page.close()
            quality = [item for item in quality if item != f'OCR_NOT_DEPLOYED:page:{number}']
            quality.append(f'OCR_IS_UNVERIFIED:page:{number}')
            if blocks:
                unsupported = [item for item in unsupported if item != f'page:{number}']
                parts = [item for item in parts if item != f'page:{number}:unsupported']
                parts.append(f'page:{number}:ocr')
            else:
                quality.append(f'NO_READABLE_TEXT:page:{number}')
    return result.model_copy(update={'anchors': tuple(anchors), 'parts': tuple(parts),
        'unsupported_parts': tuple(unsupported), 'quality_issues': tuple(quality)})
