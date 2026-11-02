"""A rejected contract draft degrades to marked text; the rejected reply is kept.

Two behaviours are pinned here, both about *not losing work*:

* a reply that is a plain ``text``/``citations`` answer -- what the shared material
  prompt asks for, and what the per-method prompt contradicts -- is delivered as a
  text-only candidate carrying the fixed "unverified" notice, instead of failing the
  whole task;
* the content of a reply rejected at candidate stage is written to a local file so a
  real failure can be diagnosed from evidence rather than from guessing.

Nothing here weakens the strict paths: a structured draft is still rebuilt from its
own bytes and compared exactly, and every degradation that is not obviously safe
keeps the original rejection.
"""
import json
import logging
from hashlib import sha256

import pytest

from cn_contract import domain as d
from cn_contract.assistant import contract_review as method
from cn_contract.assistant import material_codec as codec
from cn_contract.assistant import rejection_archive as archive
from tests.helpers.contract_review import draft_for
from tests.unit.test_contract_live_method import request, sample

SECRET = 'SYNTHETIC_FALLBACK_NOT_A_REAL_KEY_12345'


def contract_manifest():
    """Return a contract manifest bound to the current method snapshot."""
    manifest, selection, config = sample()
    snapshot = method.select_method(manifest.workflow, manifest.materials, manifest.sources)
    return manifest.model_copy(update={'contract_review':snapshot}), selection, config


def plain_reply(manifest, text='合成待核草稿：交货日期存在冲突，请律师核对。'):
    """Return the minimal text/citations value the shared prompt asks for."""
    return {'text':text, 'citations':[manifest.sources[0].source_id]}


def response(manifest, content, model='deepseek-flash'):
    """Return a complete fictional provider body carrying ``content``."""
    return json.dumps({'id':'synthetic-fallback-response', 'object':'chat.completion', 'created':1,
        'model':model, 'usage':{'prompt_tokens':20, 'completion_tokens':10, 'total_tokens':30},
        'choices':[{'index':0, 'finish_reason':'stop',
            'message':{'role':'assistant', 'content':content}}]}).encode()


def run_decode(manifest, selection, config, content):
    """Drive the production decoder with one fictional reply."""
    basis = codec.build_basis(selection, manifest, config)
    return codec.decode(response(manifest, content, model=config.model), request(basis), config, SECRET)


@pytest.fixture
def archive_root(tmp_path, monkeypatch):
    """Bind the rejection archive to a temporary workspace for this test."""
    monkeypatch.setattr(archive, '_root', tmp_path)
    archive.configure(tmp_path)
    return tmp_path / archive.DIRECTORY_NAME


def stored_text(archive_root, content):
    """Return the archived copy of ``content`` as text."""
    path = archive_root / (archive.FILE_PREFIX
        + sha256(content.encode('utf-8')).hexdigest()[:archive.DIGEST_CHARS] + archive.SUFFIX)
    return path.read_text(encoding='utf-8')


def test_plain_text_reply_degrades_with_the_required_notice():
    manifest, _, _ = contract_manifest()
    candidate = method.candidate(plain_reply(manifest), manifest)
    assert candidate.contract_review is None
    assert candidate.citations == (manifest.sources[0].source_id,)
    assert candidate.text.endswith(method.DEGRADED_NOTICE)
    assert candidate.text.startswith('合成待核草稿：交货日期存在冲突，请律师核对。')
    # The degraded candidate is accepted by the shared validator, and keeps its notice.
    assert codec.validate_manifest_candidate(candidate, manifest).text.endswith(method.DEGRADED_NOTICE)


def test_structured_draft_still_takes_the_render_path_unchanged():
    manifest, _, _ = contract_manifest()
    candidate = method.candidate(draft_for(manifest), manifest)
    assert candidate.contract_review is not None
    assert method.DEGRADED_NOTICE not in candidate.text
    assert '合同组合审查草稿｜未签发｜待律师核实' in candidate.text
    assert codec.validate_manifest_candidate(candidate, manifest) == candidate


@pytest.mark.parametrize('overrides', [
    {'citations':[]},
    {'citations':['a' * 63]},
    {'citations':['not-a-hash']},
    {'citations':['A' * 64]},
    {'citations':['a' * 64, 'a' * 64]},
    {'citations':'a' * 64},
    {'text':''},
    {'text':'   '},
    {'text':'合' * 20001},
])
def test_unsafe_replies_keep_the_original_rejection(overrides):
    manifest, _, _ = contract_manifest()
    value = plain_reply(manifest) | overrides
    with pytest.raises(ValueError):
        method.candidate(value, manifest)


