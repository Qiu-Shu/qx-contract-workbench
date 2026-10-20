"""Bounded source-checked citations over the existing local library."""
from pathlib import Path
import sqlite3

from ... import domain as d
from ...library import service
from ...library.catalog import canonical, digest
from ...library.cleaning import clean_case, normalize_case
from ...library.index import current_generation
from ...library.law_sections import law_fields, split_law
from ...library.text import normalize, query_terms


def _validated(model, value, code):
    try:
        return model.model_validate(value.model_dump(mode='python', warnings=False) if isinstance(value, model) else value)
    except (ValueError, TypeError):
        raise ValueError(code) from None


def _current(root, expected):
    manifest = current_generation(root)
    if manifest is None or manifest['generation_id'] != expected:
        raise ValueError('LIBRARY_GENERATION_STALE')


def _checked_original(root, record_id, version_id, fragment_id):
    original = (service.read_fragment(root, fragment_id) if fragment_id else
                service.read_original(root, record_id, version_id))
    record, source = original.record, original.source
    source_identity = digest(canonical(['qx-library-source-v1', source.batch_id, source.kind, source.sha256]).encode())
    record_identity = digest(canonical(['qx-library-v1', source.batch_id, source.sha256, record.ordinal]).encode())
    if (record.record_id != record_id or record.version_id != version_id or
            record.source_id != source.source_id or source.source_id != source_identity or
            record.record_id != record_identity or record.kind != source.kind or
            source.asset_key != source.sha256 + '/original' or
            record.version_id != (record.body_sha256 or record.raw_sha256)):
        raise ValueError('LIBRARY_SOURCE_UNAVAILABLE')
    fragments = split_law(record, original.text) if record.kind == 'law_markdown' else ()
    if fragment_id is not None:
        if original.fragment is None or original.fragment.fragment_id != fragment_id:
            raise ValueError('LIBRARY_SOURCE_UNAVAILABLE')
        expected = next((item for item in fragments if item.fragment_id == fragment_id), None)
        if expected is None or expected != original.fragment:
            raise ValueError('LIBRARY_SOURCE_UNAVAILABLE')
    if record.kind == 'case_csv':
        fields = clean_case(original.raw_fields)['fields']
        titles = [fields.get('title') or fields.get('case_no') or '未命名资料']
    else:
        if not source.aliases:
            raise ValueError('LIBRARY_SOURCE_UNAVAILABLE')
        # Registration aliases supply a filename clue only, never an authority URL or an opened path.
        fields, _ = law_fields(Path(source.aliases[0]), original.text)
        titles = [law_fields(Path(alias), '')[0]['title'] for alias in source.aliases]
    return original, fragments, fields, titles


def _matches(query, original, fragment, hit, fields, titles):
    if query.kind not in ('all', original.record.kind):
        return False
    for name in ('case_no', 'court', 'cause', 'province', 'document_type'):
        requested = getattr(query, name)
        value = fields.get('region_candidate') if name == 'province' and original.record.kind == 'law_markdown' else fields.get(name)
        if requested is not None and value != (normalize_case(requested) if name == 'case_no' else requested):
            return False
    decision = fields.get('decision_date')
    if query.date_from and (not decision or decision < query.date_from.isoformat()):
        return False
    if query.date_to and (not decision or decision > query.date_to.isoformat()):
        return False
    terms, _ = query_terms(query.text, query.mode)
    lower, upper = (fragment.start, fragment.end) if fragment else (0, len(original.text))
    body, mapping = normalize(original.text[lower:upper], with_map=True)
    # Whole-law hits came from title-only units, not from an unbounded body match.
    if original.record.kind == 'law_markdown' and hit.fragment_id is None:
        body = ''
        mapping = []
    title_values = [normalize(title) for title in titles]
    if any(term not in body and all(term not in title for title in title_values) for term in terms):
        return False
    starts = [(body.find(term), term) for term in terms if term in body]
    if starts:
        position, term = min(starts)
        expected = (lower + mapping[position], lower + mapping[position + len(term) - 1] + 1)
        return hit.match_field == 'body' and (hit.match_start, hit.match_end) == expected
    return (hit.match_field == ('title' if terms else 'metadata') and
            hit.match_start is None and hit.match_end is None)


