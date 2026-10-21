"""Bounded-rounds wire codec (library-context-v2). A plan is data, never a grant.

Round 1 bytes are committed by the granted basis; later rounds rebuild
deterministically from persisted plan events and handler receipts only.
"""
from decimal import Context, localcontext

from ... import domain as d
from ...config import canonical_json
from ..library_records import encoded, sha
from . import context_codec
from .context_preview import _SYSTEM_ROUNDS, build_preview


def _validated(kind, value):
    return context_codec._validated(kind, value)


def build_preview_rounds(manifest, scope, composer_revision, config):
    """v2 preview: identical envelope, rounds-capable system template."""
    return build_preview(manifest, scope, composer_revision, config,
                         template_version='saved-library-context-system-v2')


def build_basis_rounds(request_id, manifest, scope, composer_revision, config, records):
    """Describe exact proposed round-1 bytes for a bounded-rounds run."""
    records = tuple(_validated(d.SavedLibraryCitation, item) for item in records)
    bindings = tuple(d.MainContextSourceBinding(saved_citation_id=item.id,
        citation_sha256=sha(encoded(item.citation))) for item in records)
    context_codec.validate_sources(manifest, scope, bindings, records)
    preview = build_preview_rounds(manifest, scope, composer_revision, config)
    if preview.state != 'ready':
        raise ValueError('CONTEXT_INPUT_INVALID')
    return d.MainContextSendBasis(request_id=request_id, expected_scope=scope,
        expected_composer_revision=composer_revision, input_format='library-context-v2',
        template_version='saved-library-context-system-v2',
        system_sha256=sha(preview.system_text), manifest_sha256=preview.manifest_sha256,
        source_bindings=bindings, config_sha256=preview.config_sha256,
        wire_sha256=preview.wire_sha256)


def _assistant_content(plan):
    plan = _validated(d.MainContextToolPlan, plan)
    return canonical_json({'tool_plan': plan.model_dump(mode='json')})


def _outcomes_content(outcomes):
    outcomes = tuple(_validated(d.MainContextToolOutcome, item) for item in outcomes)
    return canonical_json({'tool_results': [item.model_dump(mode='json') for item in outcomes]})


def prepare_rounds(request, round_no, exchanges, config):
    """Deterministic wire for any v2 round; raises unless within input bytes."""
    request = _validated(d.MainContextRequest, request)
    config = _validated(d.MainModelConfig, config)
    if request.basis.input_format != 'library-context-v2':
        raise ValueError('CONTEXT_INPUT_INVALID')
    if type(round_no) is not int or not 1 <= round_no <= 4:
        raise ValueError('CONTEXT_INPUT_INVALID')
    exchanges = tuple(_validated(d.MainContextRoundExchange, item) for item in exchanges)
    raw = canonical_json(request.manifest.model_dump(mode='json'))
    messages = [{'role': 'system', 'content': _SYSTEM_ROUNDS},
        {'role': 'user', 'content': raw}]
    for exchange in exchanges:
        messages.append({'role': 'assistant', 'content': _assistant_content(exchange.plan)})
        messages.append({'role': 'user', 'content': _outcomes_content(exchange.outcomes)})
    with localcontext(Context(prec=60)):
        wire = canonical_json({'model': config.model, 'messages': messages,
            'max_tokens': config.max_output_tokens, 'stream': False,
            'thinking': {'type': 'disabled'}, 'response_format': {'type': 'json_object'}})
    if len(wire.encode('utf-8')) > config.max_input_bytes:
        raise ValueError('CONTEXT_INPUT_INVALID')
    return d.MainContextRoundsPreparedInput(request=request, round_no=round_no,
        exchanges=exchanges, wire_payload_json=wire)


def project_outcome(receipt):
    """Project one persisted handler receipt into the bounded model-facing shape."""
    from ..library_records import result_citations
    receipt = _validated(d.LibraryHandlerReceiptView, receipt)
    citations = tuple(d.MainContextToolOutcomeCitation(saved_citation_id=identifier,
        title=citation.title, quote=citation.quote, quote_sha256=citation.quote_sha256)
        for identifier, citation in zip(receipt.result.citation_ids,
                                        result_citations(receipt.result.result)))
    return d.MainContextToolOutcome(receipt_id=receipt.id, tool=receipt.handler_id,
                                    citations=citations)


def decode_rounds_response(raw, request, config, secret):
    """A v2 reply is either a final candidate or a bounded fixed-tool plan."""
    from .deepseek_protocol import decode_response as decode_envelope
    request = _validated(d.MainContextRequest, request)

    def parse_candidate(value):
        if set(value) == {'tool_plan'}:
            return d.MainContextToolPlan.model_validate(value['tool_plan'])
        candidate = d.MainContextCandidate.model_validate(value)
        selected = {item.saved_citation_id: item.quote_sha256 for item in request.manifest.sources}
        if any(selected.get(item.saved_citation_id) != item.quote_sha256
               for item in candidate.citations):
            raise ValueError('MODEL_OUTPUT_INVALID')
        return candidate

    return decode_envelope(raw, config, secret, parse_candidate=parse_candidate,
                           reply_type=d.MainContextReply)
