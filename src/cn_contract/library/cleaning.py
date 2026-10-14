"""Conservative derived values. Never edits or supplies missing original text."""
from datetime import date
import re
import unicodedata

FIELDS = {
    'title': '标题', 'case_no': '案号', 'court': '法院', 'document_type': '文书类型',
    'case_type': '案件类型', 'procedure': '审理程序', 'decision_date': '判决时间',
    'publication_date': '发布时间', 'filing_date': '受理时间', 'case_level': '案例级别',
    'court_level': '法院级别', 'cause': '案由', 'province': '省', 'city': '市',
    'decision_year': '判决年份', 'original_id': '原始ID', 'source_url': '原始链接',
}


def metadata_value(value):
    if not isinstance(value, str):
        return None
    value = value.strip()
    return None if not value or value.casefold() in ('none', 'null', 'nan') else value


def normalize_case(value):
    return re.sub(r'\s+', '', unicodedata.normalize('NFKC', value)) if value else None


def clean_case(values: dict[str, str]) -> dict:
    fields = {key: metadata_value(values.get(original)) for key, original in FIELDS.items()}
    warnings = ['missing:' + key for key in ('title', 'case_no', 'court', 'document_type') if fields[key] is None]
    fields['case_no'] = normalize_case(fields['case_no'])
    for key in ('decision_date', 'publication_date', 'filing_date'):
        value = fields[key]
        if value is not None:
            try:
                if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
                    raise ValueError
                fields[key] = date.fromisoformat(value).isoformat()
            except ValueError:
                fields[key] = None
                warnings.append('invalid_date:' + key)
    decision = fields['decision_date']
    if decision and fields['publication_date'] and fields['publication_date'] < decision:
        warnings.append('publication_before_decision')
    if decision and fields['filing_date'] and fields['filing_date'] > decision:
        warnings.append('filing_after_decision')
    if decision and fields['decision_year'] and fields['decision_year'] != decision[:4]:
        warnings.append('decision_year_conflict')
    return {'fields': fields, 'warnings': tuple(warnings)}