def _citation(original, generation, fragment, fields, start, end,
              match_field, match_start, match_end):
    record, source, text = original.record, original.source, original.text
    lower, upper = (fragment.start, fragment.end) if fragment else (0, len(text))
    if not lower <= start < end <= upper or end - start > 1200:
        raise ValueError('LIBRARY_CITATION_MISMATCH')
    if match_field == 'body' and not lower <= match_start < match_end <= upper:
        raise ValueError('LIBRARY_CITATION_MISMATCH')
    quote = text[start:end]
    names = (('case_no', 'court', 'cause', 'province', 'decision_date', 'publication_date', 'filing_date')
             if record.kind == 'case_csv' else ('filename_date_candidate', 'region_candidate', 'legal_status'))
    value = {
        'generation_id': generation, 'record_id': record.record_id, 'version_id': record.version_id,
        'source_id': source.source_id, 'registered_source_sha256': source.sha256,
        'raw_sha256': record.raw_sha256, 'body_sha256': record.body_sha256, 'kind': record.kind,
        'title': fields.get('title') or fields.get('case_no') or '未命名资料',
        'metadata': {name: fields.get(name) for name in names}, 'fragment_id': fragment.fragment_id if fragment else None,
        'fragment_role': fragment.role if fragment else None, 'article': fragment.article if fragment else None,
        'ambiguous': fragment.ambiguous if fragment else False, 'start': start, 'end': end,
        'line_start': text.count('\n', 0, start) + 1,
        'line_end': text.count('\n', 0, end - 1) + 1,
        'quote': quote, 'quote_sha256': digest(quote.encode('utf-8')),
        'match_field': match_field, 'match_start': match_start, 'match_end': match_end,
        'match_in_quote': bool(match_field == 'body' and start <= match_start < match_end <= end),
        'source_match': 'record_quote_matched', 'support_status': 'unverified', 'applicability_status': 'unverified',
    }
    value['citation_id'] = digest(canonical(['qx-library-citation-v1', value]).encode('utf-8'))
    return d.CitationRef.model_validate(value)


def _source_error(error):
    code = str(error)
    if code in {'LIBRARY_GENERATION_STALE', 'LIBRARY_CITATION_MISMATCH'}:
        return code
    if type(error) is ValueError and (code.startswith('QUERY_') or code.startswith('CURSOR_')):
        return 'LIBRARY_QUERY_INVALID'
    return 'LIBRARY_SOURCE_UNAVAILABLE'


class LegalLibraryAdapter:
    def __init__(self, root):
        self.root = Path(root) if root is not None else None

    def search(self, query):
        query = _validated(d.AssistantLibraryQuery, query, 'LIBRARY_QUERY_INVALID')
        if self.root is None:
            return d.LibraryCitationPage(query=query, state='not_configured')
        try:
            page = service.search(self.root, query)
            if page.state == 'not_ready':
                return d.LibraryCitationPage(query=query, state='not_ready')
            _current(self.root, page.generation_id)
            citations, omitted = [], 0
            for hit in page.hits:
                original, fragments, fields, titles = _checked_original(
                    self.root, hit.record_id, hit.version_id, hit.fragment_id)
                if not original.text.strip():
                    omitted += 1
                    continue
                if hit.kind != original.record.kind:
                    raise ValueError('LIBRARY_SOURCE_UNAVAILABLE')
                fragment = original.fragment
                if fragments and fragment is None:
                    position = hit.match_start if hit.match_start is not None else 0
                    fragment = next((item for item in fragments if item.start <= position < item.end), None)
                    if fragment is None:
                        raise ValueError('LIBRARY_SOURCE_UNAVAILABLE')
                if not _matches(query, original, fragment, hit, fields, titles):
                    omitted += 1
                    continue
                lower, upper = (fragment.start, fragment.end) if fragment else (0, len(original.text))
                start = max(lower, hit.match_start - 60) if hit.match_start is not None else lower
                end = min(upper, start + 1200)
                citations.append(_citation(original, page.generation_id, fragment, fields,
                    start, end, hit.match_field, hit.match_start, hit.match_end))
            _current(self.root, page.generation_id)
            return d.LibraryCitationPage(query=query, state=page.state, generation_id=page.generation_id,
                citations=tuple(citations), coverage=page.coverage, next_cursor=page.next_cursor,
                omitted_hits=omitted)
        except (ValueError, OSError, sqlite3.Error, TypeError, KeyError) as error:
            raise ValueError(_source_error(error)) from None

    def read_original(self, citation):
        citation = _validated(d.CitationRef, citation, 'LIBRARY_CITATION_INVALID')
        if self.root is None:
            raise ValueError('LIBRARY_NOT_CONFIGURED')
        try:
            _current(self.root, citation.generation_id)
            original, _, fields, _ = _checked_original(
                self.root, citation.record_id, citation.version_id, citation.fragment_id)
            result = _citation(original, citation.generation_id, original.fragment, fields,
                citation.start, citation.end, citation.match_field, citation.match_start, citation.match_end)
            if result != citation:
                raise ValueError('LIBRARY_CITATION_MISMATCH')
            _current(self.root, citation.generation_id)
            return result
        except (ValueError, OSError, sqlite3.Error, TypeError, KeyError) as error:
            raise ValueError(_source_error(error)) from None