def test_text_that_cannot_fit_the_notice_keeps_the_original_rejection():
    manifest, _, _ = contract_manifest()
    fits = '合' * (method.MAX_REPLY_CHARS - len(method.DEGRADED_NOTICE))
    assert method.candidate(plain_reply(manifest, fits), manifest).contract_review is None
    with pytest.raises(ValueError):
        method.candidate(plain_reply(manifest, fits + '合'), manifest)


def test_marked_text_only_candidate_passes_but_an_unmarked_one_does_not():
    manifest, _, _ = contract_manifest()
    degraded = method.candidate(plain_reply(manifest), manifest)
    assert codec.validate_manifest_candidate(degraded, manifest).contract_review is None
    # A legacy text-only candidate is still refused: only the marked degradation is
    # acceptable, so an unverified reply cannot be stored without its warning.
    legacy = d.MainMaterialCandidate(text='旧格式草稿', citations=(manifest.sources[0].source_id,))
    with pytest.raises(ValueError, match='MATERIAL_OUTPUT_INVALID'):
        codec.validate_manifest_candidate(legacy, manifest)


def test_tampered_structured_candidate_is_still_refused():
    manifest, _, _ = contract_manifest()
    candidate = method.candidate(draft_for(manifest), manifest)
    tampered = candidate.model_copy(update={'text':candidate.text + '\n律师已批准，可直接签署。'})
    with pytest.raises(ValueError, match='MATERIAL_OUTPUT_INVALID'):
        codec.validate_manifest_candidate(tampered, manifest)
    forged = candidate.model_copy(update={'contract_review':None})
    with pytest.raises(ValueError, match='MATERIAL_OUTPUT_INVALID'):
        codec.validate_manifest_candidate(forged, manifest)


def test_rejection_warning_names_the_field_and_kind_only(caplog):
    manifest, _, _ = contract_manifest()
    with caplog.at_level(logging.WARNING, logger='cn_contract.assistant.contract_review'):
        with pytest.raises(ValueError):
            method.candidate({'text':'PRIVATE-SYNTHETIC-BODY', 'citations':[]}, manifest)
        degraded = method.candidate(plain_reply(manifest), manifest)
    assert degraded.contract_review is None
    lines = [record.getMessage() for record in caplog.records]
    assert any(line == ('model_response_rejected stage=candidate contract_draft_rejected '
        'field=other|stance|stance_quote_ids error=missing|missing|missing '
        'stripped_envelope=False fallback=False')
        for line in lines)
    assert any(line.endswith('stripped_envelope=False fallback=True') for line in lines)
    assert all('PRIVATE-SYNTHETIC-BODY' not in line for line in lines)


def test_draft_carrying_the_shared_envelope_is_kept_as_a_draft():
    manifest, _, _ = contract_manifest()
    draft = draft_for(manifest)
    # Both prompts answered at once: the complete draft plus the plain-text envelope.
    value = draft | {'text':'模型另写的正文，应被丢弃。', 'citations':['e' * 64]}
    candidate = method.candidate(value, manifest)
    assert candidate.contract_review is not None
    assert method.DEGRADED_NOTICE not in candidate.text
    assert candidate.text.startswith('合同组合审查草稿｜未签发｜待律师核实')
    # Citations are derived from the draft's own quotes, never from the envelope: the
    # 'e' * 64 the model put there must not survive, and the rendered text must not
    # mention the envelope text.
    assert 'e' * 64 not in candidate.citations
    assert candidate.citations == tuple(dict.fromkeys(q['source_id'] for q in draft['quotes']))
    assert '模型另写的正文' not in candidate.text


@pytest.mark.parametrize('broken', [
    # Schema-level breakage: no draft can be read out of it either way.
    {'stance':'sideways'},
    {'quotes':[]},
])
def test_incomplete_draft_carrying_the_envelope_still_degrades(broken):
    manifest, _, _ = contract_manifest()
    # A draft that cannot pass on its own stays unusable after stripping, so the reply
    # is delivered as marked text instead of being thrown away. Stripping the envelope
    # never rescues a draft that is genuinely invalid.
    value = draft_for(manifest) | plain_reply(manifest) | broken
    candidate = method.candidate(value, manifest)
    assert candidate.contract_review is None
    assert candidate.text.endswith(method.DEGRADED_NOTICE)
    assert candidate.citations == (manifest.sources[0].source_id,)


