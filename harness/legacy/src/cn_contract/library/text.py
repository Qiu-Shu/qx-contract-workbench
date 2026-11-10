"""Deterministic Chinese bigrams and original-character mappings, no dictionaries."""
import unicodedata
import re

INVISIBLE = frozenset('\u200b\u200c\u200d\u2060\ufeff')
TOKENIZER_VERSION = 'qx-bigram-v1'
MAX_QUERY_CHARACTERS = 200
_HAN = '\u3400-\u9fff\U00020000-\U0003134f'
_RUNS = re.compile('(?P<han>[' + _HAN + ']+)|(?P<word>[^\\W_' + _HAN + ']+)|(?P<boundary>[\\W_]+)')
_SPACES = re.compile(' +')


class _CharacterMap(dict):
    def __missing__(self, codepoint):
        char = chr(codepoint)
        expanded = '' if char in INVISIBLE else unicodedata.normalize('NFKC', char).casefold()
        value = ''.join(' ' if c.isspace() else c for c in expanded)
        self[codepoint] = value
        return value


_CHARACTERS = _CharacterMap()


def normalize(text: str, *, with_map=False):
    if not with_map:
        # Per-character NFKC matches the offset-producing path exactly; whole
        # string NFKC would compose adjacent code points and change v1 semantics.
        return _SPACES.sub(' ', text.translate(_CHARACTERS))
    output, mapping = [], []
    for index, char in enumerate(text):
        for value in _CHARACTERS[ord(char)]:
            if value == ' ' and output and output[-1] == ' ':
                continue
            output.append(value)
            mapping.append(index)
    normalized = ''.join(output)
    return normalized, mapping


def original_span(text: str, start: int, end: int) -> tuple[int, int]:
    """Map one normalized span back to its original character range."""
    if type(start) is not int or type(end) is not int or not 0 <= start < end:
        raise ValueError('NORMALIZED_RANGE_INVALID')
    position, previous_space, first = 0, False, None
    for index, char in enumerate(text):
        for value in _CHARACTERS[ord(char)]:
            if value == ' ' and previous_space:
                continue
            previous_space = value == ' '
            if position == start:
                first = index
            position += 1
            if position == end:
                return first, index + 1
    raise ValueError('NORMALIZED_RANGE_INVALID')


def tokens(normalized: str) -> list[str]:
    result = []
    for match in _RUNS.finditer(normalized):
        word = match[0]
        if match.lastgroup == 'han':
            if len(word) == 1:
                result.append('s' + word)
            else:
                result.extend('h' + word[i:i + 2] for i in range(len(word) - 1))
        elif match.lastgroup == 'word':
            # Hex encoding separates user Latin text from internal namespaces.
            result.append('w' + word.encode('utf-8').hex())
        else:
            if not result or result[-1] != 'b':
                result.append('b')
    return result


def query_terms(text: str, mode: str):
    normalized = normalize(text).strip()
    if len(normalized) > MAX_QUERY_CHARACTERS:
        raise ValueError('QUERY_TOO_LONG_AFTER_NORMALIZATION')
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
