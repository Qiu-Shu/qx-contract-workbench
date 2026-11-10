"""Locate a model's verbatim quotation in the supplied material, without guessing text."""


def locate_quotes(value, manifest):
    if not isinstance(value, dict) or not isinstance(value.get('quotes'), list):
        return value
    sources = {item.source_id: (item.reference.anchor.quote if item.reference.kind == 'document'
                              else item.reference.quote) for item in manifest.sources}
    if manifest.knowledge:
        sources.update((item.source_id, item.text) for item in manifest.knowledge.passages)
    quotes = []
    for item in value['quotes']:
        if not isinstance(item, dict):
            quotes.append(item)
            continue
        original = sources.get(item.get('source_id')) if isinstance(item.get('source_id'), str) else None
        quote = item.get('exact_quote')
        if original is not None and isinstance(quote, str) and quote.strip():
            start, end = item.get('start'), item.get('end')
            if (type(start) is int and type(end) is int and 0 <= start < end <= len(original)
                    and original[start:end] == quote):
                quotes.append(item)
                continue
            # Character counting belongs to the program. Only an exact, unique match
            # can replace bad model offsets; repeated or absent text stays unresolved.
            found = original.find(quote)
            if found >= 0 and original.find(quote, found + 1) < 0:
                item = {**item, 'start': found, 'end': found + len(quote)}
        quotes.append(item)
    by_source = {}
    for item in quotes:
        if isinstance(item, dict) and isinstance(item.get('source_id'), str) and isinstance(item.get('id'), str):
            by_source.setdefault(item['source_id'], []).append(item['id'])
    aliases = {source: ids[0] for source, ids in by_source.items() if len(ids) == 1}
    ids = {item['id'] for item in quotes if isinstance(item, dict) and isinstance(item.get('id'), str)}

    def references(item):
        if isinstance(item, list):
            return [references(part) for part in item]
        if not isinstance(item, dict):
            return item
        result = {}
        for key, part in item.items():
            if key in {'quote_ids', 'stance_quote_ids'} and isinstance(part, list):
                # A source id and a quotation id are interchangeable only when that
                # source has exactly one quote. Ambiguous references are never guessed.
                result[key] = [aliases.get(ref, ref) if isinstance(ref, str) and ref not in ids else ref
                               for ref in part]
            else:
                result[key] = references(part)
        return result

    return references({**value, 'quotes': quotes})
