"""Pure validation of persisted library-context attempts; grants nothing.

Shared by runtime reads and archive validation so both enforce the same rules.
Historical proof only: no current permission, live library or network is used.
"""
from sqlalchemy import text

from .. import domain as d
from .library_records import encoded, model as library_model, sha
from .providers import context_codec
from .providers.policy import encoded as policy_encoded, sha as policy_sha

_SCOPE_KEYS = ('workspace_id', 'conversation_id', 'scope_kind', 'scope_ref', 'binding_revision')


def _project(citation, saved_citation_id):
    fields = {name: getattr(citation, name) for name in d.MainContextSource.model_fields
              if name != 'saved_citation_id'}
    return d.MainContextSource(saved_citation_id=saved_citation_id, **fields)


def validate_context_selection(db, row, prepared):
    """Relations, manifest, bindings and persisted citations must match exactly.

    The saved citation's persisted scope must sit on the same conversation
    binding and predate the approved snapshot; no current access is re-checked.
    """
    relations = db.execute(text('''SELECT ordinal,saved_citation_id FROM assistant_model_input_citations
        WHERE attempt_id=:id ORDER BY ordinal'''), {'id': row['id']}).mappings().all()
    manifest = prepared.request.manifest
    bindings = prepared.request.basis.source_bindings
    expected = prepared.request.basis.expected_scope
    if not (1 <= len(relations) == len(manifest.sources) == len(bindings) <= 8):
        raise ValueError('ASSISTANT_MODEL_INTEGRITY')
    for ordinal, (relation, source, binding) in enumerate(zip(relations, manifest.sources, bindings)):
        if (relation['ordinal'] != ordinal or relation['saved_citation_id'] != str(source.saved_citation_id)
                or binding.saved_citation_id != source.saved_citation_id):
            raise ValueError('ASSISTANT_MODEL_INTEGRITY')
        citation = db.execute(text('SELECT * FROM assistant_library_citations WHERE id=:id'),
                              {'id': relation['saved_citation_id']}).mappings().first()
        if citation is None:
            raise ValueError('ASSISTANT_MODEL_INTEGRITY')
        record = library_model(d.CitationRef, citation['citation_json'])
        if (sha(encoded(record)) != citation['citation_sha256']
                or citation['citation_sha256'] != binding.citation_sha256):
            raise ValueError('ASSISTANT_MODEL_INTEGRITY')
        if source != _project(record, citation['id']):
            raise ValueError('ASSISTANT_MODEL_INTEGRITY')
        receipt = db.execute(text('SELECT scope_json FROM assistant_handler_receipts WHERE id=:id'),
                             {'id': citation['receipt_id']}).mappings().first()
        if receipt is None:
            raise ValueError('ASSISTANT_MODEL_INTEGRITY')
        original = library_model(d.ScopeSnapshot, receipt['scope_json'])
        if (any(getattr(original, key) != getattr(expected, key) for key in _SCOPE_KEYS)
                or original.input_revision > expected.input_revision
                or original.materials_revision > expected.materials_revision):
            raise ValueError('ASSISTANT_MODEL_INTEGRITY')


def validate_context_input(row, prepared, config):
    """Deterministic rebuild must reproduce the immutable stored wire."""
    if prepared.request.basis.config_sha256 != policy_sha(policy_encoded(config)):
        raise ValueError('ASSISTANT_MODEL_INTEGRITY')
    if context_codec.prepare(prepared.request, config).wire_payload_json != prepared.wire_payload_json:
        raise ValueError('ASSISTANT_MODEL_INTEGRITY')
    if policy_sha(prepared.wire_payload_json) != row['request_sha256']:
        raise ValueError('ASSISTANT_MODEL_INTEGRITY')


def validate_context_output(view, prepared):
    """A stored answer may only cite the approved selection with exact digests."""
    selected = {item.saved_citation_id: item.quote_sha256 for item in prepared.request.manifest.sources}
    if any(selected.get(item.saved_citation_id) != item.quote_sha256
           for item in view.candidate.citations):
        raise ValueError('ASSISTANT_MODEL_INTEGRITY')
