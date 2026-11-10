"""Read XLSX values and provenance locally, without evaluating formulas or links."""
from io import BytesIO
import json
import posixpath
import re
from zipfile import ZipFile

from defusedxml import ElementTree as XML


def _local(tag):
    return tag.rsplit('}', 1)[-1]


def _child(node, name):
    return next((item for item in node if _local(item.tag) == name), None)


def _rich_text(node):
    if node is None:
        return ''
    return ''.join(item.text or '' for child in node
                   for item in ([child] if _local(child.tag) == 't' else
                                list(child) if _local(child.tag) == 'r' else [])
                   if _local(item.tag) == 't')


def _ref(value):
    match = re.fullmatch(r'([A-Z]{1,3})([1-9][0-9]*)', value or '')
    if not match:
        raise ValueError('单元格坐标无效')
    column = 0
    for letter in match[1]:
        column = column * 26 + ord(letter) - 64
    row = int(match[2])
    if column > 16384 or row > 1048576:
        raise ValueError('单元格坐标超出 XLSX 范围')
    return column, row


def _letters(column):
    result = ''
    while column:
        column, digit = divmod(column - 1, 26)
        result = chr(65 + digit) + result
    return result


def _location(base, metadata):
    return base + ':layout:' + json.dumps(metadata, ensure_ascii=False, separators=(',', ':'))


def _part(target):
    path = posixpath.normpath(target.lstrip('/') if target.startswith('/') else posixpath.join('xl', target))
    if not path.startswith('xl/') or '\\' in path or ':' in path:
        raise ValueError('工作簿部件路径无效')
    return path


def _date_format(number, code):
    if number in set(range(14, 23)) | set(range(27, 37)) | {45, 46, 47} | set(range(50, 59)):
        return True
    code = re.sub(r'"[^"]*"|\\.|_.|\*.', '', code)
    code = re.sub(r'\[(?![hms]+\])[^\]]*\]', '', code, flags=re.I)
    return bool(re.search(r'[ymdhs]', code, re.I))


