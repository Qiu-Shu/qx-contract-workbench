"""Strict tagged candidate protocol; text and model claims confer no authority."""
from uuid import UUID, uuid4
from ..domain import Fact, ParseResult
from ..persistence import get_parse_result, read_matter
from ..security import ServiceError, authorize
from .storage import trusted_parse


def require_position(matter_id, *, actor, db):
    """Block position-dependent recommendations while the user position is absent."""
    matter = read_matter(matter_id,actor,db)
    if matter.position is None:
        raise ServiceError('FACTS_UNCONFIRMED',409)
    return matter.position


def build_fact_candidates(parsed, extraction, *, matter_id, version, actor, db):
    """Return unconfirmed facts for target fact version current+1, without saving.

    parsed.version_id is the immutable document UUID, not the fact version.
    Only field/typed_value/unit/provenance_type/anchor_ids/receipt_ids are accepted.
    """
    authorize(actor,matter_id,'candidate_facts',db)
    matter = read_matter(matter_id,actor,db)
    if matter.status == 'archived':
        raise ServiceError('STATE_CONFLICT',409)
    if type(version) is not int or version != (matter.active_fact_version or 0)+1:
        raise ServiceError('VERSION_CONFLICT',409)
    parsed = ParseResult.model_validate(parsed.model_dump(mode='python'))
    stored = get_parse_result(matter_id,parsed.version_id,actor,db)
    if stored is None or parsed != stored:
        raise ServiceError('VERSION_CONFLICT',409)
    trusted_parse(matter_id,parsed.version_id,actor,db,stored)
    if type(extraction) is not dict or set(extraction) != {'facts'} or type(extraction['facts']) is not list:
        raise ValueError('facts list required')
    allowed = {'field','typed_value','unit','provenance_type','anchor_ids','receipt_ids'}
    anchors = {a.id for a in stored.anchors}
    result = []
    for item in extraction['facts']:
        if type(item) is not dict or set(item) != allowed or type(item['typed_value']) is not dict:
            raise ValueError('strict tagged candidate fields required')
        if set(item['typed_value']) != {'kind','value'}:
            raise ValueError('kind/value required')
        if item['provenance_type'] == 'external' or item['receipt_ids']:
            raise ServiceError('NOT_SUPPORTED',409)
        ids = tuple(UUID(str(value)) for value in item['anchor_ids'])
        if len(set(ids)) != len(ids) or not set(ids).issubset(anchors):
            raise ServiceError('VERSION_CONFLICT',409)
        if item['provenance_type'] == 'document' and not ids:
            raise ServiceError('FACTS_UNCONFIRMED',409)
        result.append(Fact(id=uuid4(),matter_id=matter_id,version=version,
            field=item['field'],typed_value=item['typed_value'],unit=item['unit'],
            provenance_type=item['provenance_type'],anchor_ids=ids,receipt_ids=(),
            confirmation_status='unconfirmed',confirmed_by=None,confirmed_at=None))
    return result
