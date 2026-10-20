"""Independent compatibility checks against the fixed pre-change text module."""
import itertools
import subprocess

from cn_contract.library.text import normalize, original_span


baseline = subprocess.check_output([
    'git', 'show', '4c303c541a6bfe08225642837ccda72fb761bcb2:src/cn_contract/library/text.py',
], text=True, encoding='utf-8')
before = {}
exec(compile(baseline, '<fixed-baseline-text>', 'exec'), before)
alphabet = ('\u00a8', '\ufdfa', '\r\n', '\u200b', '\u00df', '\ufb03', '\U0001f600', 'e\u0301')
sources = spans = 0
for size in range(4):
    for pieces in itertools.product(alphabet, repeat=size):
        source = ''.join(pieces)
        expected, mapping = before['normalize'](source, with_map=True)
        assert normalize(source) == expected
        assert normalize(source, with_map=True) == (expected, mapping)
        sources += 1
        for start in range(len(expected)):
            for end in range(start + 1, len(expected) + 1):
                assert original_span(source, start, end) == (mapping[start], mapping[end - 1] + 1)
                spans += 1
print(f'PASS sources={sources} spans={spans}; baseline normalization and source coordinates preserved')