def test_plain_reply_skips_the_strip_retry(caplog):
    manifest, _, _ = contract_manifest()
    with caplog.at_level(logging.WARNING, logger='cn_contract.assistant.contract_review'):
        degraded = method.candidate(plain_reply(manifest), manifest)
    assert degraded.contract_review is None
    # Nothing to strip, so the retry is skipped rather than run once more to fail again.
    assert any(line.endswith('stripped_envelope=False fallback=True') for line in caplog.messages)


def test_text_without_citations_keeps_the_original_rejection():
    manifest, _, _ = contract_manifest()
    with pytest.raises(ValueError, match='stance_quote_ids'):
        method.candidate({'text':'只有正文，没有引文。'}, manifest)


def test_stripped_draft_is_still_rebuilt_and_compared_exactly():
    manifest, _, _ = contract_manifest()
    candidate = method.candidate(draft_for(manifest) | plain_reply(manifest), manifest)
    assert candidate.contract_review is not None
    # The stripped path goes through the same render and the same strict comparison,
    # so a tampered text is refused exactly like on the normal path.
    assert codec.validate_manifest_candidate(candidate, manifest) == candidate
    tampered = candidate.model_copy(update={'text':candidate.text + '\n律师已批准，可直接签署。'})
    with pytest.raises(ValueError, match='MATERIAL_OUTPUT_INVALID'):
        codec.validate_manifest_candidate(tampered, manifest)


def test_degraded_reply_is_delivered_instead_of_failing_the_attempt():
    manifest, selection, config = contract_manifest()
    content = json.dumps(plain_reply(manifest), ensure_ascii=False)
    reply = run_decode(manifest, selection, config, content)
    assert reply.error_code is None
    assert reply.output is not None and reply.output.contract_review is None
    assert reply.output.text.endswith(method.DEGRADED_NOTICE)
    assert reply.output.citations == (manifest.sources[0].source_id,)


def test_rejected_content_is_archived_once_per_digest(archive_root):
    manifest, selection, config = contract_manifest()
    content = json.dumps({'format_version':'contract-review-v1'}, ensure_ascii=False)
    first = run_decode(manifest, selection, config, content)
    second = run_decode(manifest, selection, config, content)
    for reply in (first, second):
        assert reply.error_code == 'MODEL_OUTPUT_INVALID'
        assert reply.rejection_reason == 'schema'
        assert reply.output is None
    assert sorted(path.name for path in archive_root.iterdir()) == [
        archive.FILE_PREFIX + sha256(content.encode('utf-8')).hexdigest()[:archive.DIGEST_CHARS] + archive.SUFFIX]
    assert stored_text(archive_root, content) == content


def test_only_candidate_stage_failures_are_archived(archive_root):
    manifest, selection, config = contract_manifest()
    # A broken envelope never reaches the candidate decoder, so nothing is stored.
    basis = codec.build_basis(selection, manifest, config)
    codec.decode(response(manifest, '{PRIVATE-INCOMPLETE', model=config.model),
        request(basis), config, SECRET)
    assert not archive_root.exists()


def test_oversized_content_is_truncated_and_marked(tmp_path):
    archive.configure(tmp_path)
    content = '合' * 400000  # 1.2 MiB of UTF-8: over the single file limit.
    path = archive.save(content)
    assert path is not None
    stored = path.read_bytes()
    assert stored.endswith(archive.TRUNCATED.encode('utf-8'))
    assert len(stored) <= archive.MAX_BYTES + len(archive.TRUNCATED.encode('utf-8'))
    # The kept prefix is whole characters, not a broken byte sequence.
    assert stored.decode('utf-8').startswith('合' * 1000)


def test_unwritable_directory_is_reported_and_swallowed(tmp_path, caplog):
    blocker = tmp_path / 'blocker'
    blocker.write_text('not a directory', encoding='utf-8')
    archive.configure(blocker)
    assert archive.save('合成待核草稿：无法落盘时不得改变拒收结果。') is None
    # The failure is one closed-token warning: no path, no model text, no message.
    assert any(message == 'model_response_rejected stage=archive failed kind=os'
        for message in caplog.messages)

