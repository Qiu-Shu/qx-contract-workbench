"""Bound rendered draft text by legal importance, not by raw position.

The four material workflows (contract, case evidence, trademark, criminal) do not
take their display text from the model: the backend ``_render()`` helpers flatten
every finding field and print every quotation in full. The schema itself allows,
for example, 20 coverage gaps of 1000 characters each (or 40 quotations of 2000
characters), so a *fully legal* draft easily exceeds the 20000-character
``AssistantText`` limit (``domain.py``). Before this module existed such a draft
was rejected as a whole, i.e. the more carefully the model reviewed, the more
likely the entire task failed.

A draft is not a uniform blob. Read top to bottom it is:

1. **disclaimer head** -- "未签发｜待律师核实", the risk-colour line, "引文位置
   已校验，不代表分析正确", our party role. A reader who loses this is reading a
   legal opinion with no warning attached, which is worse than no output at all.
2. **method sources** -- the frozen method version, its SHA-256, source
   reference and license notice. Losing this makes the work unattributable.
3. **coverage gaps / open items** -- what the review explicitly did *not* verify.
4. **middle body** -- findings, positions and verbatim quotations.

So this module splits the text on those fixed markers and spends the budget in
that order of importance:

* sections 1 and 2 are charged first; the head (``HEAD_KEEP_LINES`` opening
  lines) and the method-source block are kept verbatim;
* the remainder is split so the caveat block takes at most 60% and the middle
  body at least 40% (``CAVEAT_SHARE_NUM`` / ``CAVEAT_SHARE_DEN``), with unused
  allowance handed back to whichever section still needs it;
* every section is cut on whole-line boundaries only -- no line is ever sliced
  in half, because a half line of a quotation or a license statement reads like
  a complete thought and is therefore worse than an honest gap;
* every section that is cut gets its own notice describing exactly what
  happened, and several notices may appear at once.

What this module still cannot do, stated plainly rather than glossed over:

* **Silence about count.** ``NOTICE_MIDDLE`` says the middle body was capped; it
  does not say which findings vanished. Only the structured record does. A
  reader who ignores the notice sees a shorter but apparently complete review.
* **Whole-line granularity can drop a lot.** A middle body made of very long
  lines loses more than the budget strictly requires, and a single line longer
  than the entire allowance is dropped whole (the notice then appears with no
  body at all in front of it).
* **The caveat heading can be lost.** If the caveat block does not fit even its
  first line, ``NOTICE_CAVEATS`` is the only trace of it; the count in the notice
  is exact, but the list is gone.
* **Oversized sources keep their tail, not their heading.** When the head plus
  the method-source block alone exceed the limit, the source block is kept from
  its *last* whole line backwards so the license statements survive; the
  "本次方法来源" heading may be missing and the block will not start on a clean
  heading line. ``NOTICE_SOURCES`` says so, but a reader cannot tell from the
  text which method version each surviving line belongs to.
* **Degenerate input loses the notices too.** Text whose first lines contain no
  newline at all has no line boundary to cut on; as a last resort the result is
  sliced at ``MAX_RENDER_CHARS`` with no notice. This branch is reachable only
  for input that has no line structure whatsoever, and it never raises.
* **Nothing here is a guarantee of completeness.** Every notice describes an
  omission; none of them promises that something was kept in full.

Callers should therefore treat a bounded render as a signal to open the
structured draft (``contract_review`` / ``case_evidence`` / ``trademark_triage``
/ ``criminal_analysis``), which is never truncated by this module.

Only the standard library may be imported here: every builder imports this
module, so any project import would risk a cycle.
"""

MAX_RENDER_CHARS = 20000
HEAD_KEEP_LINES = 6
NOTICE_MIDDLE = '\n（正文篇幅已达上限，中间部分条目未在正文显示，见结构化记录。）'
NOTICE_CAVEATS = '\n（另有 {count} 条待核事项未在正文显示，见结构化记录。）'
NOTICE_SOURCES = '\n（方法来源篇幅已截短，完整许可见结构化记录。）'
CAVEAT_MARKERS = ('\n覆盖缺口与待核事项', '\n证据缺口与未核事项', '\n材料缺口与未核事项')
SOURCE_MARKERS = ('\n本次方法来源', '\n本次已载入方法来源')
CAVEAT_SHARE_NUM = 6
CAVEAT_SHARE_DEN = 10


