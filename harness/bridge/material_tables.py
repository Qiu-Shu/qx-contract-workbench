"""Group already validated, revision-aware DOCX paragraphs into physical rows."""
from io import BytesIO
import json
from zipfile import ZipFile

from docx_delivery import _w, _xml


def _ancestor(node, tag):
    return next((parent for parent in node.iterancestors() if parent.tag == _w(tag)), None)


def _number(properties, name, default, minimum=0):
    node = properties.find(_w(name)) if properties is not None else None
    value = int(node.get(_w('val'), '')) if node is not None else default
    if value < minimum:
        raise ValueError(name)
    return value


def _body_paths(root):
    """Match the adapter's numbered same-tag paths, including singleton nodes."""
    body = root.find(_w('body'))
    if body is None:
        return {}
    paths = {body: 'body'}
    for parent in body.iter():
        if parent not in paths:
            continue
        counts = {}
        for child in parent:
            if not isinstance(child.tag, str):
                continue
            local = child.tag.removeprefix(_w(''))
            counts[local] = counts.get(local, 0) + 1
            paths[child] = f'{paths[parent]}/{local}[{counts[local]}]'
    return paths


def docx_table_rows(raw, paragraphs):
    """Return (rows, covered_locations, warnings) from (text, location) pairs.

    Call only after package validation. Text comes exclusively from the supplied
    visible paragraphs. Columns are 1-based and inclusive; merged cells occupy
    one tab-delimited field. A continuation records its source owner but never
    copies the owner's text. Uncovered paragraphs must remain in the caller's
    output, including those in unsupported or malformed rows. source_locations
    lets the caller insert each row at its first visible paragraph. Nested-table
    outer rows remain paragraphs so text before/after inner rows stays ordered.
    """
    with ZipFile(BytesIO(raw)) as archive:
        root = _xml(archive.read('word/document.xml'))
    tree = root.getroottree()
    paths = _body_paths(root)
    visible = dict((location, value) for value, location in paragraphs)
    cell_paragraphs = {}
    for paragraph in root.iter(_w('p')):
        aliases = [tree.getpath(paragraph)]
        if paragraph in paths:
            aliases.append(paths[paragraph])
        location = next(('word/document.xml:' + alias for alias in aliases
                         if 'word/document.xml:' + alias in visible), None)
        if location is None:
            continue
        cell = _ancestor(paragraph, 'tc')
        if cell is not None:
            cell_paragraphs.setdefault(cell, []).append((visible[location], location))

    result, covered, warnings = [], set(), []
    for table in root.iter(_w('tbl')):
        active_merges = {}
        context=[]
        for cell in reversed([parent for parent in table.iterancestors() if parent.tag==_w('tc')]):
            for text,loc in cell_paragraphs.get(cell,[]):
                if text.strip():context.append(dict(value=text,location=loc,start=0,end=len(text),uncertain=False))
        for row in table.iter(_w('tr')):
            if _ancestor(row, 'tbl') is not table:
                continue
            location = 'word/document.xml:' + paths.get(row, tree.getpath(row))
            cells = [cell for cell in row.iter(_w('tc'))
                     if _ancestor(cell, 'tr') is row and _ancestor(cell, 'tbl') is table]
            try:
                before = _number(row.find(_w('trPr')), 'gridBefore', 0)
                after = _number(row.find(_w('trPr')), 'gridAfter', 0)
                column, metadata, next_merges = before + 1, [], {}
                row_warnings = []
                for cell in cells:
                    properties = cell.find(_w('tcPr'))
                    span = _number(properties, 'gridSpan', 1, 1)
                    if properties is not None and properties.find(_w('hMerge')) is not None:
                        raise ValueError('hMerge')
                    merge = properties.find(_w('vMerge')) if properties is not None else None
                    mode = merge.get(_w('val'), 'continue') if merge is not None else None
                    if mode not in {None, 'restart', 'continue'}:
                        raise ValueError('vMerge')
                    extent = (column, column + span - 1)
                    owner = None
                    if mode == 'restart':
                        owner = 'word/document.xml:' + paths.get(cell, tree.getpath(cell))
                    elif mode == 'continue':
                        owner = active_merges.get(extent)
                        if owner is None:
                            row_warnings.append(location + '：纵向合并起点不明，保留本格文字，请对照原件。')
                    if mode is not None and owner is not None:
                        next_merges[extent] = owner
                    metadata.append({'start_col': extent[0], 'end_col': extent[1],
                                     'vmerge': mode, 'owner': owner})
                    column += span
            except (ValueError, OverflowError):
                warnings.append(location + '：表格网格无法可靠解释，已保留原段落，请对照原件。')
                active_merges = {}
                continue
            active_merges = next_merges
            warnings.extend(row_warnings)
            if len(cells) < 2 and not any(c['end_col']>c['start_col'] for c in metadata):
                continue
            if any(True for _ in row.iter(_w('tbl'))):
                warnings.append(location + '：嵌套表格外层保留原段落顺序，内层表格单独提取。')
                continue
            texts=['\n'.join(text for text, _ in cell_paragraphs.get(cell, [])) for cell in cells]
            value = '\t'.join(texts)
            if not value.strip():
                continue
            grid = {'grid_before': before, 'grid_after': after, 'cells': metadata}
            if context:grid['table_context']=context
            offset=0
            for cell,text in zip(metadata,texts):
                cell.update(text_start=offset,text_end=offset+len(text));offset+=len(text)+1
            properties=row.find(_w('trPr'))
            grid['header_row']=properties is not None and properties.find(_w('tblHeader')) is not None
            sources = [loc for cell in cells for _, loc in cell_paragraphs.get(cell, [])]
            result.append({'value': value, 'location': location + ':grid:' +
                           json.dumps(grid, ensure_ascii=False, separators=(',', ':')),
                           'source_locations': sources})
            covered.update(sources)
    from material_headers import annotate_headers
    annotate_headers(result)
    return result, covered, warnings