def xlsx_rows(raw, settings):
    """Return ({value, location} rows, warnings); numeric/date caches stay literal.

    Each sheet has a metadata row with its name, merged ranges and hidden columns.
    Data rows preserve A-based tab offsets and cell references, including blank cells.
    """
    from cn_contract.documents.material_adapter import _check_package
    _check_package(raw, settings)
    rows, warnings = [], []
    with ZipFile(BytesIO(raw)) as archive:
        workbook = XML.fromstring(archive.read('xl/workbook.xml'))
        relationships = XML.fromstring(archive.read('xl/_rels/workbook.xml.rels'))
        rels = {rel.get('Id'): rel for rel in relationships}
        shared, styles = [], []
        for kind in ('sharedStrings', 'styles'):
            rel = next((item for item in relationships if item.get('Type', '').endswith('/' + kind)), None)
            fallback = f'xl/{kind}.xml'
            if rel is None and fallback not in archive.namelist():
                continue
            try:
                if rel is not None and rel.get('TargetMode', '').lower() == 'external':
                    raise ValueError('不读取外部部件')
                root = XML.fromstring(archive.read(_part(rel.get('Target', '')) if rel is not None else fallback))
                if kind == 'sharedStrings':
                    shared = [_rich_text(item) for item in root if _local(item.tag) == 'si']
                else:
                    formats = {int(item.get('numFmtId')): item.get('formatCode', '')
                               for parent in root if _local(parent.tag) == 'numFmts' for item in parent}
                    for parent in root:
                        if _local(parent.tag) == 'cellXfs':
                            for item in parent:
                                number = int(item.get('numFmtId', '0'))
                                styles.append(dict(number_format_id=number, number_format=formats.get(number, ''),
                                                   date_format=_date_format(number, formats.get(number, ''))))
            except Exception as exc:
                warnings.append(f'XLSX {kind} 读取不完整（{type(exc).__name__}），其他可读单元格继续保留。')
        if any(item.get('Type', '').endswith('/externalLink') for item in relationships):
            warnings.append('工作簿含外部链接；仅读取文件已有缓存，未访问链接或刷新数据。')
        properties = next((item for item in workbook if _local(item.tag) == 'workbookPr'), None)
        date1904 = properties is not None and properties.get('date1904', '0') in {'1', 'true'}
        sheets = next((item for item in workbook if _local(item.tag) == 'sheets'), [])
        for sheet_index, sheet in enumerate(sheets, 1):
            name = sheet.get('name', '')
            base = f'xlsx:sheet:{sheet_index}'
            sheet_info = dict(sheet_name=name, sheet_state=sheet.get('state', 'visible'),
                              merged_ranges=[], hidden_columns=[], date1904=date1904)
            header = dict(value=name, location='')
            rows.append(header)
            try:
                relationship_id = next((value for key, value in sheet.attrib.items() if _local(key) == 'id'), None)
                rel = rels.get(relationship_id)
                if rel is None or not rel.get('Type', '').endswith('/worksheet'):
                    raise ValueError('工作表关系缺失或类型不支持')
                if rel.get('TargetMode', '').lower() == 'external':
                    raise ValueError('不读取外部工作表')
                part = _part(rel.get('Target', ''))
                sheet_info['part'] = part
                previous_row = 0
                with archive.open(part) as stream:
                    for event, element in XML.iterparse(stream, events=('end',)):
                        tag = _local(element.tag)
                        if tag == 'mergeCell':
                            sheet_info['merged_ranges'].append(element.get('ref', ''))
                        elif tag == 'col' and element.get('hidden', '0') in {'1', 'true'}:
                            sheet_info['hidden_columns'].append(dict(element.attrib))
                        elif tag == 'row':
                            try:
                                row_number = int(element.get('r', str(previous_row + 1)))
                                if not 1 <= row_number <= 1048576:
                                    raise ValueError('行号无效')
                            except (ValueError, TypeError):
                                warnings.append(f'{base} 行号无效，按有效单元格坐标保留可读内容。')
                                valid = []
                                for cell in element:
                                    try:
                                        valid.append(_ref(cell.get('r'))[1])
                                    except (ValueError, TypeError):
                                        pass
                                row_number = valid[0] if valid else previous_row + 1
                            previous_row = row_number
                            values, cells, previous_column = {}, [], 0
                            for cell in element:
                                if _local(cell.tag) != 'c':
                                    continue
                                reference = cell.get('r', '')
                                try:
                                    if not reference:
                                        reference = f'{_letters(previous_column + 1)}{row_number}'
                                    column, cell_row = _ref(reference)
                                    previous_column = column
                                    kind = cell.get('t', 'n')
                                    value_node, formula = _child(cell, 'v'), _child(cell, 'f')
                                    cached = value_node is not None and value_node.text is not None
                                    value = value_node.text or '' if value_node is not None else ''
                                    info = dict(ref=reference, type=kind, formula=formula is not None,
                                                cached=cached, style=cell.get('s'))
                                    if cell_row != row_number:
                                        warnings.append(f'{base}:{reference} 与所在行号不一致，已保留原坐标，请核对。')
                                    if kind == 's' and value:
                                        index = int(value)
                                        if not 0 <= index < len(shared):
                                            raise ValueError('共享字符串索引无效')
                                        value = shared[index]
                                    elif kind == 'inlineStr':
                                        value = _rich_text(_child(cell, 'is'))
                                    elif kind == 'b' and value in {'0', '1'}:
                                        value = 'TRUE' if value == '1' else 'FALSE'
                                    if formula is not None:
                                        info['formula_attributes'] = dict(formula.attrib)
                                        info['cache_status'] = 'present_unverified' if cached else 'missing'
                                        warnings.append(f'{base}:{reference} 公式未执行；' +
                                                        ('已保留已有缓存，结果可能过期。' if cached else '缺少缓存结果，未推算数值。'))
                                    if cell.get('s') is not None:
                                        try:
                                            style_index = int(cell.get('s'))
                                            if not 0 <= style_index < len(styles):
                                                raise ValueError('样式索引无效')
                                            info.update(styles[style_index])
                                        except (ValueError, TypeError):
                                            warnings.append(f'{base}:{reference} 样式无法识别，已保留原始缓存值。')
                                    if value and (kind == 'd' or info.get('date_format')):
                                        warnings.append(f'{base}:{reference} 日期或时间值保留原始内容（含序列值），未自动转换。')
                                    if kind == 'e' and value:
                                        warnings.append(f'{base}:{reference} 含电子表格错误值 {value}。')
                                    cells.append(info)
                                    if column in values:
                                        warnings.append(f'{base}:{reference} 坐标重复，重复内容已单独保留。')
                                        if value:
                                            rows.append(dict(value=value, location=_location(base + f':row:{row_number}:duplicate', info)))
                                    else:
                                        values[column] = value
                                except (ValueError, TypeError, IndexError) as exc:
                                    warnings.append(f'{base}:{reference or "unknown-cell"} 单元格无法解码（{exc}），其他单元格已保留。')
                            if any(value.strip() for value in values.values()):
                                last = max(column for column, value in values.items() if value)
                                positions={};offset=0
                                for column in range(1,last+1):
                                    value=values.get(column,'');positions[column]=(offset,offset+len(value));offset+=len(value)+1
                                for cell in cells:
                                    column,_=_ref(cell['ref'])
                                    if column in positions:cell.update(column=column,text_start=positions[column][0],text_end=positions[column][1])
                                metadata = dict(sheet_name=name, part=part, row=row_number,
                                                sheet_state=sheet_info['sheet_state'],
                                                row_hidden=element.get('hidden', '0') in {'1', 'true'}, cells=cells)
                                rows.append(dict(value='\t'.join(values.get(column, '') for column in range(1, last + 1)),
                                                 location=_location(base + f':row:{row_number}', metadata)))
                            element.clear()
            except Exception as exc:
                warnings.append(f'{base}（{name}）读取不完整（{type(exc).__name__}），已保留此前及其他工作表的可读内容。')
            header['location'] = _location(base + ':metadata', sheet_info)
    from material_headers import annotate_headers
    annotate_headers(rows)
    return rows, warnings
