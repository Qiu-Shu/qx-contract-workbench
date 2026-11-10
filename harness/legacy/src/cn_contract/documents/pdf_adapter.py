"""Native PDF text, characters, tables and coordinates on every page."""
from io import BytesIO
import math
from uuid import UUID

import pdfplumber
import pdfplumber.pdf as pdf_api
from pdfminer.pdfpage import PDFPage

from ..domain import AnchorKind, ParseResult
from ..security import ServiceError
from .anchors import make_anchor
from .ocr_adapter import unavailable
from .pdf_visibility import VisibilityAggregator, VisibilityInterpreter, outside_visible_page


def parse_pdf(data, version, settings):
    version_id = version if isinstance(version, UUID) else version.id
    anchors, parts, unsupported, quality, pages = [], [], [], [], []
    try:
        # pdfplumber.PDF.pages eagerly materializes the entire file, and its
        # close() flushes the page cache then materializes it again. Own the input
        # stream and explicitly close each bounded page to avoid that path.
        with BytesIO(data) as stream:
            pdf = pdfplumber.open(stream)
            if pdf.doc.encryption:
                raise ServiceError('FILE_UNSUPPORTED', 400)
            doctop = 0
            for number, native_page in enumerate(PDFPage.create_pages(pdf.doc), 1):
                if number > settings.parse_max_pages_per_file:
                    raise ServiceError('FILE_LIMIT', 413)
                page = pdf_api.Page(pdf, native_page, page_number=number, initial_doctop=doctop)
                doctop += page.height
                pages.append(number)
                page_extras = [key for key in ('Annots', 'AA', 'A', 'AF', 'PieceInfo', 'PresSteps')
                               if page.page_obj.attrs.get(key)]
                if 'Annots' in page_extras:
                    unsupported.append(f'page:{number}:annotations')
                    quality.append(f'ANNOTATIONS_NOT_READ:page:{number}')
                if any(key != 'Annots' for key in page_extras):
                    unsupported.append(f'page:{number}:interactive_or_embedded_parts')
                device = VisibilityAggregator(pdf.rsrcmgr, pageno=number, laparams=pdf.laparams)
                VisibilityInterpreter(pdf.rsrcmgr, device).process_page(page.page_obj)
                page._layout = device.get_result()
                if page.page_obj.attrs.get('Group'):
                    device.visual_reasons.add('PDF_DRAWING_EFFECT_REQUIRES_CONFIRMATION')
                rendering_requires_review = bool(device.visual_reasons)
                if rendering_requires_review:
                    suffix = 'text_rendering' if 'TEXT_RENDERING_REQUIRES_CONFIRMATION' in device.visual_reasons else 'visual_check'
                    unsupported.append(f'page:{number}:{suffix}')
                    quality.extend(f'{reason}:page:{number}' for reason in sorted(device.visual_reasons))
                chars = page.chars
                quote = page.extract_text(layout=False) or ''
                if not chars or not quote.strip():
                    status, issue = unavailable(number)
                    parts.append(status)
                    unsupported.append(f'page:{number}')
                    quality.append(issue)
                    page.close()
                    continue
                bbox = (min(char['x0'] for char in chars), min(char['top'] for char in chars),
                        max(char['x1'] for char in chars), max(char['bottom'] for char in chars))
                if not all(math.isfinite(value) for value in bbox) or min(bbox) < 0 or bbox[2] <= bbox[0] or bbox[3] <= bbox[1]:
                    parts.append(f'page:{number}:manual')
                    unsupported.append(f'page:{number}:invalid_coordinates')
                    quality.append(f'PDF_COORDINATES_UNRELIABLE:page:{number}')
                    page.close()
                    continue
                low_quality = '\ufffd' in quote or '(cid:' in quote or any(ord(char) < 32 and char not in '\n\t\r' for char in quote)
                manual = bool(page_extras) or low_quality or rendering_requires_review
                if outside_visible_page(chars, page):
                    manual = True
                    quality.append(f'PDF_TEXT_OUTSIDE_VISIBLE_PAGE:page:{number}')
                    unsupported.append(f'page:{number}:visible_page_bounds')
                if low_quality:
                    quality.append(f'TEXT_QUALITY_REQUIRES_CONFIRMATION:page:{number}')
                    unsupported.append(f'page:{number}:text_quality')
                if page.images:
                    manual = True
                    quality.append(f'VISIBLE_IMAGE_TEXT_NOT_VERIFIED:page:{number}')
                    unsupported.append(f'page:{number}:images')
                parts.append(f'page:{number}:{"manual" if manual else "read"}')
                anchors.append(make_anchor(version, f'page:{number}', f'page[{number}]/text', quote,
                                           AnchorKind.PDF_SPAN, page=number, bbox=bbox))
                for table_number, table in enumerate(page.find_tables()):
                    cells = table.extract()
                    for row_number, row in enumerate(table.rows):
                        for cell_number, cell_bbox in enumerate(row.cells):
                            value = cells[row_number][cell_number]
                            if value and cell_bbox:
                                anchors.append(make_anchor(version, f'page:{number}',
                                                           f'page[{number}]/table[{table_number}]/row[{row_number}]/cell[{cell_number}]',
                                                           value, AnchorKind.PDF_SPAN, page=number, bbox=cell_bbox))
                page.close()
            catalog = pdf.doc.catalog
            if any(key in catalog for key in ('OpenAction', 'AA', 'AcroForm', 'Names')):
                unsupported.append('pdf:interactive_or_embedded_parts')
                parts.append('pdf:interactive_or_embedded_parts:unsupported')
            if not pages:
                raise ServiceError('FILE_UNSUPPORTED', 400)
            pdf.flush_cache()
        return ParseResult(version_id=version_id, anchors=tuple(anchors), pages=tuple(pages), parts=tuple(parts),
                           unsupported_parts=tuple(unsupported), quality_issues=tuple(quality))
    except ServiceError:
        raise
    except Exception:
        # Third-party parser diagnostics may contain file bytes; expose no details.
        raise ServiceError('FILE_UNSUPPORTED', 400) from None