def bounded(text: str) -> str:
    """Return ``text`` unchanged when it fits, else spend the budget by importance.

    Args:
        text: The fully rendered draft text produced by a builder's ``_render``.

    Returns:
        The same object when ``len(text) <= MAX_RENDER_CHARS``. Otherwise a new
        string of length at most ``MAX_RENDER_CHARS`` built as
        ``head + middle + sources`` in importance order, where the disclaimer
        head and the method-source block are kept verbatim, the caveat block and
        the middle body are cut on whole-line boundaries, and every cut section
        is announced with its own notice. The result is always bounded, and
        calling this function on its own output returns that output unchanged.

    Raises:
        TypeError: If ``text`` is not a ``str``.
    """
    if not isinstance(text, str):
        raise TypeError('RENDER_BUDGET_TEXT_INVALID')
    if len(text) <= MAX_RENDER_CHARS:
        return text
    head, middle, caveats, sources = _split(text)
    reserve = _notice_reserve(middle, caveats)
    if len(head) + len(sources) + reserve > MAX_RENDER_CHARS:
        # No room for the caveat block or the body; keep the head and the tail of
        # the sources. See the module docstring for what is lost here.
        return _squeeze(head, middle, caveats, sources)
    room = MAX_RENDER_CHARS - len(head) - len(sources) - reserve
    middle_allow, caveat_allow = _allowances(room, middle, caveats)
    kept_middle = _line_prefix(middle, middle_allow)
    kept_caveats = _line_prefix(caveats, caveat_allow)
    # Hand unused allowance back to whatever section is still cut, lowest
    # priority first, so the result uses the budget instead of leaving it idle.
    for _ in range(3):
        slack = room - len(kept_middle) - len(kept_caveats) - _notice_length(
            middle, caveats, kept_middle, kept_caveats)
        if slack <= 0:
            break
        if kept_middle != middle:
            grown = _line_prefix(middle, len(kept_middle) + slack)
            if grown != kept_middle:
                kept_middle = grown
                continue
        if kept_caveats != caveats:
            grown = _line_prefix(caveats, len(kept_caveats) + slack)
            if grown != kept_caveats:
                kept_caveats = grown
                continue
        break
    hidden = _hidden_caveats(caveats, kept_caveats)
    pieces = [head, kept_middle]
    if kept_middle != middle:
        pieces.append(NOTICE_MIDDLE)
    pieces.append(kept_caveats)
    if hidden:
        pieces.append(NOTICE_CAVEATS.format(count=hidden))
    pieces.append(sources)
    result = ''.join(pieces)
    assert len(result) <= MAX_RENDER_CHARS, 'render budget exceeded'
    return result


def _split(text: str) -> tuple[str, str, str, str]:
    """Split ``text`` into ``(head, middle, caveats, sources)``.

    The four pieces concatenate back to ``text`` exactly, so nothing is lost by
    the split itself.
    """
    head_end = _head_end(text)
    sources_start = _first_marker(text, SOURCE_MARKERS, head_end, len(text))
    if sources_start is None:
        sources_start = len(text)
    caveat_start = _first_marker(text, CAVEAT_MARKERS, head_end, sources_start)
    middle_end = sources_start if caveat_start is None else caveat_start
    head = text[:head_end]
    middle = text[head_end:middle_end]
    caveats = '' if caveat_start is None else text[caveat_start:sources_start]
    sources = text[sources_start:]
    return head, middle, caveats, sources


def _head_end(text: str) -> int:
    """Return the offset just past the ``HEAD_KEEP_LINES``-th line."""
    index = 0
    for _ in range(HEAD_KEEP_LINES):
        found = text.find('\n', index)
        if found < 0:
            return len(text)
        index = found + 1
    return index


