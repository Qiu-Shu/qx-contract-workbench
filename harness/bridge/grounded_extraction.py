"""Local LangExtract alignment of existing model quotes, scoped to a case.

No provider is constructed: this adapter never makes a second model request.
"""
import hashlib
import re


def ground_case_extractions(cases, case_id, path, source_sha256, chunk, extractions):
    if not isinstance(source_sha256, str) or not re.fullmatch(r'[0-9a-f]{64}', source_sha256):
        raise ValueError('请先读取本案材料，提供返回的 source_sha256。')
    if type(chunk) is not int or chunk < 0:
        raise ValueError('chunk 必须是读取材料得到的非负片段编号。')
    if not isinstance(extractions, list) or not 1 <= len(extractions) <= 30:
        raise ValueError('每次核对1至30项原文摘录。')
    for item in extractions:
        if not isinstance(item, dict) or set(item) != {'label', 'quote'}:
            raise ValueError('每项只能包含 label 和 quote；法律评价请单独保存为待核分析。')
        for key, maximum in (('label', 80), ('quote', 2000)):
            if not isinstance(item[key], str) or not item[key].strip() or len(item[key]) > maximum:
                raise ValueError('label 为1至80字；quote 为1至2000字逐字原文。')
    # Authorize the case before any index query. PDF ordinals are sparse identifiers.
    view = cases.read_material(case_id, path, start=0, limit=1)
    if view.get('sha256') != source_sha256 or not view.get('chunks'):
        raise ValueError('材料版本变化或片段不存在，请重新读取本案材料。')
    with cases.store.db() as db:
        offset = db.execute('SELECT COUNT(*) FROM chunks WHERE path=? AND ordinal<?',
                            (view['path'], chunk)).fetchone()[0]
    view = cases.read_material(case_id, path, start=offset, limit=1)
    if view.get('sha256') != source_sha256 or not view.get('chunks'):
        raise ValueError('材料版本变化或片段不存在，请重新读取本案材料。')
    piece = view['chunks'][0]
    if piece['ordinal'] != chunk or len(piece['text']) > 16000:
        raise ValueError('片段不存在或过长，请先拆分材料再核对。')
    source = cases.store.safe(path)
    def current_digest():
        with source.open('rb') as stream:
            return hashlib.file_digest(stream, 'sha256').hexdigest()
    if current_digest() != source_sha256:
        raise ValueError('原件已变化，请重新导入、解析并关联本案。')
    try:
        from langextract.core.data import Extraction
        from langextract.resolver import Resolver
    except ImportError:
        raise ValueError('本机未安装 LangExtract，请安装项目的候选依赖后重试。') from None
    resolver = Resolver()
    text = piece['text']
    rows = []
    for item in extractions:
        quote = item['quote']
        # Token matching alone can ignore case/spacing; require literal equality too.
        aligned = list(resolver.align([Extraction(extraction_class=item['label'], extraction_text=quote)],
                       text, token_offset=0, char_offset=0,
                       enable_fuzzy_alignment=False, accept_match_lesser=False))
        interval = aligned[0].char_interval if aligned else None
        first = text.find(quote)
        ambiguous = first >= 0 and text.find(quote, first + 1) >= 0
        exact = (interval is not None and text[interval.start_pos:interval.end_pos] == quote)
        status = 'ambiguous' if ambiguous else 'matched' if exact else 'unmatched'
        rows.append({**item, 'status': status, 'path': view['path'], 'sha256': source_sha256,
                     'chunk': chunk, 'page': piece['page'], 'location': piece['location'],
                     'start': interval.start_pos if status == 'matched' else None,
                     'end': interval.end_pos if status == 'matched' else None})
    if current_digest() != source_sha256:
        raise ValueError('核对期间原件变化，请重新读取；本次结果未保存。')
    return {'case_id': case_id, 'engine': 'langextract', 'mode': 'local_alignment',
            'material_version': view.get('material_version'), 'extractions': rows,
            'legal_verified': False, 'saved': False,
            'notice': '仅核对本片段逐字出处；不证明真实性、法律关系或证明力。重复原句需补充上下文重新定位。'
                      '保存时用 record_case_note 并原样传递引用结果（含start/end）；'
                      '只有matched可称已定位，其他项保持待核，不能删去位置字段后改称已匹配。'}
