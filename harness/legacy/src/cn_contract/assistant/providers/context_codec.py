"""Fixed context wire codec. A basis is data; current permission lives elsewhere."""
from decimal import Context, localcontext
import json

from ... import domain as d
from ..library_records import encoded, sha
from .context_preview import build_preview, project_source


def _validated(kind, value):
    if type(value) is not kind:
        raise ValueError('CONTEXT_INPUT_INVALID')
    with localcontext(Context(prec=60)):
        return kind.model_validate(value.model_dump(mode='python', warnings=False))


def validate_sources(manifest, scope, bindings, records):
    """Check trusted saved snapshots, not current access or a live library lookup."""
    manifest = _validated(d.MainContextManifest, manifest)
    scope = _validated(d.ScopeSnapshot, scope)
    if len(records) != len(manifest.sources) or len(bindings) != len(records):
        raise ValueError('CONTEXT_INPUT_INVALID')
    for source, binding, record in zip(manifest.sources, bindings, records):
        binding = _validated(d.MainContextSourceBinding, binding)
        record = _validated(d.SavedLibraryCitation, record)
        original = record.scope
        if (binding.saved_citation_id != record.id or source != project_source(record)
                or binding.citation_sha256 != sha(encoded(record.citation))
                or any(getattr(original, key) != getattr(scope, key) for key in
                    ('workspace_id', 'conversation_id', 'scope_kind', 'scope_ref', 'binding_revision'))
                or original.input_revision > scope.input_revision
                or original.materials_revision > scope.materials_revision):
            raise ValueError('CONTEXT_INPUT_INVALID')


def manifest_digest(manifest):
    """Authorization-key digest of the manifest alone; independent of any config."""
    manifest = _validated(d.MainContextManifest, manifest)
    from ...config import canonical_json
    from hashlib import sha256
    return sha256(canonical_json(manifest.model_dump(mode='json')).encode('utf-8')).hexdigest()


def build_basis(request_id, manifest, scope, composer_revision, config, records):
    """Describe exact proposed bytes after source checks; does not grant a send."""
    records = tuple(_validated(d.SavedLibraryCitation, item) for item in records)
    bindings = tuple(d.MainContextSourceBinding(saved_citation_id=item.id,
        citation_sha256=sha(encoded(item.citation))) for item in records)
    validate_sources(manifest, scope, bindings, records)
    preview = build_preview(manifest, scope, composer_revision, config)
    if preview.state != 'ready':
        raise ValueError('CONTEXT_INPUT_INVALID')
    return d.MainContextSendBasis(request_id=request_id, expected_scope=scope,
        expected_composer_revision=composer_revision, system_sha256=sha(preview.system_text),
        manifest_sha256=preview.manifest_sha256, source_bindings=bindings,
        config_sha256=preview.config_sha256, wire_sha256=preview.wire_sha256)


def prepare(request, config):
    request = _validated(d.MainContextRequest, request)
    config = _validated(d.MainModelConfig, config)
    basis = request.basis
    preview = build_preview(request.manifest, basis.expected_scope,
        basis.expected_composer_revision, config)
    if (preview.state != 'ready' or basis.system_sha256 != sha(preview.system_text)
            or basis.config_sha256 != preview.config_sha256
            or basis.manifest_sha256 != preview.manifest_sha256
            or basis.wire_sha256 != preview.wire_sha256):
        raise ValueError('CONTEXT_INPUT_INVALID')
    return d.MainContextPreparedInput(request=request, wire_payload_json=preview.wire_payload_json)


def build_request(request, config):
    return json.loads(prepare(request, config).wire_payload_json)


def decode_response(raw, request, config, secret):
    from .deepseek_protocol import decode_response as decode_envelope
    request = _validated(d.MainContextRequest, request)
    def parse_candidate(value):
        candidate = d.MainContextCandidate.model_validate(value)
        selected = {item.saved_citation_id: item.quote_sha256 for item in request.manifest.sources}
        if any(selected.get(item.saved_citation_id) != item.quote_sha256 for item in candidate.citations):
            raise ValueError('MODEL_OUTPUT_INVALID')
        return candidate
    return decode_envelope(raw, config, secret, parse_candidate=parse_candidate, reply_type=d.MainContextReply)