def _first_marker(text: str, markers: tuple[str, ...], start: int, end: int) -> int | None:
    """Return the earliest marker offset inside ``text[start:end]``, or ``None``."""
    best = None
    for marker in markers:
        index = text.find(marker, start, end)
        if index >= 0 and (best is None or index < best):
            best = index
    return best


def _notice_reserve(middle: str, caveats: str) -> int:
    """Return the longest notice text these sections can require."""
    reserve = len(NOTICE_MIDDLE) if middle else 0
    total = len(_caveat_items(caveats))
    if total:
        reserve += len(NOTICE_CAVEATS.format(count=total))
    return reserve


def _notice_length(middle: str, caveats: str, kept_middle: str, kept_caveats: str) -> int:
    """Return the notice text length the given cut actually needs."""
    length = len(NOTICE_MIDDLE) if kept_middle != middle else 0
    hidden = _hidden_caveats(caveats, kept_caveats)
    if hidden:
        length += len(NOTICE_CAVEATS.format(count=hidden))
    return length


def _allowances(room: int, middle: str, caveats: str) -> tuple[int, int]:
    """Split ``room`` so the caveats keep at most 60% and the body at least 40%."""
    if room <= 0:
        return 0, 0
    if not caveats:
        return room, 0
    if not middle:
        return 0, room
    caveat_allow = room * CAVEAT_SHARE_NUM // CAVEAT_SHARE_DEN
    return room - caveat_allow, caveat_allow


def _caveat_items(caveats: str) -> list[str]:
    """Return the caveat item lines, i.e. everything but the heading line."""
    filled = [line for line in caveats.split('\n') if line.strip()]
    return filled[1:]


def _hidden_caveats(caveats: str, kept: str) -> int:
    """Return how many caveat items the cut removed."""
    return max(len(_caveat_items(caveats)) - len(_caveat_items(kept)), 0)


def _line_prefix(chunk: str, budget: int) -> str:
    """Return the longest whole-line prefix of ``chunk`` fitting ``budget``."""
    if budget <= 0 or not chunk:
        return ''
    if len(chunk) <= budget:
        return chunk
    index = chunk[:budget].rfind('\n')
    return chunk[:index] if index >= 0 else ''


def _line_suffix(chunk: str, budget: int) -> str:
    """Return the longest whole-line suffix of ``chunk`` fitting ``budget``."""
    if budget <= 0 or not chunk:
        return ''
    body = chunk.rstrip('\n')
    if len(body) <= budget:
        return body
    kept: list[str] = []
    total = 0
    for line in reversed(body.split('\n')):
        extra = len(line) if not kept else len(line) + 1
        if total + extra > budget:
            break
        kept.append(line)
        total += extra
    return '\n'.join(reversed(kept))


def _squeeze(head: str, middle: str, caveats: str, sources: str) -> str:
    """Keep the head and the newest whole lines of an oversized source block.

    Never raises and never returns more than ``MAX_RENDER_CHARS`` characters.
    """
    room = MAX_RENDER_CHARS - len(head) - len(NOTICE_SOURCES)
    if room < 0:
        # A head with no line structure to cut on: last resort, documented above.
        trimmed = _line_prefix(head, MAX_RENDER_CHARS - len(NOTICE_SOURCES))
        if not trimmed:
            return _guarantee(head[:MAX_RENDER_CHARS])
        head = trimmed
        room = MAX_RENDER_CHARS - len(head) - len(NOTICE_SOURCES)
    optional = []
    if middle:
        optional.append(NOTICE_MIDDLE)
    total = len(_caveat_items(caveats))
    if total:
        optional.append(NOTICE_CAVEATS.format(count=total))
    kept: list[str] = []
    for notice in optional:
        if len(notice) <= room:
            kept.append(notice)
            room -= len(notice)
    return _guarantee(head + ''.join(kept) + NOTICE_SOURCES + _line_suffix(sources, room))


def _guarantee(result: str) -> str:
    """Clamp ``result`` to the limit without ever raising."""
    if len(result) <= MAX_RENDER_CHARS:
        return result
    cut = _line_prefix(result, MAX_RENDER_CHARS)
    return cut if cut else result[:MAX_RENDER_CHARS]
