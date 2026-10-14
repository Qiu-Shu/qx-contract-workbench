"""Deterministic Chinese bigrams and original-character mappings, no dictionaries."""
import unicodedata

INVISIBLE = frozenset('\u200b\u200c\u200d\u2060\ufeff')
TOKENIZER_VERSION = 'qx-bigram-v1'


def normalize(text: str, *, with_map=False):
    output, mapping = [], []
    for index, char in enumerate(text):
        if char in INVISIBLE:
            continue
        for value in unicodedata.normalize('NFKC', char).casefold():
            if value.isspace():
                if output and output[-1] == ' ':
                    continue
                value = ' '
            output.append(value)
            if with_map:
                mapping.append(index)
    normalized = ''.join(output)
    return (normalized, mapping) if with_map else normalized


def is_han(char):
    return '\u3400' <= char <= '\u9fff' or '\U00020000' <= char <= '\U0003134f'


def tokens(normalized: str) -> list[str]:
    result = []
    index = 0
    while index < len(normalized):
        start = index
        if is_han(normalized[index]):
            while index < len(normalized) and is_han(normalized[index]):
                index += 1
            word = normalized[start:index]
            if len(word) == 1:
                result.append('s' + word)
            else:
                result.extend('h' + word[i:i + 2] for i in range(len(word) - 1))
        elif normalized[index].isalnum():
            while index < len(normalized) and normalized[index].isalnum() and not is_han(normalized[index]):
                index += 1
            # Hex encoding separates user Latin text from internal namespaces.
            result.append('w' + normalized[start:index].encode('utf-8').hex())
        else:
            while index < len(normalized) and not normalized[index].isalnum():
                index += 1
            if not result or result[-1] != 'b':
                result.append('b')
    return result


def query_terms(text: str, mode: str):
    normalized = normalize(text).strip()
    if not normalized:
        return [], None
    terms = normalized.split() if mode == 'all' else [normalized]
    if len(terms) > 20:
        raise ValueError('QUERY_TOO_MANY_TERMS')
    expressions = []
    for term in terms:
        pieces = tokens(term)
        if not pieces or not any(piece.startswith(('h', 'w')) for piece in pieces):
            raise ValueError('QUERY_TOO_SHORT_OR_NO_TERMS')
        # Encoded tokens contain no FTS syntax; the caller never supplies operators.
        expressions.append('"' + ' '.join(pieces) + '"')
    return terms, ' AND '.join(expressions)
