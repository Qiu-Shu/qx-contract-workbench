"""Single v2.0 domain vocabulary; validation only, with no I/O or authorization.

All nullable fields without a default still require an explicit key. IDs refer to
internal UUIDs; their ownership and approval evidence must be checked by services.
Frozen models represent snapshots; services create a new validated snapshot when
state changes. Decimal fields accept exact strings/integers, never binary floats.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
from decimal import Decimal, DecimalException
from enum import StrEnum
from typing import Annotated, Literal, Mapping, Union, get_args
from uuid import UUID

from pydantic import (
    AfterValidator, AwareDatetime, BaseModel, BeforeValidator, ConfigDict,
    Field, JsonValue, StrictBool, StringConstraints, field_serializer, field_validator,
    model_validator,
)


def _exact_decimal(value: object) -> object:
    if isinstance(value, (float, bool)):
        raise ValueError('Decimal input must be an exact string, integer or Decimal')
    return value


def _utc(value: datetime) -> datetime:
    return value.astimezone(timezone.utc)


ExactDecimal = Annotated[Decimal, BeforeValidator(_exact_decimal), Field(allow_inf_nan=False)]
Credits = Annotated[ExactDecimal, Field(ge=0)]
UTCDatetime = Annotated[AwareDatetime, AfterValidator(_utc)]
SHA256 = Annotated[str, StringConstraints(pattern=r'^[a-f0-9]{64}$')]
NonEmpty = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
PositiveInt = Annotated[int, Field(strict=True, gt=0)]
NonNegativeInt = Annotated[int, Field(strict=True, ge=0)]
Audience = Literal['internal', 'client', 'counterparty']
EvaluationMode = Literal['offline', 'approved_model', 'live_guarded']


def _immutable_operation(*args: object, **kwargs: object) -> None:
    raise TypeError('domain snapshots are immutable; validate a new snapshot')


class _FrozenDict(dict):
    __setitem__ = __delitem__ = clear = pop = popitem = setdefault = update = __ior__ = _immutable_operation

    def __deepcopy__(self, memo: dict) -> _FrozenDict:
        return self


class _FrozenList(list):
    __setitem__ = __delitem__ = append = clear = extend = insert = pop = remove = reverse = sort = __iadd__ = __imul__ = _immutable_operation

    def __deepcopy__(self, memo: dict) -> _FrozenList:
        return self


def _freeze(value: object) -> object:
    if isinstance(value, (_FrozenDict, _FrozenList)):
        return value
    if isinstance(value, dict):
        return _FrozenDict({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return _FrozenList([_freeze(item) for item in value])
    if isinstance(value, tuple):
        return tuple(_freeze(item) for item in value)
    return value


class DomainModel(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True, validate_default=True)

    @model_validator(mode='after')
    def freeze_collections(self) -> DomainModel:
        for name in type(self).model_fields:
            object.__setattr__(self, name, _freeze(getattr(self, name)))
        return self


class ErrorCode(StrEnum):
    STATE_CONFLICT = 'STATE_CONFLICT'
    ASSISTANT_BUSY = 'ASSISTANT_BUSY'
    VERSION_CONFLICT = 'VERSION_CONFLICT'
    FILE_UNSUPPORTED = 'FILE_UNSUPPORTED'
    FILE_LIMIT = 'FILE_LIMIT'
    BASELINE_REQUIRED = 'BASELINE_REQUIRED'
    CROSS_MATTER_DENIED = 'CROSS_MATTER_DENIED'
    FACTS_UNCONFIRMED = 'FACTS_UNCONFIRMED'
    SOURCE_VISUAL_CONFIRMATION_REQUIRED = 'SOURCE_VISUAL_CONFIRMATION_REQUIRED'
    RULE_SCOPE_UNSUPPORTED = 'RULE_SCOPE_UNSUPPORTED'
    PARTY_AMBIGUOUS = 'PARTY_AMBIGUOUS'
    TOOL_UNBOUND = 'TOOL_UNBOUND'
    PRICE_UNKNOWN = 'PRICE_UNKNOWN'
    PLAN_CHANGED = 'PLAN_CHANGED'
    PLAN_EXPIRED = 'PLAN_EXPIRED'
    BUDGET_EXCEEDED = 'BUDGET_EXCEEDED'
    QUERY_STATE_UNKNOWN = 'QUERY_STATE_UNKNOWN'
    MODEL_OUTPUT_INVALID = 'MODEL_OUTPUT_INVALID'
    UNRESOLVED_HARD_GATE = 'UNRESOLVED_HARD_GATE'
    APPROVAL_STALE = 'APPROVAL_STALE'
    AUTHORIZATION_REQUIRED = 'AUTHORIZATION_REQUIRED'
    SOURCE_UNLOCKED = 'SOURCE_UNLOCKED'
    LICENSE_UNAPPROVED = 'LICENSE_UNAPPROVED'
    RULE_UNAPPROVED = 'RULE_UNAPPROVED'
    DATA_POLICY_UNAPPROVED = 'DATA_POLICY_UNAPPROVED'
    NOT_IMPLEMENTED = 'NOT_IMPLEMENTED'
    NOT_SUPPORTED = 'NOT_SUPPORTED'
    BLOCKED_LIVE = 'BLOCKED_LIVE'


class ContractType(StrEnum):
    SALES = 'sales'
    SERVICE = 'service'
    LEASE = 'lease'
    NDA = 'nda'
    UNKNOWN = 'unknown'


class ReviewRoute(StrEnum):
    FULL = 'full'
    SPECIALIST = 'specialist'


class ReviewMode(StrEnum):
    PRE_SIGN = 'pre_sign'
    POST_SIGN = 'post_sign'


class Position(StrEnum):
    BUYER = 'buyer'
    SELLER = 'seller'
    CUSTOMER = 'customer'
    PROVIDER = 'provider'
    LESSOR = 'lessor'
    LESSEE = 'lessee'
    DISCLOSER = 'discloser'
    RECIPIENT = 'recipient'
    MUTUAL = 'mutual'
    PARTY_A = 'party_a'
    PARTY_B = 'party_b'


class MatterStatus(StrEnum):
    INTAKE = 'intake'
    PARSED = 'parsed'
    AWAITING_FACT_CONFIRMATION = 'awaiting_fact_confirmation'
    READY_FOR_REVIEW = 'ready_for_review'
    REVIEWING = 'reviewing'
    AWAITING_LAWYER = 'awaiting_lawyer'
    APPROVED = 'approved'
    SUPERSEDED = 'superseded'
    ARCHIVED = 'archived'
    FAILED = 'failed'


class GateScope(StrEnum):
    REVIEW = 'review'
    EXTERNAL_QUERY = 'external_query'
    AUTOMATIC_PATCH = 'automatic_patch'
    FORMAL_EXPORT = 'formal_export'


class BaselineView(StrEnum):
    ORIGINAL = 'original'
    ACCEPTED_VIEW = 'accepted_view'
    REJECTED_VIEW = 'rejected_view'
    CONFIRMED_CUSTOM = 'confirmed_custom'


class ParseStatus(StrEnum):
    PENDING = 'pending'
    PARSING = 'parsing'
    PARSED = 'parsed'
    PARTIAL = 'partial'
    FAILED = 'failed'
    UNSUPPORTED = 'unsupported'


class AnchorKind(StrEnum):
    BODY_PARAGRAPH = 'body_paragraph'
    TABLE_CELL = 'table_cell'
    PDF_SPAN = 'pdf_span'
    OTHER = 'other'


class ProvenanceType(StrEnum):
    SOURCE_VERIFICATION = 'source_verification'
    DOCUMENT = 'document'
    EXTERNAL = 'external'
    CLIENT_STATEMENT = 'client_statement'
    ASSUMPTION = 'assumption'


class ConfirmationStatus(StrEnum):
    UNCONFIRMED = 'unconfirmed'
    CONFIRMED = 'confirmed'
    CORRECTED = 'corrected'
    REJECTED = 'rejected'


class ResolutionStatus(StrEnum):
    UNRESOLVED = 'unresolved'
    AMBIGUOUS = 'ambiguous'
    CONFIRMED = 'confirmed'


class FetchStatus(StrEnum):
    PENDING = 'pending'
    FETCHED = 'fetched'
    FAILED = 'failed'
    UNAVAILABLE = 'unavailable'


class VerificationStatus(StrEnum):
    UNVERIFIED = 'unverified'
    VERIFIED = 'verified'
    REJECTED = 'rejected'
    EXPIRED = 'expired'


class BasisKind(StrEnum):
    LAW = 'law'
    CLIENT_POLICY = 'client_policy'
    PRACTICE = 'practice'
    LOGIC = 'logic'


class RuleStatus(StrEnum):
    DRAFT = 'draft'
    APPROVED = 'approved'
    RETIRED = 'retired'


class Severity(StrEnum):
    HIGH = 'high'
    MEDIUM = 'medium'
    LOW = 'low'
    INFO = 'info'


class EvidenceState(StrEnum):
    CONFIRMED = 'confirmed'
    UNCONFIRMED = 'unconfirmed'
    MISSING = 'missing'
    CONFLICTING = 'conflicting'


class CoverageId(StrEnum):
    C01 = 'C01'
    C02 = 'C02'
    C03 = 'C03'
    C04 = 'C04'
    C05 = 'C05'
    C06 = 'C06'
    C07 = 'C07'
    C08 = 'C08'
    C09 = 'C09'
    C10 = 'C10'
    C11 = 'C11'
    C12 = 'C12'
    C13 = 'C13'
    C14 = 'C14'
    C15 = 'C15'
    C16 = 'C16'
    C17 = 'C17'
    C18 = 'C18'


class CoverageStatus(StrEnum):
    REVIEWED_ISSUE = 'reviewed_issue'
    REVIEWED_NO_ISSUE = 'reviewed_no_issue'
    INSUFFICIENT_MATERIAL = 'insufficient_material'
    UNSUPPORTED = 'unsupported'
    NOT_APPLICABLE = 'not_applicable'


class RunStatus(StrEnum):
    QUEUED = 'queued'
    RUNNING = 'running'
    COMPLETED = 'completed'
    FAILED = 'failed'
    SUPERSEDED = 'superseded'


class HumanDecisionKind(StrEnum):
    ACCEPT = 'accept'
    EDIT = 'edit'
    REJECT = 'reject'
    REQUEST_INFO = 'request_info'
    REFER = 'refer'


class QueryScope(StrEnum):
    Q0 = 'Q0'
    Q1 = 'Q1'
    Q2 = 'Q2'
    Q3 = 'Q3'


class PlanStatus(StrEnum):
    DRAFT = 'draft'
    APPROVED = 'approved'
    EXECUTING = 'executing'
    COMPLETED = 'completed'
    EXPIRED = 'expired'
    CANCELLED = 'cancelled'
    BLOCKED = 'blocked'


class BillingState(StrEnum):
    RESERVED = 'reserved'
    DISPATCHING = 'dispatching'
    CONFIRMED = 'confirmed'
    CANCELLED_BEFORE_SEND = 'cancelled_before_send'
    RELEASED = 'released'
    SENT_UNKNOWN = 'sent_unknown'


class ProviderStatus(StrEnum):
    SUCCESS = 'success'
    FAILED = 'failed'
    SENT_UNKNOWN = 'sent_unknown'
    BLOCKED = 'blocked'


class PatchStatus(StrEnum):
    PROPOSED = 'proposed'
    APPROVED = 'approved'
    APPLIED = 'applied'
    MANUAL_REQUIRED = 'manual_required'
    REJECTED = 'rejected'


class ApprovalStatus(StrEnum):
    VALID = 'valid'
    REVOKED = 'revoked'
    STALE = 'stale'


class ArtifactMode(StrEnum):
    DRAFT = 'draft'
    APPROVED = 'approved'


class Role(StrEnum):
    ADMIN = 'admin'
    HANDLING_LAWYER = 'handling_lawyer'
    REVIEWING_LAWYER = 'reviewing_lawyer'
    ASSISTANT = 'assistant'


class JobState(StrEnum):
    QUEUED = 'queued'
    RUNNING = 'running'
    COMPLETED = 'completed'
    FAILED = 'failed'
    CANCELLED = 'cancelled'
    BLOCKED = 'blocked'


class AcceptanceStatus(StrEnum):
    NOT_RUN = 'NOT_RUN'
    PASS = 'PASS'
    FAIL = 'FAIL'
    NOT_IMPLEMENTED = 'NOT_IMPLEMENTED'
    NOT_SUPPORTED = 'NOT_SUPPORTED'
    BLOCKED = 'BLOCKED'


class ReadinessStatus(StrEnum):
    GO = 'GO'
    NO_GO = 'NO_GO'
    BLOCKED = 'BLOCKED'


class GateIssue(DomainModel):
    code: ErrorCode
    scope: GateScope
    blocking_action: NonEmpty
    reason: NonEmpty
    remediation: NonEmpty
    resolved_by: UUID | None


class Matter(DomainModel):
    id: UUID
    client_ref: NonEmpty
    title: NonEmpty
    jurisdiction: NonEmpty
    contract_type: ContractType
    review_mode: ReviewMode
    position: Position | None
    objectives: tuple[NonEmpty, ...]
    member_ids: frozenset[UUID]
    status: MatterStatus
    active_fact_version: PositiveInt | None
    active_policy_version: PositiveInt | None
    gate_issues: tuple[GateIssue, ...]

    @property
    def review_route(self) -> ReviewRoute:
        return ReviewRoute.SPECIALIST if self.contract_type == ContractType.UNKNOWN else ReviewRoute.FULL


class DocumentVersion(DomainModel):
    id: UUID
    matter_id: UUID
    original_name: NonEmpty
    mime: NonEmpty
    sha256: SHA256
    storage_ref: NonEmpty
    byte_size: NonNegativeInt
    uploaded_by: UUID
    created_at: UTCDatetime
    baseline_view: BaselineView
    part_inventory: tuple[NonEmpty, ...]
    page_count: PositiveInt | None
    parse_status: ParseStatus
    unsupported_parts: tuple[NonEmpty, ...]
    supersedes_id: UUID | None

    @model_validator(mode='after')
    def distinct_predecessor(self) -> DocumentVersion:
        if self.supersedes_id == self.id:
            raise ValueError('a document version cannot supersede itself')
        return self


class Anchor(DomainModel):
    id: UUID
    document_version_id: UUID
    part_name: NonEmpty
    element_id: NonEmpty
    kind: AnchorKind
    quote: str
    quote_sha256: SHA256
    start: NonNegativeInt
    end: NonNegativeInt
    table: NonNegativeInt | None
    row: NonNegativeInt | None
    cell: NonNegativeInt | None
    page: PositiveInt | None
    bbox: tuple[float, float, float, float] | None

    @model_validator(mode='after')
    def exact_location(self) -> Anchor:
        if hashlib.sha256(self.quote.encode('utf-8')).hexdigest() != self.quote_sha256:
            raise ValueError('quote_sha256 does not match the exact UTF-8 quote')
        if self.end < self.start or self.end - self.start != len(self.quote):
            raise ValueError('anchor offsets must cover the exact quote using [start,end)')
        table_fields = (self.table, self.row, self.cell)
        if self.kind == AnchorKind.TABLE_CELL and any(value is None for value in table_fields):
            raise ValueError('table_cell requires zero-based table, row and cell')
        if self.kind != AnchorKind.TABLE_CELL and any(value is not None for value in table_fields):
            raise ValueError('table coordinates belong only to a table_cell')
        if self.kind == AnchorKind.PDF_SPAN and (self.page is None or self.bbox is None):
            raise ValueError('pdf_span requires a one-based page and bbox')
        if self.kind != AnchorKind.PDF_SPAN and (self.page is not None or self.bbox is not None):
            raise ValueError('PDF coordinates belong only to a pdf_span')
        if self.bbox is not None:
            x0, y0, x1, y1 = self.bbox
            if not all(Decimal(str(v)).is_finite() for v in self.bbox) or x0 < 0 or y0 < 0 or x1 <= x0 or y1 <= y0:
                raise ValueError('bbox must be finite, nonnegative and ordered (x0,y0,x1,y1)')
        return self


class TextFactValue(DomainModel):
    kind: Literal['text']
    value: Annotated[str, Field(strict=True)]


class BooleanFactValue(DomainModel):
    kind: Literal['bool']
    value: Annotated[bool, Field(strict=True)]


class IntegerFactValue(DomainModel):
    kind: Literal['integer']
    value: Annotated[int, Field(strict=True)]


class DecimalFactValue(DomainModel):
    kind: Literal['decimal']
    value: ExactDecimal


class DateFactValue(DomainModel):
    kind: Literal['date']
    value: date

    @field_validator('value', mode='before')
    @classmethod
    def exact_date(cls, value: object) -> date:
        if type(value) is date:
            return value
        if isinstance(value, str):
            parsed = date.fromisoformat(value)
            if parsed.isoformat() == value:
                return parsed
        raise ValueError('date fact values require a date or YYYY-MM-DD string')


class DatetimeFactValue(DomainModel):
    kind: Literal['datetime']
    value: UTCDatetime

    @field_validator('value', mode='before')
    @classmethod
    def explicit_timestamp(cls, value: object) -> object:
        if not isinstance(value, (str, datetime)):
            raise ValueError('datetime fact values require an explicit aware timestamp')
        return value


class NullFactValue(DomainModel):
    kind: Literal['null']
    value: None


FactValue = Annotated[
    Union[TextFactValue, BooleanFactValue, IntegerFactValue, DecimalFactValue,
          DateFactValue, DatetimeFactValue, NullFactValue],
    Field(discriminator='kind'),
]


class Fact(DomainModel):
    id: UUID
    matter_id: UUID
    version: PositiveInt
    field: NonEmpty
    typed_value: FactValue
    unit: NonEmpty | None
    provenance_type: ProvenanceType
    anchor_ids: tuple[UUID, ...]
    receipt_ids: tuple[UUID, ...]
    confirmation_status: ConfirmationStatus
    confirmed_by: UUID | None
    confirmed_at: UTCDatetime | None
    verification_ids: tuple[UUID, ...] = Field(default=(), exclude_if=lambda value: not value)

    @model_validator(mode='after')
    def confirmed_requires_evidence(self) -> Fact:
        if self.provenance_type == 'source_verification':
            if len(self.verification_ids) != 1 or self.anchor_ids or self.receipt_ids:
                raise ValueError('independent source verification required; not a PDF anchor')
        elif self.verification_ids:
            raise ValueError('verification cannot impersonate document provenance')
        if isinstance(self.typed_value, DecimalFactValue) and self.unit is None:
            raise ValueError('Decimal facts require an explicit unit')
        if self.confirmation_status in {ConfirmationStatus.CONFIRMED, ConfirmationStatus.CORRECTED}:
            if self.confirmed_by is None or self.confirmed_at is None:
                raise ValueError('a confirmed/corrected fact requires confirmer and time')
        return self


class PartyCandidate(DomainModel):
    candidate_id: UUID
    name: NonEmpty
    credit_code: NonEmpty | None
    source: NonEmpty


class Party(DomainModel):
    id: UUID
    matter_id: UUID
    role: NonEmpty
    name_raw: NonEmpty
    name_confirmed: NonEmpty | None
    credit_code: NonEmpty | None
    entity_id: UUID | None
    resolution_status: ResolutionStatus
    candidate_evidence: tuple[PartyCandidate, ...]
    confirmed_by: UUID | None

    @model_validator(mode='after')
    def confirmed_identity(self) -> Party:
        if self.resolution_status == ResolutionStatus.CONFIRMED and (self.confirmed_by is None or self.name_confirmed is None):
            raise ValueError('confirmed party requires explicit name and confirmer')
        return self


class AuthorityInput(DomainModel):
    title: NonEmpty
    issuer: NonEmpty
    url: NonEmpty
    article: NonEmpty | None
    text_snapshot: str
    snapshot_sha256: SHA256
    promulgated_at: date | None
    effective_from: date | None
    effective_to: date | None
    jurisdiction: NonEmpty
    legal_rank: NonEmpty
    fetch_status: FetchStatus
    fetched_at: UTCDatetime | None
    verification_status: VerificationStatus
    verified_by: UUID | None
    verified_at: UTCDatetime | None

    @model_validator(mode='after')
    def verified_snapshot(self) -> AuthorityInput:
        if hashlib.sha256(self.text_snapshot.encode('utf-8')).hexdigest() != self.snapshot_sha256:
            raise ValueError('authority hash must match the exact snapshot')
        if self.effective_from is not None and self.effective_to is not None and self.effective_to < self.effective_from:
            raise ValueError('effective_to must not precede effective_from')
        if self.fetch_status == FetchStatus.FETCHED and self.fetched_at is None:
            raise ValueError('fetched authority requires an acquisition timestamp')
        if self.verification_status == VerificationStatus.VERIFIED:
            if self.verified_by is None or self.verified_at is None or not self.text_snapshot.strip():
                raise ValueError('verified authority requires reviewer, time and source text')
            if self.fetch_status != FetchStatus.FETCHED:
                raise ValueError('unfetched authority cannot be verified')
        return self


class Authority(AuthorityInput):
    id: UUID


class AuthoritySourceView(Authority):
    current_verified: bool
    superseded: bool


class AuthoritySourcePage(DomainModel):
    items: tuple[AuthoritySourceView, ...]
    next_cursor: UUID | None


class Rule(DomainModel):
    id: UUID
    version: PositiveInt
    contract_types: tuple[ContractType, ...]
    positions: tuple[Position, ...]
    trigger_facts: tuple[NonEmpty, ...]
    exception_facts: tuple[NonEmpty, ...]
    basis_kind: BasisKind
    authority_ids: tuple[UUID, ...]
    finding_template: NonEmpty
    coverage_ids: Annotated[tuple[CoverageId, ...], Field(min_length=1)]
    status: RuleStatus
    approved_by: UUID | None
    approved_at: UTCDatetime | None

    @model_validator(mode='after')
    def approval_evidence(self) -> Rule:
        if len(set(self.coverage_ids)) != len(self.coverage_ids):
            raise ValueError('rule coverage_ids cannot be duplicated')
        if self.status == RuleStatus.APPROVED:
            if self.approved_by is None or self.approved_at is None:
                raise ValueError('approved rule requires an actual approver and time')
            if self.basis_kind == BasisKind.LAW and not self.authority_ids:
                raise ValueError('approved law rule requires authority references')
        return self


def _validate_edit_fields(value):
    fields = (value.edited_analysis, value.edited_recommendation, value.edited_replacement_text)
    if value.decision != HumanDecisionKind.EDIT and any(v is not None for v in fields):
        raise ValueError('only edit may carry explicit edited text')
    if any(v is not None for v in fields) and (value.edited_analysis is None or value.edited_recommendation is None):
        raise ValueError('explicit edit requires analysis and recommendation')
    if value.edited_replacement_text is not None and not value.edited_replacement_text.strip():
        raise ValueError('explicit replacement cannot be blank')
    return value


class FindingBasisReviewInput(DomainModel):
    kind: Literal['law', 'business_preference'] = 'law'
    authority_id: UUID | None = None
    source_sha256: SHA256 | None = None
    quote: Annotated[NonEmpty, Field(max_length=8000)] | None = None
    proposition: Annotated[NonEmpty, Field(max_length=2000)]
    support: Literal['pending', 'supported', 'not_supported', 'not_applicable']
    support_reason: Annotated[NonEmpty, Field(max_length=2000)]
    applicability: Literal['pending', 'applies', 'not_applies', 'not_applicable']
    applicability_reason: Annotated[NonEmpty, Field(max_length=2000)]
    event_date: date | None = None
    policy_sha256: SHA256
    standard_position: Annotated[NonEmpty, Field(max_length=2000)] | None = None
    fallback_position: Annotated[NonEmpty, Field(max_length=2000)] | None = None
    escalation_conditions: Annotated[NonEmpty, Field(max_length=2000)] | None = None

    @model_validator(mode='after')
    def distinguish_law_and_preference(self):
        if self.kind == 'law':
            if any(v is None for v in (self.authority_id,self.source_sha256,self.quote,self.event_date)):
                raise ValueError('law review requires exact source and event date')
            if self.support == 'not_applicable' or self.applicability == 'not_applicable':
                raise ValueError('law review requires separate support and applicability outcomes')
        elif (any(v is not None for v in (self.authority_id,self.source_sha256,self.quote,self.event_date))
              or self.support != 'not_applicable' or self.applicability != 'not_applicable'
              or any(v is None for v in (self.standard_position,self.fallback_position,self.escalation_conditions))):
            raise ValueError('business standards are not legal authority')
        return self


class FindingBasisReview(FindingBasisReviewInput):
    source_status: Literal['verified', 'unverified', 'not_legal_basis']
    source_dependency_sha256: SHA256 | None
    position: Position


class HumanDecision(DomainModel):
    decision: HumanDecisionKind
    reason: NonEmpty
    actor_id: UUID
    decided_at: UTCDatetime
    basis_review: FindingBasisReview | None = Field(default=None, exclude_if=lambda value:value is None)
    edited_analysis: Annotated[NonEmpty, Field(max_length=20000)] | None = None
    edited_recommendation: Annotated[NonEmpty, Field(max_length=20000)] | None = None
    edited_replacement_text: Annotated[str, Field(min_length=1, max_length=20000)] | None = None

    @model_validator(mode='after')
    def explicit_edit(self) -> HumanDecision:
        return _validate_edit_fields(self)

    @property
    def pending_edit(self) -> bool:
        return self.decision == HumanDecisionKind.EDIT and self.edited_analysis is None


class Finding(DomainModel):
    id: UUID
    run_id: UUID
    coverage_ids: Annotated[tuple[CoverageId, ...], Field(min_length=1)]
    issue_type: NonEmpty
    severity: Severity
    evidence_state: EvidenceState
    anchor_ids: tuple[UUID, ...]
    verification_ids: tuple[UUID, ...] = Field(default=(), exclude_if=lambda value:not value)
    cross_anchor_ids: tuple[UUID, ...]
    rule_ids: tuple[UUID, ...]
    authority_ids: tuple[UUID, ...]
    analysis: NonEmpty
    business_effect: NonEmpty
    recommendation: NonEmpty
    replacement_text: str | None
    fallback: str | None
    human_decision: HumanDecision | None

    @model_validator(mode='after')
    def distinct_dimensions(self) -> Finding:
        if len(set(self.coverage_ids)) != len(self.coverage_ids):
            raise ValueError('finding coverage_ids cannot be duplicated')
        return self


class FindingDecisionRecord(DomainModel):
    id: UUID
    sequence: PositiveInt
    matter_id: UUID
    run_id: UUID
    finding_id: UUID
    run_sha256: SHA256
    decision: HumanDecision


class ReviewDecisionSnapshot(DomainModel):
    matter_id: UUID
    run_id: UUID
    run_sha256: SHA256
    version: NonNegativeInt
    ordered_decisions: tuple[FindingDecisionRecord, ...]
    resolved_findings: tuple[Finding, ...]
    actor_id: UUID
    timestamp: UTCDatetime
    sha256: SHA256

    @model_validator(mode='after')
    def consistent_decisions(self) -> ReviewDecisionSnapshot:
        ids = {f.id for f in self.resolved_findings}
        if len(ids) != len(self.resolved_findings) or any(f.run_id != self.run_id for f in self.resolved_findings):
            raise ValueError('snapshot findings must identify this run')
        sequences = [r.sequence for r in self.ordered_decisions]
        if sequences != sorted(set(sequences)) or len({r.finding_id for r in self.ordered_decisions}) != len(sequences):
            raise ValueError('snapshot decisions must be ordered and latest per finding')
        if any(r.matter_id != self.matter_id or r.run_id != self.run_id or r.run_sha256 != self.run_sha256
               or r.finding_id not in ids for r in self.ordered_decisions):
            raise ValueError('snapshot decision object binding differs')
        if self.version != max(sequences, default=0):
            raise ValueError('snapshot version must identify last decision sequence')
        payload = self.model_dump(mode='json', exclude={'sha256'})
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False,
            separators=(',', ':'), allow_nan=False).encode()).hexdigest()
        if digest != self.sha256:
            raise ValueError('snapshot hash differs')
        return self


class ReviewDecisionAuthorityStatus(DomainModel):
    """Live internal qualification view; never an approval or frozen snapshot."""
    matter_id: UUID
    run_id: UUID
    decision_snapshot_sha256: SHA256
    status: Literal['current', 'recheck_required']
    recheck_finding_ids: tuple[UUID, ...]

    @model_validator(mode='after')
    def consistent_recheck(self) -> ReviewDecisionAuthorityStatus:
        if len(set(self.recheck_finding_ids)) != len(self.recheck_finding_ids):
            raise ValueError('recheck findings cannot be duplicated')
        if (self.status == 'recheck_required') != bool(self.recheck_finding_ids):
            raise ValueError('authority status must identify required rechecks')
        return self


class CoverageItem(DomainModel):
    coverage_id: CoverageId
    status: CoverageStatus
    examined_anchor_ids: tuple[UUID, ...]
    rule_ids: tuple[UUID, ...]
    rationale: str | None
    finding_ids: tuple[UUID, ...]

    @model_validator(mode='after')
    def justified_status(self) -> CoverageItem:
        if self.status in {CoverageStatus.NOT_APPLICABLE, CoverageStatus.REVIEWED_NO_ISSUE}:
            if self.rationale is None or not self.rationale.strip():
                raise ValueError('not_applicable/reviewed_no_issue require a factual rationale')
        if self.status == CoverageStatus.REVIEWED_ISSUE and not self.finding_ids:
            raise ValueError('reviewed_issue requires at least one finding')
        if self.status in {CoverageStatus.NOT_APPLICABLE, CoverageStatus.REVIEWED_NO_ISSUE} and self.finding_ids:
            raise ValueError('no-issue/not-applicable coverage cannot contain issue findings')
        if len(set(self.finding_ids)) != len(self.finding_ids):
            raise ValueError('coverage finding_ids cannot be duplicated')
        return self


class RunManifest(DomainModel):
    schema_version: Literal['2.0'] = '2.0'
    contract_type: ContractType
    document_hashes: Mapping[UUID, SHA256]
    fact_snapshot_sha256: SHA256
    rules_sha256: SHA256
    policy_sha256: SHA256
    model_config_sha256: SHA256
    config_sha256: SHA256
    model_provider: NonEmpty = 'mock'

    @property
    def review_route(self) -> ReviewRoute:
        return ReviewRoute.SPECIALIST if self.contract_type == ContractType.UNKNOWN else ReviewRoute.FULL

    @field_validator('document_hashes')
    @classmethod
    def readonly_hashes(cls, value: Mapping[UUID, str]) -> Mapping[UUID, str]:
        return _FrozenDict(value)

    @field_serializer('document_hashes')
    def serialize_hashes(self, value: Mapping[UUID, str]) -> dict[str, str]:
        return {str(key): hash_value for key, hash_value in value.items()}


class ModelUsage(DomainModel):
    provider: NonEmpty
    model: NonEmpty
    operation: NonEmpty
    request_id: NonEmpty
    input_tokens: NonNegativeInt
    output_tokens: NonNegativeInt
    cost: Credits
    unit: NonEmpty


class ReviewRun(DomainModel):
    id: UUID
    matter_id: UUID
    manifest: RunManifest
    status: RunStatus
    coverage: Annotated[tuple[CoverageItem, ...], Field(min_length=18, max_length=18)]
    findings: tuple[Finding, ...]
    limitations: tuple[NonEmpty, ...]
    model_usage: tuple[ModelUsage, ...]
    started_at: UTCDatetime
    finished_at: UTCDatetime | None
    error_code: ErrorCode | None

    @model_validator(mode='after')
    def consistent_review(self) -> ReviewRun:
        dimensions = [item.coverage_id for item in self.coverage]
        if set(dimensions) != set(CoverageId) or len(set(dimensions)) != 18:
            raise ValueError('ReviewRun requires exactly the 18 distinct C01-C18 dimensions')
        findings = {finding.id: finding for finding in self.findings}
        if len(findings) != len(self.findings):
            raise ValueError('ReviewRun finding IDs cannot be duplicated')
        coverage = {item.coverage_id: item for item in self.coverage}
        for finding in self.findings:
            if finding.run_id != self.id:
                raise ValueError('finding.run_id must identify this ReviewRun')
            for dimension in finding.coverage_ids:
                if finding.id not in coverage[dimension].finding_ids:
                    raise ValueError('each finding dimension must link back to the finding')
        for item in self.coverage:
            for finding_id in item.finding_ids:
                if finding_id not in findings or item.coverage_id not in findings[finding_id].coverage_ids:
                    raise ValueError('coverage finding reference is missing or points to another dimension')
        if self.finished_at is not None and self.finished_at < self.started_at:
            raise ValueError('finished_at cannot precede started_at')
        return self


def validate_review(payload: dict) -> ReviewRun:
    return ReviewRun.model_validate(payload)


class ToolBinding(DomainModel):
    capability_key: NonEmpty
    provider: NonEmpty
    tool_name: NonEmpty
    input_schema_snapshot: dict[str, JsonValue]
    output_schema_snapshot: dict[str, JsonValue]
    schema_hash: SHA256
    endpoint_config_ref: NonEmpty
    price_snapshot_id: UUID | None
    enabled: bool
    approved_by: UUID | None
    approved_at: UTCDatetime | None

    @model_validator(mode='after')
    def enabled_requires_approval(self) -> ToolBinding:
        if self.enabled and (self.approved_by is None or self.approved_at is None or self.price_snapshot_id is None):
            raise ValueError('enabled tool requires approver, time and price snapshot')
        return self


class QueryItemInput(DomainModel):
    capability_key: NonEmpty
    pages: PositiveInt


class QueryPlanItem(QueryItemInput):
    id: UUID
    tool_binding_ref: NonEmpty
    parameters: dict[str, JsonValue]
    max_credits: Credits
    price_snapshot_id: UUID


class QueryPlan(DomainModel):
    id: UUID
    matter_id: UUID
    version: PositiveInt
    party_id: UUID
    purpose: NonEmpty
    items: tuple[QueryPlanItem, ...]
    estimated_max_credits: Credits
    max_calls: NonNegativeInt
    scope: QueryScope
    authorization_id: UUID | None
    status: PlanStatus
    expires_at: UTCDatetime
    plan_sha256: SHA256


class QueryReceipt(DomainModel):
    id: UUID
    plan_id: UUID
    item_id: UUID
    idempotency_key: NonEmpty
    status: ProviderStatus
    query_at: UTCDatetime
    provider_trace_id: NonEmpty | None
    price_snapshot_id: UUID
    raw_ref: NonEmpty | None
    raw_sha256: SHA256 | None
    normalized_summary: str
    coverage_limit: tuple[NonEmpty, ...]
    charged_credits: Credits | None
    billing_state: BillingState


class BudgetEntry(DomainModel):
    id: UUID
    matter_id: UUID
    plan_item_id: UUID
    idempotency_key: NonEmpty
    reserved_credits: Credits
    confirmed_credits: Credits | None
    status: BillingState
    price_snapshot_id: UUID
    created_at: UTCDatetime
    updated_at: UTCDatetime
    reconciliation_ref: NonEmpty | None


class Patch(DomainModel):
    id: UUID
    finding_id: UUID
    document_version_id: UUID
    anchor_id: UUID
    old_text: str
    new_text: str
    old_text_sha256: SHA256
    status: PatchStatus
    reason: NonEmpty
    approved_by: UUID | None

    @model_validator(mode='after')
    def approved_exact_patch(self) -> Patch:
        if hashlib.sha256(self.old_text.encode('utf-8')).hexdigest() != self.old_text_sha256:
            raise ValueError('patch hash must match the exact old text')
        if self.status in {PatchStatus.APPROVED, PatchStatus.APPLIED} and self.approved_by is None:
            raise ValueError('approved/applied patch requires an approver')
        return self


class Approval(DomainModel):
    id: UUID
    matter_id: UUID
    approver_id: UUID
    audience: Audience
    review_snapshot_sha256: SHA256
    artifact_manifest_sha256: SHA256
    scope: tuple[NonEmpty, ...]
    limitations: tuple[NonEmpty, ...]
    approved_at: UTCDatetime
    status: ApprovalStatus
    exception_authorization_id: UUID | None


class ExportArtifact(DomainModel):
    id: UUID
    matter_id: UUID
    run_id: UUID
    audience: Audience
    type: NonEmpty
    content_sha256: SHA256
    storage_ref: NonEmpty
    mode: ArtifactMode
    approval_id: UUID | None
    created_at: UTCDatetime
    superseded: bool

    @model_validator(mode='after')
    def formal_artifact_requires_approval(self) -> ExportArtifact:
        if self.mode == ArtifactMode.APPROVED and self.approval_id is None:
            raise ValueError('approved artifact requires approval_id')
        return self


class AuditEvent(DomainModel):
    id: UUID
    matter_id: UUID
    actor_id: UUID
    action: NonEmpty
    entity_type: NonEmpty
    entity_id: UUID
    before_hash: SHA256 | None
    after_hash: SHA256 | None
    timestamp: UTCDatetime
    reason: NonEmpty
    correlation_id: UUID


class Actor(DomainModel):
    user_id: UUID
    roles: frozenset[Role]
    session_id: UUID


class VersionInput(DomainModel):
    matter_id: UUID
    original_name: NonEmpty
    mime: NonEmpty
    baseline_view: BaselineView | None
    supersedes_id: UUID | None


class UploadMeta(VersionInput):
    """File content is supplied separately through a file stream."""


class AnchoredSpan(Anchor):
    """An exact extracted span uses the same anchor vocabulary."""


class ParseResult(DomainModel):
    version_id: UUID
    anchors: tuple[Anchor, ...]
    pages: tuple[PositiveInt, ...]
    parts: tuple[NonEmpty, ...]
    unsupported_parts: tuple[NonEmpty, ...]
    quality_issues: tuple[NonEmpty, ...]

    @model_validator(mode='after')
    def anchors_match_version(self) -> ParseResult:
        if any(anchor.document_version_id != self.version_id for anchor in self.anchors):
            raise ValueError('parse anchors must belong to the parsed version')
        if len({anchor.id for anchor in self.anchors}) != len(self.anchors):
            raise ValueError('parse anchor IDs cannot be duplicated')
        return self


class FactDecision(DomainModel):
    fact_id: UUID
    decision: Literal['confirmed', 'corrected', 'rejected']
    confirmed_value: FactValue
    reason: NonEmpty

class FactSnapshot(DomainModel):
    version: PositiveInt
    facts: tuple[Fact, ...]
    sha256: SHA256

    @model_validator(mode='after')
    def consistent_fact_versions(self) -> FactSnapshot:
        if any(fact.version != self.version for fact in self.facts):
            raise ValueError('facts must belong to the snapshot version')
        if len({fact.id for fact in self.facts}) != len(self.facts):
            raise ValueError('snapshot fact IDs cannot be duplicated')
        if len({fact.matter_id for fact in self.facts}) > 1:
            raise ValueError('a fact snapshot cannot combine multiple matters')
        return self


class ArithmeticOperator(StrEnum):
    ADD = 'add'
    SUBTRACT = 'subtract'
    MULTIPLY = 'multiply'
    DIVIDE = 'divide'
    POWER = 'power'


class LiteralExpression(DomainModel):
    kind: Literal['literal']
    value: ExactDecimal


class VariableExpression(DomainModel):
    kind: Literal['variable']
    name: Annotated[str, StringConstraints(pattern=r'^[A-Za-z][A-Za-z0-9_]*$')]


class BinaryExpression(DomainModel):
    kind: Literal['binary']
    operator: ArithmeticOperator
    left: ExpressionNode
    right: ExpressionNode


ExpressionNode = Annotated[Union[LiteralExpression, VariableExpression, BinaryExpression], Field(discriminator='kind')]
BinaryExpression.model_rebuild()


class SafeExpression(DomainModel):
    ast: ExpressionNode
    unit: NonEmpty


class CalculationInput(DomainModel):
    name: NonEmpty
    value: ExactDecimal
    unit: NonEmpty
    fact_ids: tuple[UUID, ...]


class RoundingSpec(DomainModel):
    mode: Literal['ROUND_HALF_EVEN', 'ROUND_HALF_UP', 'ROUND_HALF_DOWN', 'ROUND_DOWN', 'ROUND_UP', 'ROUND_FLOOR', 'ROUND_CEILING', 'ROUND_05UP']
    quantum: Annotated[ExactDecimal, Field(gt=0)]


class CalculationResult(DomainModel):
    value: ExactDecimal
    unit: NonEmpty
    formula: SafeExpression
    inputs: tuple[CalculationInput, ...]
    rounding: RoundingSpec
    assumptions: tuple[NonEmpty, ...]


class PartyDecision(DomainModel):
    selected_candidate_id: UUID
    reason: NonEmpty
    confirmed_by: UUID


class PolicySnapshot(DomainModel):
    client_ref: NonEmpty
    version: PositiveInt
    sha256: SHA256
    preferences: tuple[NonEmpty, ...]
    approved_by: UUID | None
    approved_at: UTCDatetime | None


class ReviewContext(DomainModel):
    matter: Matter
    document_versions: tuple[DocumentVersion, ...]
    fact_snapshot: FactSnapshot
    position: Position
    rules: tuple[Rule, ...]
    policy: PolicySnapshot
    authority_ids: tuple[UUID, ...]
    allowed_scope: tuple[CoverageId, ...]


class EvidenceBundle(DomainModel):
    anchors: dict[UUID, Anchor]
    authorities: dict[UUID, Authority]
    receipts: dict[UUID, QueryReceipt]

    @model_validator(mode='after')
    def stable_evidence_keys(self) -> EvidenceBundle:
        for mapping in (self.anchors, self.authorities, self.receipts):
            if any(key != value.id for key, value in mapping.items()):
                raise ValueError('evidence map keys must match the object IDs')
        return self


class RuleSnapshot(DomainModel):
    rules: tuple[Rule, ...]
    sha256: SHA256


class RuleExclusion(DomainModel):
    rule_id: UUID
    version: PositiveInt
    reason: Literal['not_applicable', 'missing_facts', 'unapproved', 'unsupported']
    rationale: NonEmpty


class RuleSelection(DomainModel):
    applied: tuple[Rule, ...]
    excluded: tuple[RuleExclusion, ...]


class ApprovalEvidence(DomainModel):
    reviewer_id: UUID
    reviewed_at: UTCDatetime
    text_snapshot_sha256: SHA256
    applicability: NonEmpty
    exceptions: NonEmpty


class ModelRequest(DomainModel):
    model_config = ConfigDict(serialize_by_alias=True)

    operation: NonEmpty
    context: ReviewContext
    output_schema: dict[str, JsonValue] = Field(alias='schema')
    budget_approval_id: UUID | None
    usage_limit: ModelUsageLimit


class ModelUsageLimit(DomainModel):
    max_input_tokens: NonNegativeInt
    max_output_tokens: NonNegativeInt
    max_cost: Credits
    unit: NonEmpty


ModelRequest.model_rebuild()


class ModelResponse(DomainModel):
    payload: dict[str, JsonValue]
    usage: ModelUsage
    provider: NonEmpty
    model: NonEmpty
    request_id: NonEmpty
    status: ProviderStatus


def _bounded_synthetic_decimal(value: object) -> Decimal:
    """Small exact offline numbers; no account-price or currency inference."""
    if type(value) not in (str, int, Decimal) or len(str(value)) > 80:
        raise ValueError('bounded exact synthetic Decimal required')
    try:
        parsed = Decimal(value)
    except DecimalException as exc:
        raise ValueError('valid synthetic Decimal required') from exc
    if not parsed.is_finite():
        raise ValueError('finite synthetic Decimal required')
    parts = parsed.as_tuple()
    if len(parts.digits) > 30 or not -18 <= parts.exponent <= 6 or not 0 <= parsed <= 1000000:
        raise ValueError('synthetic Decimal outside offline bounds')
    return parsed


SyntheticDecimal = Annotated[Decimal, BeforeValidator(_bounded_synthetic_decimal)]
DeepSeekModelId = Literal['deepseek-flash', 'deepseek-v4-pro']
DeepSeekOperation = Literal['extract_facts', 'review_chunk', 'review_cross_clauses']


class DeepSeekOfflineUsage(DomainModel):
    """Vendor-reported counts; unknown cost is never replaced by zero."""
    prompt_tokens: Annotated[int, Field(strict=True, ge=0, le=4096)]
    prompt_cache_hit_tokens: Annotated[int, Field(strict=True, ge=0, le=4096)]
    prompt_cache_miss_tokens: Annotated[int, Field(strict=True, ge=0, le=4096)]
    completion_tokens: Annotated[int, Field(strict=True, ge=0, le=1024)]
    total_tokens: Annotated[int, Field(strict=True, ge=0, le=5120)]
    cached_tokens: Annotated[int, Field(strict=True, ge=0, le=4096)] | None
    reasoning_tokens: Annotated[int, Field(strict=True, ge=0, le=1024)] | None
    cost: Credits | None
    unit: Literal['USD'] = 'USD'
    pricing_status: Literal['unknown', 'estimated_synthetic'] = 'unknown'

    @model_validator(mode='after')
    def consistent_offline_usage(self) -> DeepSeekOfflineUsage:
        if self.prompt_tokens != self.prompt_cache_hit_tokens + self.prompt_cache_miss_tokens:
            raise ValueError('prompt count must equal cache hit plus cache miss')
        if self.total_tokens != self.prompt_tokens + self.completion_tokens:
            raise ValueError('total count must equal prompt plus completion')
        if self.cached_tokens is not None and self.cached_tokens != self.prompt_cache_hit_tokens:
            raise ValueError('cached count must equal cache hit count')
        if self.reasoning_tokens is not None and self.reasoning_tokens > self.completion_tokens:
            raise ValueError('reasoning count exceeds completion count')
        if (self.pricing_status == 'unknown') != (self.cost is None):
            raise ValueError('cost and synthetic pricing status must agree')
        return self


class DeepSeekOfflineReply(DomainModel):
    """Protocol parsing only: no legal validation, approval, or paid receipt."""
    provider: Literal['deepseek'] = 'deepseek'
    model: DeepSeekModelId
    operation: DeepSeekOperation
    request_id: Annotated[str, StringConstraints(min_length=1, max_length=256)]
    payload: dict[str, JsonValue]
    usage: DeepSeekOfflineUsage
    status: Literal['OFFLINE_ONLY'] = 'OFFLINE_ONLY'
    validation_scope: Literal['protocol_only'] = 'protocol_only'


class DeepSeekSyntheticRates(DomainModel):
    """Explicit invented USD-per-million prices for offline arithmetic only."""
    input_hit_per_million: SyntheticDecimal
    input_miss_per_million: SyntheticDecimal
    output_per_million: SyntheticDecimal
    unit: Literal['USD'] = 'USD'
    pricing_status: Literal['synthetic'] = 'synthetic'


McpOfflineFixture = Literal['sales', 'service', 'lease', 'nda']


class McpOfflineExampleArguments(DomainModel):
    """The complete offline tool input; no material, identity or approval fields."""
    fixture: McpOfflineFixture
    operation: DeepSeekOperation
    model: DeepSeekModelId

    @field_validator('fixture', 'operation', 'model', mode='before')
    @classmethod
    def exact_enum_text(cls, value: object) -> object:
        if type(value) is not str:
            raise ValueError('exact enum text required')
        return value


class McpOfflineStatus(DomainModel):
    synthetic: Literal[True] = True
    status: Literal['OFFLINE_ONLY'] = 'OFFLINE_ONLY'
    real_models_enabled: Literal[False] = False
    qcc_enabled: Literal[False] = False
    production_status: Literal['PRODUCTION_BLOCKED'] = 'PRODUCTION_BLOCKED'
    transport_frame_limit: Literal['NOT_ESTABLISHED'] = 'NOT_ESTABLISHED'
    os_cpu_memory_sandbox: Literal['NOT_ESTABLISHED'] = 'NOT_ESTABLISHED'
    legal_review_available: Literal[False] = False
    chatgpt_connection_verified: Literal[False] = False
    scope: Literal['controlled_local_process_synthetic_data_only'] = 'controlled_local_process_synthetic_data_only'


class McpOfflineExample(DomainModel):
    fixture: McpOfflineFixture
    fixture_sha256: SHA256
    request: dict[str, JsonValue]
    reply: DeepSeekOfflineReply
    synthetic: Literal[True] = True
    status: Literal['OFFLINE_ONLY'] = 'OFFLINE_ONLY'
    response_origin: Literal['manually_constructed_not_supplier'] = 'manually_constructed_not_supplier'
    token_origin: Literal['invented_example_counts_not_supplier'] = 'invented_example_counts_not_supplier'
    legal_opinion: Literal[False] = False
    notice: Literal['独立虚构材料；响应及token人工构造，非供应商结果，非法律意见。'] = '独立虚构材料；响应及token人工构造，非供应商结果，非法律意见。'


class ProviderConfig(DomainModel):
    endpoint: NonEmpty
    transport: Literal['stdio', 'streamable_http', 'sse', 'mock']
    secret_ref: NonEmpty | None
    approved_by: UUID | None
    approved_at: UTCDatetime | None


class ToolDefinition(DomainModel):
    name: NonEmpty
    input_schema_snapshot: dict[str, JsonValue]
    output_schema_snapshot: dict[str, JsonValue]


class ToolCatalog(DomainModel):
    provider: NonEmpty
    tools: tuple[ToolDefinition, ...]


class BindingInput(DomainModel):
    capability_key: NonEmpty
    provider: NonEmpty
    tool_name: NonEmpty
    input_schema_snapshot: dict[str, JsonValue]
    output_schema_snapshot: dict[str, JsonValue]
    schema_hash: SHA256
    endpoint_config_ref: NonEmpty
    unit_price: Credits | None
    price_unit: NonEmpty
    price_snapshot_id: UUID | None
    approved_by: UUID | None
    approved_at: UTCDatetime | None


class ProviderResult(DomainModel):
    status: ProviderStatus
    trace_id: NonEmpty | None
    raw_ref: NonEmpty | None
    raw_sha256: SHA256 | None
    billing_known: bool
    charged_credits: Credits | None


class BillingEvidence(DomainModel):
    bill_sha256: SHA256
    recorded_at: UTCDatetime
    charged_credits: Credits
    unit: NonEmpty
    approved_by: UUID


class QueryPlanInput(DomainModel):
    matter_id: UUID
    party_id: UUID
    purpose: NonEmpty
    items: tuple[QueryItemInput, ...]
    authorization_id: UUID | None
    scope: QueryScope


class Reservation(DomainModel):
    ledger_id: UUID
    credits: Credits
    calls: NonNegativeInt
    idempotency_key: NonEmpty
    status: BillingState


class PatchResult(DomainModel):
    status: Literal['applied', 'manual_required', 'rejected']
    reason: NonEmpty
    target_sha256: SHA256 | None


class ArtifactBundle(DomainModel):
    id: UUID
    matter_id: UUID
    run_id: UUID
    audience: Audience
    artifacts: tuple[ExportArtifact, ...]
    manifest_sha256: SHA256


class VerificationResult(DomainModel):
    ok: bool
    errors: tuple[NonEmpty, ...]
    warnings: tuple[NonEmpty, ...]
    checked: tuple[NonEmpty, ...]

    @model_validator(mode='after')
    def consistent_result(self) -> VerificationResult:
        if self.ok and self.errors:
            raise ValueError('a verification with errors cannot claim ok')
        return self


class ValidationResult(VerificationResult):
    """Validation evidence never changes a business approval state."""


class JobInput(DomainModel):
    matter_id: UUID
    job_type: NonEmpty
    parameters_sha256: SHA256


class JobStatus(DomainModel):
    id: UUID
    state: JobState
    stage: NonEmpty
    error_code: ErrorCode | None
    result_ref: NonEmpty | None


class DocumentReparseInput(DomainModel):
    document_hashes: Annotated[dict[UUID, SHA256], Field(min_length=1, max_length=100)]
    fact_version: Annotated[int, Field(strict=True, ge=0)]
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
    reconfirmation_acknowledged: StrictBool


# HTTP inputs share the domain vocabulary. Server identity, time, IDs and
# approval status are intentionally absent from client write inputs.
class LoginInput(DomainModel):
    username: Annotated[str, StringConstraints(min_length=1, max_length=128)]
    password: Annotated[str, StringConstraints(min_length=1, max_length=256)]


class MatterCreateInput(DomainModel):
    title: Annotated[NonEmpty, Field(max_length=300)]
    contract_type: ContractType
    review_mode: ReviewMode
    position: Position
    objectives: Annotated[tuple[NonEmpty, ...], Field(min_length=1, max_length=10)]
    reviewer_username: Annotated[NonEmpty, Field(max_length=128)] | None = None
    material_mode: Literal['synthetic', 'local'] = Field(default='synthetic', exclude_if=lambda value:value == 'synthetic')


def _intake_text(value: str) -> str:
    # Word/XML and browser renderers share the same accepted text alphabet.
    if any(not (c in '\t\n\r' or '\u0020' <= c <= '\ud7ff' or '\ue000' <= c <= '\ufffd'
                or '\U00010000' <= c <= '\U0010ffff') for c in value):
        raise ValueError('unsupported text character')
    return value


IntakeText = Annotated[str, StringConstraints(max_length=12000), AfterValidator(_intake_text)]
IntakeLabel = Annotated[NonEmpty, Field(max_length=300), AfterValidator(_intake_text)]


class IntakeMaterial(DomainModel):
    name: IntakeLabel
    state: Literal['needed', 'received', 'checked'] = 'needed'


class IntakeDraft(DomainModel):
    title: IntakeLabel
    contact: Annotated[IntakeText, Field(max_length=300)] = ''
    consultation: IntakeText = ''
    questions: Annotated[tuple[IntakeLabel, ...], Field(max_length=30)] = ()
    materials: Annotated[tuple[IntakeMaterial, ...], Field(max_length=30)] = ()
    follow_up_at: UTCDatetime | None = None
    follow_up_note: Annotated[IntakeText, Field(max_length=2000)] = ''
    status: Literal['open', 'waiting', 'closed'] = 'open'
    client_reply: IntakeText = ''
    internal_notes: IntakeText = ''


class IntakeCreateInput(DomainModel):
    request_id: UUID
    draft: IntakeDraft


class IntakeUpdateInput(DomainModel):
    expected_revision: PositiveInt
    draft: IntakeDraft


class IntakeConvertInput(DomainModel):
    expected_revision: PositiveInt
    matter: MatterCreateInput


class IntakeExportInput(DomainModel):
    revision: PositiveInt
    audience: Literal['client', 'internal']
    text_checked: StrictBool = False


class IntakeRecord(IntakeDraft):
    id: UUID
    revision: PositiveInt
    saved_at: UTCDatetime
    matter_id: UUID | None
    verification_status: Literal['unverified'] = 'unverified'
    consultation_origin: Literal['user', 'profile_summary'] = 'user'
    source_conversation_id: UUID | None = None
    source_profile_revision: NonNegativeInt | None = None


class ReceptionSource(DomainModel):
    id: SHA256
    title: IntakeLabel
    aliases: tuple[IntakeLabel, ...]
    text_sha256: SHA256
    paragraph_count: NonNegativeInt
    limitations: tuple[IntakeLabel, ...]
    verification_status: Literal['user_supplied_unverified'] = 'user_supplied_unverified'


class ReceptionReference(DomainModel):
    source_id: SHA256
    paragraph: PositiveInt
    quote_sha256: SHA256


class ReceptionPassage(ReceptionReference):
    title: IntakeLabel
    text: Annotated[IntakeText, Field(max_length=1200)]
    source_sha256: SHA256


class ReceptionKnowledgeCatalog(DomainModel):
    state: Literal['ready', 'not_configured']
    archive_sha256: SHA256 | None = None
    original_documents: NonNegativeInt = 0
    sources: tuple[ReceptionSource, ...] = ()


class ReceptionSearchResult(DomainModel):
    items: tuple[ReceptionPassage, ...] = ()


class ReceptionSourcePage(DomainModel):
    source: ReceptionSource
    items: tuple[ReceptionPassage, ...]
    next_start: NonNegativeInt | None = None


class ReceptionAssistantInput(DomainModel):
    expected_revision: PositiveInt
    mode: Literal['first_reply', 'materials', 'follow_up'] = 'first_reply'
    references: Annotated[tuple[ReceptionReference, ...], Field(max_length=4)] = ()

    @model_validator(mode='after')
    def distinct_references(self):
        keys = [(r.source_id, r.paragraph) for r in self.references]
        if len(keys) != len(set(keys)):
            raise ValueError('references cannot repeat')
        return self


class ReceptionConversationInput(ReceptionAssistantInput):
    request_id: UUID


class ReceptionAssistantPreview(DomainModel):
    intake_id: UUID
    revision: PositiveInt
    mode: Literal['first_reply', 'materials', 'follow_up']
    client_reply: IntakeText
    internal_notes: IntakeText
    prompt: Annotated[str, StringConstraints(max_length=20000)]
    references: tuple[ReceptionPassage, ...] = ()
    kind: Literal['template_draft'] = 'template_draft'
    model_calls: Literal[0] = 0


class PositionInput(DomainModel):
    position: Position
    objectives: Annotated[tuple[NonEmpty, ...], Field(min_length=1, max_length=10)]


class FactsConfirmInput(DomainModel):
    fact_version: PositiveInt
    decisions: Annotated[tuple[FactDecision, ...], Field(min_length=1, max_length=1000)]


class ReviewStartInput(DomainModel):
    fact_version: PositiveInt
    document_hashes: Mapping[UUID, SHA256]


class SyntheticAssistedPolicy(DomainModel):
    """Trusted server fiction registry, never supplied by a contract or HTTP body."""
    policy_id: Annotated[NonEmpty, Field(max_length=128)]
    purpose: Literal['assisted_draft']
    document_hashes: Annotated[tuple[SHA256, ...], Field(min_length=1, max_length=128)]
    candidate_source: Literal['manual_synthetic']

    @field_validator('document_hashes')
    @classmethod
    def distinct_registry(cls, values):
        if len(set(values)) != len(values): raise ValueError('registry hashes cannot be repeated')
        return values


class LocalMaterialPolicy(DomainModel):
    """Local human workpapers; never authorizes a supplier or chat connection."""
    policy_id: Literal['local-workpaper-v1'] = 'local-workpaper-v1'
    purpose: Literal['assisted_draft'] = 'assisted_draft'
    candidate_source: Literal['manual_local'] = 'manual_local'
    allowed_mime: Literal['application/vnd.openxmlformats-officedocument.wordprocessingml.document'] = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    external_processing: Literal[False] = False


FiniteCoordinate = Annotated[float, Field(allow_inf_nan=False, ge=0)]


class OCRPageSource(DomainModel):
    document_version_id: UUID
    document_sha256: SHA256
    page: Annotated[int, Field(strict=True, ge=1, le=200)]
    page_width_points: Annotated[float, Field(gt=0, allow_inf_nan=False)]
    page_height_points: Annotated[float, Field(gt=0, allow_inf_nan=False)]
    bitmap_width: Annotated[int, Field(strict=True, gt=0, le=8192)]
    bitmap_height: Annotated[int, Field(strict=True, gt=0, le=8192)]
    bitmap_sha256: SHA256
    coordinate_space: Literal['rendered_page_top_left']

    @model_validator(mode='after')
    def bounded_image(self):
        if self.bitmap_width*self.bitmap_height>16000000:raise ValueError('page pixels exceed limit')
        return self


class OCRBlock(DomainModel):
    raw_text: Annotated[str, Field(strict=True, max_length=4000)]
    polygon: Annotated[tuple[tuple[FiniteCoordinate,FiniteCoordinate],...],Field(min_length=4,max_length=4)]
    confidence: Annotated[float,Field(ge=0,le=1,allow_inf_nan=False)] | None
    alternatives: tuple[str,...] = ()
    verification_state: Literal['unverified'] = 'unverified'


class OCRResult(DomainModel):
    id: UUID
    source: OCRPageSource
    created_at: UTCDatetime
    engine: Literal['PaddleOCR-3.7.0/PaddleX-3.7.0/PaddlePaddle-3.3.0-CPU']
    asset_manifest_sha256: SHA256
    raw_output_sha256: SHA256
    blocks: Annotated[tuple[OCRBlock,...],Field(max_length=2000)]
    bitmap_to_page: tuple[float,float,float,float,float,float]
    reasons: tuple[NonEmpty,...]

    @model_validator(mode='after')
    def coordinates_match_source(self):
        s=self.source
        if self.bitmap_to_page!=(s.page_width_points/s.bitmap_width,0,0,s.page_height_points/s.bitmap_height,0,0):
            raise ValueError('coordinate transform mismatch')
        if any(x>s.bitmap_width or y>s.bitmap_height for block in self.blocks for x,y in block.polygon):
            raise ValueError('OCR polygon outside source bitmap')
        return self


class PageOCRInput(DomainModel):
    document_version_id: UUID
    document_sha256: SHA256
    page: Annotated[int,Field(strict=True,ge=1,le=200)]


class OCRCandidate(DomainModel):
    matter_id: UUID
    actor_id: UUID
    result: OCRResult
    sha256: SHA256


class PageVerificationInput(DomainModel):
    document_version_id: UUID
    document_sha256: SHA256
    fact_version: PositiveInt
    page: Annotated[int, Field(strict=True, ge=1, le=200)] | None
    # Omit absent DOCX locator to preserve historical PDF record digests.
    source_anchor_id: UUID | None = Field(default=None, exclude_if=lambda value: value is None)
    source_kind: Literal['visible_original', 'lawyer_transcription', 'provider_clarification']
    observed_text: Annotated[NonEmpty, Field(max_length=4000)]
    field: Annotated[NonEmpty, Field(max_length=100)]
    typed_value: FactValue
    unit: Annotated[NonEmpty, Field(max_length=32)] | None
    reason: Annotated[NonEmpty, Field(max_length=2000)]
    original_page_checked: Literal[True]
    previous_id: UUID | None
    candidate_id: UUID | None
    candidate_sha256: SHA256 | None

    @field_validator('original_page_checked', mode='before')
    @classmethod
    def explicit_check(cls, value):
        if value is not True: raise ValueError('explicit page check required')
        return value

    @model_validator(mode='after')
    def bounded_value(self):
        if (self.page is None) == (self.source_anchor_id is None):
            raise ValueError('exactly one PDF page or DOCX anchor required')
        if self.source_anchor_id is not None and self.candidate_id is not None:
            raise ValueError('OCR candidates are PDF only')
        if isinstance(self.typed_value, DecimalFactValue) and self.unit is None:
            raise ValueError('decimal source value requires unit')
        if len(self.typed_value.model_dump_json().encode()) > 4000:
            raise ValueError('source value too large')
        if (self.candidate_id is None) != (self.candidate_sha256 is None):
            raise ValueError('candidate id and digest required together')
        return self


class PageVerification(DomainModel):
    id: UUID
    matter_id: UUID
    fact_id: UUID
    actor_id: UUID
    created_at: UTCDatetime
    input: PageVerificationInput
    sha256: SHA256


class AssistedFactCandidate(DomainModel):
    field: Annotated[NonEmpty, Field(max_length=100)]
    typed_value: FactValue
    unit: Annotated[NonEmpty, Field(max_length=32)] | None
    anchor_ids: Annotated[tuple[UUID, ...], Field(min_length=1, max_length=8)]

    @model_validator(mode='after')
    def bounded_candidate(self):
        if len(set(self.anchor_ids)) != len(self.anchor_ids): raise ValueError('candidate anchors cannot repeat')
        if isinstance(self.typed_value, DecimalFactValue) and self.unit is None:
            raise ValueError('decimal candidate requires a unit')
        if len(self.typed_value.model_dump_json().encode('utf-8')) > 4000:
            raise ValueError('bounded candidate value required')
        return self


class AssistedFactsInput(DomainModel):
    document_version_id: UUID
    document_sha256: SHA256
    fact_version: PositiveInt
    candidates: Annotated[tuple[AssistedFactCandidate, ...], Field(min_length=1, max_length=64)]


class AssistedOpinionCandidate(DomainModel):
    coverage_ids: Annotated[tuple[CoverageId, ...], Field(min_length=1, max_length=18)]
    issue_type: Annotated[NonEmpty, Field(max_length=100)]
    severity: Severity
    evidence_state: Literal['unconfirmed', 'missing', 'conflicting']
    anchor_ids: Annotated[tuple[UUID, ...], Field(max_length=8)]
    verification_ids: Annotated[tuple[UUID, ...], Field(max_length=8)] = Field(default=(), exclude_if=lambda value:not value)
    analysis: Annotated[NonEmpty, Field(max_length=4000)]
    business_effect: Annotated[NonEmpty, Field(max_length=4000)]
    recommendation: Annotated[NonEmpty, Field(max_length=4000)]
    basis_kind: Literal['material_observation', 'business_preference', 'pending_authority']
    authority_refs: Annotated[tuple[Annotated[NonEmpty, Field(max_length=300)], ...], Field(max_length=8)]
    unknowns: Annotated[tuple[Annotated[NonEmpty, Field(max_length=500)], ...], Field(max_length=10)]

    @model_validator(mode='after')
    def distinct_references(self):
        if not self.anchor_ids and not self.verification_ids:raise ValueError('verified source reference required')
        if any(len(set(value)) != len(value) for value in (self.coverage_ids, self.anchor_ids, self.verification_ids,self.authority_refs, self.unknowns)):
            raise ValueError('candidate references cannot repeat')
        if self.authority_refs and self.basis_kind != 'pending_authority':
            raise ValueError('unverified legal references must stay pending')
        return self


class AssistedReviewInput(DomainModel):
    context_sha256: SHA256
    fact_version: PositiveInt
    document_hashes: Mapping[UUID, SHA256]
    examined_anchor_ids: Annotated[tuple[UUID, ...], Field(max_length=512)]
    examined_verification_ids: Annotated[tuple[UUID, ...], Field(max_length=256)] = Field(default=(), exclude_if=lambda value:not value)
    opinions: Annotated[tuple[AssistedOpinionCandidate, ...], Field(min_length=1, max_length=32)]

    @field_validator('document_hashes')
    @classmethod
    def readonly_hashes(cls, value):
        return _FrozenDict(value)

    @field_serializer('document_hashes')
    def serialize_hashes(self, value):
        return {str(key): digest for key, digest in value.items()}

    @model_validator(mode='after')
    def bounded_distinct_input(self):
        if not self.examined_anchor_ids and not self.examined_verification_ids:raise ValueError('examined source required')
        if len(set(self.examined_verification_ids))!=len(self.examined_verification_ids):raise ValueError('duplicate source record')
        if not 1 <= len(self.document_hashes) <= 32: raise ValueError('bounded document set required')
        if len(set(self.examined_anchor_ids)) != len(self.examined_anchor_ids): raise ValueError('examined anchors cannot repeat')
        values = [value.model_dump_json() for value in self.opinions]
        if len(set(values)) != len(values): raise ValueError('duplicate candidate opinions')
        return self


class AssistedReviewContextView(DomainModel):
    matter_id: UUID
    purpose: Literal['assisted_draft']
    context_sha256: SHA256
    policy_sha256: SHA256
    fact_version: PositiveInt
    document_hashes: Mapping[UUID, SHA256]
    eligible_anchor_ids: tuple[UUID, ...]
    eligible_verification_ids: tuple[UUID, ...] = Field(default=(), exclude_if=lambda value:not value)
    candidate_source: Literal['manual_synthetic', 'manual_local', 'local_plugin_unverified']
    real_model_calls: Literal[0] = 0
    qcc_calls: Literal[0] = 0
    model_inference: Literal['NOT_RUN', 'NOT_ATTESTED'] = 'NOT_RUN'

    @field_validator('document_hashes')
    @classmethod
    def readonly_hashes(cls, value):
        return _FrozenDict(value)

    @field_serializer('document_hashes')
    def serialize_hashes(self, value):
        return {str(key): digest for key, digest in value.items()}


class CaseBridgeConsent(DomainModel):
    context_sha256: SHA256
    share_with_chat: Literal[True]
    allow_candidate_submission: StrictBool = False

    @field_validator('share_with_chat', mode='before')
    @classmethod
    def explicit_consent(cls, value):
        if value is not True: raise ValueError('explicit consent required')
        return value


class CaseBridgeGrant(DomainModel):
    id: UUID
    matter_id: UUID
    context_sha256: SHA256
    expires_at: UTCDatetime
    read_only: StrictBool = True


class CaseBridgeReadingScope(DomainModel):
    version_id: UUID
    pages: tuple[PositiveInt, ...]
    parts: tuple[NonEmpty, ...]
    unsupported_parts: tuple[NonEmpty, ...]
    quality_issues: tuple[NonEmpty, ...]
    excluded_anchor_count: NonNegativeInt


class CaseBridgeContext(DomainModel):
    grant: CaseBridgeGrant
    context: AssistedReviewContextView
    title: NonEmpty
    contract_type: ContractType
    position: Position
    facts: tuple[Fact, ...]
    anchors: tuple[Anchor, ...]
    source_verifications: tuple[PageVerification, ...]
    reading_scope: tuple[CaseBridgeReadingScope, ...]
    limitations: tuple[NonEmpty, ...]
    synthetic: Literal[True] = True
    read_only: Literal[True] = True


class ManualCandidateReceipt(DomainModel):
    source: Literal['manual_synthetic', 'manual_local']
    submitted_by: UUID
    submitted_at: UTCDatetime
    real_model_calls: Literal[0] = 0
    qcc_calls: Literal[0] = 0
    model_inference: Literal['NOT_RUN'] = 'NOT_RUN'


class PluginCandidateReceipt(DomainModel):
    source: Literal['local_plugin_unverified'] = 'local_plugin_unverified'
    submitted_by: UUID
    submitted_at: UTCDatetime
    grant_id: UUID
    model_identity: Literal['UNVERIFIED'] = 'UNVERIFIED'
    model_inference: Literal['NOT_ATTESTED'] = 'NOT_ATTESTED'
    backend_model_calls: Literal[0] = 0
    qcc_calls: Literal[0] = 0


class PluginCandidateSubmission(DomainModel):
    grant_id: UUID
    matter_id: UUID
    context_sha256: SHA256
    input_sha256: SHA256
    run_id: UUID
    finding_ids: tuple[UUID, ...]
    source: Literal['local_plugin_unverified'] = 'local_plugin_unverified'
    disposition: Literal['awaiting_lawyer'] = 'awaiting_lawyer'


class ReviewProposal(DomainModel):
    id: UUID
    matter_id: UUID
    run_id: UUID
    policy_sha256: SHA256
    context_sha256: SHA256
    input_sha256: SHA256
    input: AssistedReviewInput
    finding_ids: tuple[UUID, ...]
    execution_receipt: Annotated[Union[ManualCandidateReceipt, PluginCandidateReceipt], Field(discriminator='source')]
    sha256: SHA256

    @model_validator(mode='after')
    def immutable_proposal_binding(self):
        if len(self.finding_ids) != len(self.input.opinions) or len(set(self.finding_ids)) != len(self.finding_ids):
            raise ValueError('proposal findings must correspond one to one')
        def digest(value):
            return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                separators=(',', ':'), allow_nan=False).encode()).hexdigest()
        if self.context_sha256 != self.input.context_sha256 or self.input_sha256 != digest(self.input.model_dump(mode='json')):
            raise ValueError('proposal input binding differs')
        if self.sha256 != digest(self.model_dump(mode='json', exclude={'sha256'})):
            raise ValueError('proposal content hash differs')
        return self


class EffectiveParagraph(DomainModel):
    anchor_id: UUID
    location: NonEmpty
    kind: AnchorKind
    original_text: str
    text: str
    patch_id: UUID | None = None


class EffectiveDocument(DomainModel):
    version_id: UUID
    original_sha256: SHA256
    original_name: NonEmpty
    baseline_view: BaselineView
    artifact_id: UUID | None = None
    paragraphs: tuple[EffectiveParagraph, ...]
    limitations: tuple[NonEmpty, ...]


class EffectiveTextSignal(DomainModel):
    kind: Literal['number', 'deadline', 'reference', 'old_value_remaining']
    document_version_id: UUID
    anchor_id: UUID
    quote: NonEmpty


class EffectiveTextSnapshot(DomainModel):
    bundle_id: UUID
    matter_id: UUID
    run_id: UUID
    bundle_manifest_sha256: SHA256
    decision_snapshot_sha256: SHA256
    artifact_hashes: Mapping[UUID, SHA256]
    documents: tuple[EffectiveDocument, ...]
    signals: tuple[EffectiveTextSignal, ...]
    limitations: tuple[NonEmpty, ...]
    algorithm: Literal['effective-text-v1'] = 'effective-text-v1'
    sha256: SHA256


class EffectiveReviewDimension(DomainModel):
    status: Literal['reviewed', 'pending']
    reason: Annotated[NonEmpty, Field(max_length=2000)]


class EffectiveTextReviewInput(DomainModel):
    bundle_id: UUID
    effective_text_sha256: SHA256
    legal: EffectiveReviewDimension
    amounts: EffectiveReviewDimension
    deadlines: EffectiveReviewDimension
    attachments: EffectiveReviewDimension
    definitions_references: EffectiveReviewDimension


class EffectiveTextReview(EffectiveTextReviewInput):
    id: UUID
    matter_id: UUID
    actor_id: UUID
    reviewed_at: UTCDatetime
    status: Literal['pending', 'reviewed_within_read_scope']
    formal_signoff: Literal[False] = False


class WorkingDraftConfirmationInput(DomainModel):
    bundle_id: UUID
    bundle_manifest_sha256: SHA256
    decision_snapshot_sha256: SHA256
    audience: Audience
    acknowledged_unresolved_finding_ids: Annotated[tuple[UUID, ...], Field(max_length=128)]
    reason: Annotated[NonEmpty, Field(max_length=2000)]
    effective_text_review_id: UUID | None = Field(default=None, exclude_if=lambda value:value is None)

    @field_validator('acknowledged_unresolved_finding_ids')
    @classmethod
    def distinct_unresolved(cls, values):
        if len(set(values)) != len(values):raise ValueError('unresolved findings cannot repeat')
        return values


class WorkingDraftConfirmation(DomainModel):
    id: UUID
    matter_id: UUID
    run_id: UUID
    bundle_id: UUID
    bundle_manifest_sha256: SHA256
    decision_snapshot_sha256: SHA256
    audience: Audience
    artifact_hashes: Mapping[UUID, SHA256]
    acknowledged_unresolved_finding_ids: tuple[UUID, ...]
    reason: Annotated[NonEmpty, Field(max_length=2000)]
    actor_id: UUID
    confirmed_at: UTCDatetime
    purpose: Literal['working_draft'] = 'working_draft'
    formal_signoff: Literal[False] = False
    effective_text_review_id: UUID | None = Field(default=None, exclude_if=lambda value:value is None)
    effective_text_review_status: Literal['pending', 'reviewed_within_read_scope'] | None = Field(default=None, exclude_if=lambda value:value is None)

    @field_validator('artifact_hashes')
    @classmethod
    def readonly_hashes(cls, value):
        return _FrozenDict(value)

    @field_serializer('artifact_hashes')
    def serialize_hashes(self, value):
        return {str(key): digest for key, digest in value.items()}

    @model_validator(mode='after')
    def bounded_confirmation(self):
        if not self.artifact_hashes or len(set(self.acknowledged_unresolved_finding_ids)) != len(self.acknowledged_unresolved_finding_ids):
            raise ValueError('confirmation must bind distinct artifacts and unresolved findings')
        return self


class FindingDecisionInput(DomainModel):
    run_id: UUID
    run_sha256: SHA256
    decision: HumanDecisionKind
    reason: Annotated[NonEmpty, Field(max_length=2000)]
    basis_review: FindingBasisReviewInput | None = Field(default=None, exclude_if=lambda value:value is None)
    edited_analysis: Annotated[NonEmpty, Field(max_length=20000)] | None = None
    edited_recommendation: Annotated[NonEmpty, Field(max_length=20000)] | None = None
    edited_replacement_text: Annotated[str, Field(min_length=1, max_length=20000)] | None = None

    @model_validator(mode='after')
    def explicit_edit(self) -> FindingDecisionInput:
        return _validate_edit_fields(self)


class PatchApproveInput(DomainModel):
    run_id: UUID
    run_sha256: SHA256
    finding_id: UUID
    anchor_id: UUID
    new_text: Annotated[str, Field(min_length=1, max_length=10000)]
    reason: Annotated[NonEmpty, Field(max_length=2000)]
    audiences: Annotated[tuple[Audience, ...], Field(min_length=1, max_length=3)]


class ExportPreviewInput(DomainModel):
    run_id: UUID
    run_sha256: SHA256
    audience: Audience
    patch_ids: Annotated[tuple[UUID, ...], Field(max_length=1000)]


class FormalApprovalInput(DomainModel):
    bundle_id: UUID
    artifact_manifest_hash: SHA256
    review_snapshot_hash: SHA256
    scope: Audience


class PlanApproveInput(DomainModel):
    plan_sha256: SHA256


class PartySelectionInput(DomainModel):
    party_id: UUID
    candidate_id: UUID
    reason: Annotated[NonEmpty, Field(max_length=2000)]


class AcceptanceCase(DomainModel):
    test_id: NonEmpty
    fixture: NonEmpty
    expected: tuple[NonEmpty, ...]
    entrypoint: NonEmpty
    owner: NonEmpty
    status: AcceptanceStatus
    input_scene: NonEmpty | None = None
    source: NonEmpty | None = None
    responsible_tasks: tuple[NonEmpty, ...] = ()
    fixture_id: NonEmpty | None = None
    fixture_sha256: SHA256 | None = None
    limitations: tuple[NonEmpty, ...] = ()


class EvaluationCaseResult(DomainModel):
    test_id: NonEmpty
    status: AcceptanceStatus
    details: tuple[NonEmpty, ...]
    guard_status: AcceptanceStatus = 'NOT_RUN'
    guard_details: tuple[NonEmpty, ...] = ()
    partial_status: AcceptanceStatus = 'NOT_RUN'
    hard_gate: bool = False
    evidence_refs: tuple[NonEmpty, ...] = ()


class ExecutionEvidence(DomainModel):
    command: NonEmpty
    exit_code: int
    executed_at: UTCDatetime
    passed: NonNegativeInt
    failed: NonNegativeInt
    argv: tuple[NonEmpty, ...] = ()
    completed_at: UTCDatetime | None = None
    skipped: NonNegativeInt = 0
    errors: NonNegativeInt = 0
    junit_ref: NonEmpty | None = None
    junit_sha256: SHA256 | None = None
    collection_ref: NonEmpty | None = None
    collection_sha256: SHA256 | None = None
    output_ref: NonEmpty | None = None
    output_sha256: SHA256 | None = None
    source_hashes: dict[NonEmpty, SHA256] = Field(default_factory=dict)
    source_stable: bool = False


class SyntheticAcceptanceSample(DomainModel):
    id: NonEmpty
    path: NonEmpty
    sha256: SHA256
    byte_size: PositiveInt
    family: NonEmpty
    template_ref: NonEmpty
    template_sha256: SHA256
    partition: Literal['development', 'blind']
    contract_type: ContractType
    boundary: bool
    origin: Literal['project_authored_independent_synthetic']
    limitations: tuple[NonEmpty, ...]
    scenario_ids: tuple[NonEmpty, ...]


class AcceptanceGold(DomainModel):
    status: Literal['pending'] = 'pending'
    reviewer_1: UUID | None = None
    reviewer_2: UUID | None = None
    disagreements: Literal['pending'] = 'pending'


class UnmeasuredLegalMetrics(DomainModel):
    major_recall: None = None
    precision: None = None
    anchor_accuracy: None = None
    legal_accuracy: None = None


class SampleEvaluationResult(DomainModel):
    sample_id: NonEmpty
    family: NonEmpty
    partition: Literal['development', 'blind']
    contract_type: ContractType
    fixture_sha256: SHA256
    status: AcceptanceStatus
    parse_status: Literal['NOT_RUN', 'completed', 'failed']
    facts_confirmed: NonNegativeInt = 0
    coverage_count: NonNegativeInt = 0
    unsupported_parts: NonNegativeInt = 0
    model_usage: tuple[ModelUsage, ...] = ()
    attempts: NonNegativeInt = 0
    run_id: UUID | None = None
    error_code: ErrorCode | None = None
    evidence_ref: NonEmpty | None = None
    evidence_sha256: SHA256 | None = None
    limitations: tuple[NonEmpty, ...] = ()


class EvaluationReport(DomainModel):
    mode: EvaluationMode
    results: tuple[EvaluationCaseResult, ...]
    executions: tuple[ExecutionEvidence, ...]
    denominator: PositiveInt
    limitations: tuple[NonEmpty, ...]
    counts: dict[AcceptanceStatus, NonNegativeInt] = Field(default_factory=dict)
    readiness: Literal['GO', 'NO_GO', 'BLOCKED'] = 'BLOCKED'
    gold: AcceptanceGold = Field(default_factory=AcceptanceGold)
    legal_metrics: UnmeasuredLegalMetrics = Field(default_factory=UnmeasuredLegalMetrics)
    real_provider_requests: Literal[0] = 0
    cost: Credits | None = None
    human_review_minutes: ExactDecimal | None = None
    sample_denominator: NonNegativeInt = 0
    samples_reviewed: NonNegativeInt = 0
    sample_results: tuple[SampleEvaluationResult, ...] = ()
    sample_type_counts: dict[ContractType, NonNegativeInt] = Field(default_factory=dict)
    sample_partition_counts: dict[NonEmpty, NonNegativeInt] = Field(default_factory=dict)
    sample_family_counts: dict[NonEmpty, NonNegativeInt] = Field(default_factory=dict)
    registry_sha256: SHA256 | None = None
    fixture_manifest_sha256: SHA256 | None = None
    full_capability_numerator: NonNegativeInt = 0
    guard_numerator: NonNegativeInt = 0
    guard_denominator: NonNegativeInt = 0


class ReleaseConfig(DomainModel):
    source_lock_ref: NonEmpty
    rule_version_refs: tuple[NonEmpty, ...]
    config_ref: NonEmpty
    test_evidence_refs: tuple[NonEmpty, ...]
    deployment_evidence_refs: tuple[NonEmpty, ...]


class ReleaseManifest(DomainModel):
    source_lock_sha256: SHA256
    rules_sha256: SHA256
    config_sha256: SHA256
    test_evidence_sha256: SHA256
    deployment_evidence_sha256: SHA256
    approved_by: UUID | None
    approved_at: UTCDatetime | None
    mode: Literal['development', 'production'] = 'development'
    blockers: tuple[NonEmpty, ...] = ()
    evidence_hashes: dict[NonEmpty, SHA256] = Field(default_factory=dict)
    evidence_currentness: dict[NonEmpty, NonEmpty] = Field(default_factory=dict)
    created_at: UTCDatetime | None = None


class EgressPolicy(DomainModel):
    allowed_endpoints: tuple[NonEmpty, ...]
    allowed_regions: tuple[NonEmpty, ...]
    allowed_data_types: tuple[NonEmpty, ...]


class BackupConfig(DomainModel):
    storage_ref: NonEmpty
    key_ref: NonEmpty
    retention_days: PositiveInt


class WorkspaceBackupFile(DomainModel):
    path: NonEmpty
    size: NonNegativeInt
    sha256: SHA256


class WorkspaceBackupManifest(DomainModel):
    format: Literal['qx-local-workspace-v1']
    archive_id: UUID
    workspace_id: UUID
    created_at: UTCDatetime
    files: tuple[WorkspaceBackupFile, ...]


class BackupReport(DomainModel):
    backup_ref: NonEmpty
    restored_at: UTCDatetime
    ok: bool
    differences: tuple[NonEmpty, ...]
    archive_sha256: SHA256 | None = None
    manifest_sha256: SHA256 | None = None
    restored_root: NonEmpty | None = None
    restored_database_sha256: SHA256 | None = None
    verified_file_count: NonNegativeInt = 0
    source_table_counts: dict[NonEmpty, NonNegativeInt] = Field(default_factory=dict)
    quarantine_ref: UUID | None = None
    limitations: tuple[NonEmpty, ...] = ()


class BackupArchiveHeader(DomainModel):
    version: PositiveInt
    archive_id: UUID
    key_ref: Annotated[str, StringConstraints(pattern=r'^synthetic-[a-z0-9-]{1,100}$')]
    synthetic_only: Annotated[bool, Field(strict=True)]

    @model_validator(mode='after')
    def independent_format(self):
        if self.version != 1 or self.synthetic_only is not True:
            raise ValueError('independent fictional backup format required')
        return self


class BackupFileEvidence(DomainModel):
    logical_ref: NonEmpty
    physical_ref: NonEmpty
    sha256: SHA256
    size: NonNegativeInt
    record_ref: UUID
    kind: Literal['original', 'export', 'patch']
    matter_id: UUID


class BackupTableEvidence(DomainModel):
    count: NonNegativeInt
    sha256: SHA256


class BackupManifestEvidence(DomainModel):
    version: PositiveInt
    archive_id: UUID
    synthetic_only: Annotated[bool, Field(strict=True)]
    created_at: UTCDatetime
    source_database_sha256: SHA256
    schema_sha256: SHA256
    tables: dict[NonEmpty, BackupTableEvidence]
    files: tuple[BackupFileEvidence, ...]
    retention_days: PositiveInt
    latest_external_checkpoint: None
    limitations: tuple[NonEmpty, ...]

    @model_validator(mode='after')
    def independent_format(self):
        if self.version != 1 or self.synthetic_only is not True:
            raise ValueError('independent fictional backup manifest required')
        return self


class SecretFinding(DomainModel):
    path: NonEmpty
    reason: NonEmpty


class SecretScanReport(DomainModel):
    ok: bool
    findings: tuple[SecretFinding, ...]
    checked_files: NonNegativeInt
    scope: NonEmpty = 'explicit candidate bytes only; pattern scan, manual classification pending'


class ReadinessEvidence(DomainModel):
    license_approval_refs: tuple[NonEmpty, ...]
    rule_approval_refs: tuple[NonEmpty, ...]
    interface_billing_refs: tuple[NonEmpty, ...]
    test_evidence_refs: tuple[NonEmpty, ...]
    blind_evaluation_refs: tuple[NonEmpty, ...]
    shadow_run_refs: tuple[NonEmpty, ...]


class ReadinessDecision(DomainModel):
    decision: ReadinessStatus
    reasons: dict[NonEmpty, NonEmpty]
    evidence: ReadinessEvidence | None
    scope: Literal['restricted_engineering'] = 'restricted_engineering'
    real_evidence_trust: Literal['NOT_IMPLEMENTED'] = 'NOT_IMPLEMENTED'
    evidence_hashes: dict[NonEmpty, SHA256] = Field(default_factory=dict)
    evidence_currentness: dict[NonEmpty, NonEmpty] = Field(default_factory=dict)
    server_gate_counts: dict[NonEmpty, NonNegativeInt] = Field(default_factory=dict)
    real_provider_requests: Literal[0] = 0
    assessed_at: UTCDatetime | None = None

    @model_validator(mode='after')
    def go_needs_evidence(self) -> ReadinessDecision:
        if self.decision == ReadinessStatus.GO:
            if self.evidence is None or any(not getattr(self.evidence, name) for name in ReadinessEvidence.model_fields):
                raise ValueError('GO requires every category of readiness evidence')
            raise ValueError('REAL_READINESS_TRUST_NOT_IMPLEMENTED')
        return self


# Public-library snapshots are separate from approved legal authorities and cases.
class LibrarySource(DomainModel):
    source_id: SHA256
    batch_id: Annotated[str, StringConstraints(pattern=r'^[A-Za-z0-9_.-]{1,80}$')]
    sha256: SHA256
    size: NonNegativeInt
    asset_key: Annotated[str, StringConstraints(pattern=r'^[a-f0-9]{64}/original$')]
    kind: Literal['case_csv', 'law_markdown']
    aliases: tuple[NonEmpty, ...]
    registered_at: UTCDatetime


class LibraryReviewEvent(DomainModel):
    subject_id: SHA256
    version_id: SHA256
    operator: NonEmpty
    recorded_at: UTCDatetime
    field: Literal['text_integrity', 'source_provenance', 'version_relation']
    value: Literal['needs_review', 'text_checked', 'source_candidate']
    reason: NonEmpty


class LibraryRecord(DomainModel):
    record_id: SHA256
    source_id: SHA256
    kind: Literal['case_csv', 'law_markdown']
    ordinal: PositiveInt
    byte_start: NonNegativeInt
    byte_end: NonNegativeInt
    raw_sha256: SHA256
    body_sha256: SHA256 | None
    version_id: SHA256
    fields: dict[str, str | None]
    warnings: tuple[str, ...] = ()
    body_status: Literal['body_present_unverified', 'catalog_only', 'damaged_record']
    cleaning_version: Literal['qx-clean-v1'] = 'qx-clean-v1'
    verification_status: Literal['unverified'] = 'unverified'

    @model_validator(mode='after')
    def valid_library_range(self):
        if self.byte_end < self.byte_start or self.byte_end - self.byte_start > 32 * 1024 * 1024:
            raise ValueError('LIBRARY_RECORD_RANGE_INVALID')
        return self


class LibraryFragment(DomainModel):
    fragment_id: SHA256
    record_id: SHA256
    version_id: SHA256
    ordinal: PositiveInt
    start: NonNegativeInt
    end: NonNegativeInt
    line_start: PositiveInt
    line_end: PositiveInt
    text_sha256: SHA256
    role: Literal['paragraph', 'article_candidate', 'contents_candidate', 'quoted_candidate']
    article: str | None
    ambiguous: StrictBool = False

    @model_validator(mode='after')
    def valid_fragment_range(self):
        if self.end < self.start or self.line_end < self.line_start:
            raise ValueError('FRAGMENT_RANGE_INVALID')
        return self


class LibraryQuery(DomainModel):
    text: Annotated[str, StringConstraints(max_length=200)] = ''
    kind: Literal['all', 'case_csv', 'law_markdown'] = 'all'
    mode: Literal['phrase', 'all'] = 'all'
    case_no: str | None = None
    court: str | None = None
    cause: str | None = None
    document_type: str | None = None
    province: str | None = None
    date_from: date | None = None
    date_to: date | None = None
    limit: Annotated[int, Field(strict=True, ge=1, le=100)] = 20
    cursor: Annotated[str, StringConstraints(max_length=2048)] | None = None

    @model_validator(mode='after')
    def library_filters(self):
        if (self.date_from or self.date_to) and self.kind != 'case_csv':
            raise ValueError('DATE_FILTER_CASES_ONLY')
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValueError('DATE_RANGE_INVALID')
        return self


class LibraryHit(DomainModel):
    record_id: SHA256
    version_id: SHA256
    fragment_id: SHA256 | None
    kind: Literal['case_csv', 'law_markdown']
    title: str
    snippet: str
    match_start: NonNegativeInt | None
    match_end: NonNegativeInt | None
    match_field: Literal['body', 'title', 'metadata']
    score: float
    fields: dict[str, str | None]
    verification_status: Literal['unverified'] = 'unverified'
    body_status: str
    article: str | None = None
    ambiguous: StrictBool = False
    fragment_role: Literal['paragraph', 'article_candidate', 'contents_candidate', 'quoted_candidate'] | None = None


class LibraryPage(DomainModel):
    hits: tuple[LibraryHit, ...] = ()
    generation_id: str | None = None
    coverage: dict[str, NonNegativeInt] = Field(default_factory=dict)
    state: Literal['ready', 'timeout', 'not_ready']
    next_cursor: str | None = None
    total_matches: NonNegativeInt | None = None


class LibraryOriginal(DomainModel):
    record: LibraryRecord
    source: LibrarySource
    text: str
    raw_fields: dict[str, JsonValue]
    fragment: LibraryFragment | None = None


# Conversation input is source material, never a confirmed fact or issued opinion.
AssistantSkill = Literal['client_reply', 'material_organize', 'contract_review',
                         'content_draft', 'legal_research']
AssistantRunState = Literal['queued', 'preparing', 'routing', 'retrieving', 'generating',
                            'persisting', 'completed', 'cancelled', 'failed',
                            'interrupted', 'awaiting_input', 'blocked']
AssistantText = Annotated[str, StringConstraints(strict=True, max_length=20000), AfterValidator(_intake_text)]


class AssistantScope(DomainModel):
    scope_kind: Literal['conversation', 'intake', 'matter'] = 'conversation'
    scope_ref: UUID | None = None

    @model_validator(mode='after')
    def explicit_scope_reference(self):
        if (self.scope_kind == 'conversation') != (self.scope_ref is None):
            raise ValueError('conversation has no reference; intake and matter require one')
        return self


class ScopeSnapshot(AssistantScope):
    workspace_id: UUID
    conversation_id: UUID
    binding_revision: PositiveInt
    input_revision: NonNegativeInt
    materials_revision: NonNegativeInt


class AssistantConversationCreateInput(AssistantScope):
    request_id: UUID
    display_title: IntakeLabel = '新对话'


class AssistantDraftInput(DomainModel):
    expected_scope: ScopeSnapshot
    expected_composer_revision: NonNegativeInt
    content: AssistantText


class AssistantMessageInput(AssistantDraftInput):
    request_id: UUID
    requested_skill: AssistantSkill | None = None
    attachment_ids: Annotated[tuple[UUID, ...], Field(max_length=20)] = ()

    @field_validator('content')
    @classmethod
    def nonblank_message(cls, value):
        if not value.strip():
            raise ValueError('message text required')
        return value


class AssistantMessageView(DomainModel):
    id: UUID
    role: Literal['user', 'assistant']
    content: AssistantText
    source_revision: PositiveInt
    created_at: UTCDatetime


class AssistantConversationView(DomainModel):
    scope: ScopeSnapshot
    display_title: IntakeLabel
    composer_revision: NonNegativeInt
    draft_input: AssistantText
    projection_intake_id: UUID | None
    created_at: UTCDatetime
    archived_at: UTCDatetime | None
    messages: tuple[AssistantMessageView, ...]


class AssistantMessagePageQuery(DomainModel):
    before: UUID | None = None
    limit: Annotated[int, Field(strict=True, ge=1, le=50)] = 50


class AssistantRunSummary(DomainModel):
    id: UUID
    message_id: UUID
    request_id: UUID
    request_sha256: SHA256
    scope: ScopeSnapshot
    state: AssistantRunState
    requested_skill: AssistantSkill | None
    cancel_requested: StrictBool
    created_at: UTCDatetime
    last_event_seq: NonNegativeInt


class AssistantConversationPageView(AssistantConversationView):
    messages: Annotated[tuple[AssistantMessageView, ...], Field(max_length=50)]
    next_before: UUID | None
    latest_run: AssistantRunSummary | None


class AssistantConversationSummary(DomainModel):
    scope: ScopeSnapshot
    display_title: IntakeLabel
    composer_revision: NonNegativeInt
    created_at: UTCDatetime
    archived_at: UTCDatetime | None


class AssistantConversationQuery(DomainModel):
    cursor: UUID | None = None
    limit: Annotated[int, Field(strict=True, ge=1, le=50)] = 20


class AssistantConversationPage(DomainModel):
    items: tuple[AssistantConversationSummary, ...]
    next_cursor: UUID | None


class AssistantCancelInput(DomainModel):
    request_id: UUID


class AssistantEventQuery(DomainModel):
    after_seq: NonNegativeInt = 0
    limit: Annotated[int, Field(strict=True, ge=1, le=100)] = 100


class AssistantRunEvent(DomainModel):
    seq: PositiveInt
    event_type: NonEmpty
    audience: Literal['internal', 'client']
    payload: dict[str, JsonValue]
    created_at: UTCDatetime


class AssistantEventPage(DomainModel):
    run_id: UUID
    conversation_id: UUID
    state: AssistantRunState
    events: tuple[AssistantRunEvent, ...]
    next_after_seq: NonNegativeInt
    has_more: StrictBool


class AssistantRunView(DomainModel):
    id: UUID
    message_id: UUID
    request_id: UUID
    request_sha256: SHA256
    scope: ScopeSnapshot
    state: AssistantRunState
    requested_skill: AssistantSkill | None
    selected_provider: str | None
    selected_model: str | None
    cancel_requested: StrictBool
    created_at: UTCDatetime
    events: tuple[AssistantRunEvent, ...]


class AssistantSkillView(DomainModel):
    id: AssistantSkill
    label: NonEmpty
    state: Literal['not_connected', 'local_only'] = 'not_connected'
    reason: NonEmpty


class AssistantSkillCatalog(DomainModel):
    items: tuple[AssistantSkillView, ...]
    generation_enabled: Literal[False] = False


class DocumentParseInput(DomainModel):
    """Pure parser identity, without pretending an unattached file has a case."""
    id: UUID
    baseline_view: BaselineView


class AssistantMaterialPolicy(DomainModel):
    policy_id: Literal['assistant-local-docx-v1', 'assistant-local-files-v2'] = 'assistant-local-docx-v1'
    material_mode: Literal['synthetic', 'local'] = 'synthetic'
    local_processing_accepted: Literal[True]
    external_processing: Literal[False] = False


ASSISTANT_MATERIAL_MIME_EXT = {
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document': ('.docx',),
    'application/msword': ('.doc',),
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': ('.xlsx',),
    'application/pdf': ('.pdf',),
    'image/png': ('.png',),
    'image/jpeg': ('.jpg', '.jpeg'),
    'text/csv': ('.csv',),
}


class AssistantAttachmentInput(DomainModel):
    request_id: UUID
    expected_scope: ScopeSnapshot
    original_name: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=240)]
    mime: Literal[
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'application/msword',
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        'application/pdf',
        'image/png',
        'image/jpeg',
        'text/csv',
    ]
    policy: AssistantMaterialPolicy

    @field_validator('original_name')
    @classmethod
    def filename_only(cls, value):
        if value != value.strip() or any(ord(c) < 32 or c in '/\\:< >"|?*'.replace(' ', '') for c in value):
            raise ValueError('a plain filename is required')
        if value.rstrip('.') != value:
            raise ValueError('a plain filename is required')
        return value

    @model_validator(mode='after')
    def extension_matches_mime(self):
        from pathlib import PurePath
        if PurePath(self.original_name).suffix.lower() not in ASSISTANT_MATERIAL_MIME_EXT[self.mime]:
            raise ValueError('filename extension does not match the declared type')
        return self


class AssistantMaterialRef(DomainModel):
    attachment_id: UUID
    parse_revision: PositiveInt | None


class AssistantMaterialSelectionInput(DomainModel):
    request_id: UUID
    expected_scope: ScopeSnapshot
    items: Annotated[tuple[AssistantMaterialRef, ...], Field(max_length=20)]

    @field_validator('items')
    @classmethod
    def distinct_attachments(cls, values):
        if len({value.attachment_id for value in values}) != len(values):
            raise ValueError('duplicate attachment selection')
        return values


class AssistantAttachmentParseInput(DomainModel):
    request_id: UUID
    expected_scope: ScopeSnapshot
    baseline_view: BaselineView | None = None


class AssistantAttachmentView(DomainModel):
    id: UUID
    conversation_id: UUID
    request_id: UUID
    original_name: NonEmpty
    mime: NonEmpty
    byte_size: PositiveInt
    sha256: SHA256
    policy: AssistantMaterialPolicy
    created_at: UTCDatetime
    review_status: Literal['unverified'] = 'unverified'


class AssistantAttachmentReceipt(DomainModel):
    attachment: AssistantAttachmentView
    materials_revision: PositiveInt


class AssistantMaterialReceipt(DomainModel):
    request_id: UUID
    kind: Literal['upload', 'parse', 'selection']
    materials_revision: PositiveInt
    items: tuple[AssistantMaterialRef, ...]


class AssistantAttachmentParseView(DomainModel):
    attachment_id: UUID
    conversation_id: UUID
    revision: PositiveInt
    request_id: UUID
    parser_version: NonEmpty
    baseline_view: BaselineView | None
    reading_status: Literal['readable', 'partial', 'needs_baseline', 'failed']
    result: ParseResult | None
    result_sha256: SHA256 | None
    failure_code: NonEmpty | None
    created_at: UTCDatetime
    review_status: Literal['unverified'] = 'unverified'


class AssistantAttachmentParseReceipt(DomainModel):
    parse: AssistantAttachmentParseView
    materials_revision: PositiveInt


class AssistantMaterialsView(DomainModel):
    scope: ScopeSnapshot
    items: tuple[AssistantMaterialRef, ...]
    attachments: tuple[AssistantAttachmentView, ...]


class AssistantAttachmentExcerpt(DomainModel):
    conversation_id: UUID
    attachment_id: UUID
    parse_revision: PositiveInt
    original_sha256: SHA256
    anchor: Anchor
    review_status: Literal['unverified'] = 'unverified'


MainUSD = Annotated[ExactDecimal, Field(ge=0, le=1000000000, max_digits=24, decimal_places=12)]
MainRate = Annotated[ExactDecimal, Field(gt=0, le=10000, max_digits=12, decimal_places=6)]
MainAttemptState = Literal['reserved', 'sending', 'sent_unknown', 'received', 'failed_before_send']
MainTokenCount = Annotated[int, Field(strict=True, ge=0, le=2147483647)]


class MainModelConfig(DomainModel):
    enabled: StrictBool = False
    protocol_version: Literal['deepseek-chat-json-v1'] = 'deepseek-chat-json-v1'
    provider: Literal['deepseek'] = 'deepseek'
    model: Literal['deepseek-flash', 'deepseek-v4-pro']
    max_input_bytes: Annotated[int, Field(strict=True, ge=1, le=262144)] = 65536
    max_output_tokens: Annotated[int, Field(strict=True, ge=1, le=8192)] = 4096
    max_response_bytes: Annotated[int, Field(strict=True, ge=1, le=1048576)] = 1048576
    timeout_seconds: Annotated[int, Field(strict=True, ge=1, le=120)] = 30
    input_usd_per_million: MainRate
    output_usd_per_million: MainRate
    price_reference: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=256)]


class MainSendApproval(DomainModel):
    request_id: UUID
    expected_scope: ScopeSnapshot
    expected_composer_revision: NonNegativeInt
    content_sha256: SHA256


class NativeModelConfigure(DomainModel):
    config: MainModelConfig
    secret: Annotated[str, StringConstraints(strict=True, min_length=16, max_length=512,
        pattern=r'^[!-~]+$')] = Field(repr=False)


class NativeModelAuthorization(DomainModel):
    session_token: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=256)] = Field(repr=False)
    expected_config_version: UUID
    basis: MainSendApproval
    max_total_usd: Annotated[MainUSD, Field(gt=0, le=1000000)]
    valid_for_seconds: Annotated[int, Field(strict=True, ge=1, le=900)]


class NativeModelRevoke(DomainModel):
    session_token: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=256)] = Field(repr=False)


class MainRequest(DomainModel):
    run_id: UUID
    scope: ScopeSnapshot
    message_id: UUID
    content: AssistantText
    source_sha256: SHA256

    @model_validator(mode='after')
    def exact_message(self):
        if not self.content.strip() or hashlib.sha256(self.content.encode('utf-8')).hexdigest() != self.source_sha256:
            raise ValueError('nonempty source message with matching digest required')
        return self


class MainPreparedInput(DomainModel):
    request: MainRequest
    wire_payload_json: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=262144)]


class MainCitation(DomainModel):
    message_id: UUID
    quote_sha256: SHA256


class MainCandidate(DomainModel):
    text: AssistantText
    citations: Annotated[tuple[MainCitation, ...], Field(max_length=1)] = ()

    @field_validator('text')
    @classmethod
    def nonempty_candidate(cls, value):
        if not value.strip():
            raise ValueError('empty model candidate')
        return value


class MainUsage(DomainModel):
    prompt_tokens: MainTokenCount
    completion_tokens: MainTokenCount
    total_tokens: MainTokenCount
    prompt_cache_hit_tokens: MainTokenCount | None = None
    prompt_cache_miss_tokens: MainTokenCount | None = None

    @model_validator(mode='after')
    def consistent_counts(self):
        if self.total_tokens != self.prompt_tokens + self.completion_tokens:
            raise ValueError('token total mismatch')
        cache = (self.prompt_cache_hit_tokens, self.prompt_cache_miss_tokens)
        if any(value is not None and value > self.prompt_tokens for value in cache):
            raise ValueError('cache tokens exceed input')
        if all(value is not None for value in cache) and sum(cache) != self.prompt_tokens:
            raise ValueError('cache token total mismatch')
        return self


class MainReply(DomainModel):
    state: Literal['received', 'sent_unknown', 'failed_before_send']
    provider_request_id: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=256)] | None = None
    usage: MainUsage | None = None
    output: MainCandidate | None = None
    error_code: Literal['BLOCKED_LIVE', 'PROVIDER_ERROR', 'MODEL_OUTPUT_INVALID'] | None = None

    @model_validator(mode='after')
    def consistent_reply(self):
        if self.output is not None and (self.state != 'received' or self.error_code is not None):
            raise ValueError('output requires a received validated response')
        if self.output is None and self.error_code is None:
            raise ValueError('failed response needs a fixed error code')
        if self.state != 'received' and (self.usage is not None or self.provider_request_id is not None):
            raise ValueError('unknown/unsent response cannot claim received usage')
        return self


class MainModelPolicy(DomainModel):
    policy_id: UUID
    workspace_id: UUID
    actor_id: UUID
    config_sha256: SHA256
    allowed_content_sha256s: Annotated[tuple[SHA256, ...], Field(min_length=1, max_length=256)]
    max_total_usd: Annotated[MainUSD, Field(gt=0, le=1000000)]
    max_calls: Annotated[int, Field(strict=True, ge=1, le=1000)]
    expires_at: UTCDatetime

    @field_validator('allowed_content_sha256s')
    @classmethod
    def unique_allowed_content(cls, value):
        if len(value) != len(set(value)):
            raise ValueError('duplicate allowed source')
        return value


class MainReceipt(DomainModel):
    state: Literal['received', 'sent_unknown', 'failed_before_send']
    provider_request_id: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=256)] | None
    usage: MainUsage | None
    cost_status: Literal['unknown', 'estimated', 'not_sent']
    estimated_cost_usd: MainUSD | None
    unit: Literal['USD'] = 'USD'
    error_code: Literal['BLOCKED_LIVE', 'PROVIDER_ERROR', 'MODEL_OUTPUT_INVALID'] | None

    @model_validator(mode='after')
    def no_false_zero_cost(self):
        if self.cost_status == 'unknown' and self.estimated_cost_usd is not None:
            raise ValueError('unknown usage has unknown cost')
        if self.cost_status == 'estimated' and (self.state != 'received' or self.usage is None or self.estimated_cost_usd is None):
            raise ValueError('estimated cost requires received usage')
        if self.cost_status == 'not_sent' and (self.state != 'failed_before_send' or self.estimated_cost_usd != Decimal(0)):
            raise ValueError('zero unsent cost needs proof before sending')
        if self.state != 'received' and (self.usage is not None or self.provider_request_id is not None):
            raise ValueError('no fabricated usage or response identity')
        return self


class MainOutputView(DomainModel):
    id: UUID
    run_id: UUID
    scope: ScopeSnapshot
    audience: Literal['internal'] = 'internal'
    generation_kind: Literal['model_generated'] = 'model_generated'
    review_status: Literal['unverified'] = 'unverified'
    candidate: MainCandidate
    created_at: UTCDatetime


class MainAttemptView(DomainModel):
    id: UUID
    run_id: UUID
    scope: ScopeSnapshot
    state: MainAttemptState
    reserved_usd: MainUSD
    unit: Literal['USD'] = 'USD'
    receipt: MainReceipt | None
    output: MainOutputView | None


class MainGenerationHistoryQuery(DomainModel):
    message_ids: Annotated[tuple[UUID, ...], Field(min_length=1, max_length=50)]

    @field_validator('message_ids')
    @classmethod
    def unique_messages(cls, value):
        if len(value) != len(set(value)):
            raise ValueError('duplicate history message')
        return value


class MainGenerationCapability(DomainModel):
    scope: ScopeSnapshot
    composer_revision: Annotated[int, Field(strict=True, ge=0)]
    basis: Literal['saved_draft'] = 'saved_draft'
    content_sha256: SHA256 | None
    state: Literal['unconfigured', 'unapproved', 'empty', 'unsupported', 'busy',
                   'budget_exhausted', 'restored_read_only', 'ready']


JudgePurpose = Literal['primary_intent', 'material_kind', 'possible_result_guarantee']
JudgeMaterialKind = Literal['contract', 'chat', 'transfer', 'judgment', 'mixed', 'unknown']
JudgeSkipReason = Literal['unconfigured', 'no_budget', 'no_egress', 'explicit_skill', 'not_needed', 'stale_scope']
JudgeProbability = Annotated[float, Field(strict=True, ge=0, le=1, allow_inf_nan=False)]
JudgeLabel = Annotated[str, StringConstraints(strict=True, min_length=1, max_length=64, pattern=r'^[a-z_]+$')]


class JevConfig(DomainModel):
    enabled: StrictBool = False
    protocol_version: Literal['typesafe-systemone-v1'] = 'typesafe-systemone-v1'
    model: Literal['jev-1.13.0'] = 'jev-1.13.0'
    max_input_bytes: Annotated[int, Field(strict=True, ge=1, le=65536)] = 65536
    max_response_bytes: Annotated[int, Field(strict=True, ge=1, le=262144)] = 262144
    timeout_ms: Annotated[int, Field(strict=True, ge=1, le=2000)] = 2000


class NativeJudgeConfigure(DomainModel):
    config: JevConfig
    secret: Annotated[str, StringConstraints(strict=True, min_length=16, max_length=512,
        pattern=r'^[!-~]+$')] = Field(repr=False)


class JudgeRequest(DomainModel):
    local_request_id: UUID
    scope: ScopeSnapshot
    purpose: JudgePurpose
    text: Annotated[str, StringConstraints(strict=True, max_length=32768)]
    explicit_skill: Annotated[str, StringConstraints(strict=True, max_length=80)] | None = None


class JudgeChoice(DomainModel):
    type: Literal['choice'] = 'choice'
    choice: JudgeLabel
    probabilities: Annotated[dict[JudgeLabel, JudgeProbability], Field(min_length=1, max_length=16)]
    confidence: JudgeProbability

    @model_validator(mode='after')
    def valid_distribution(self):
        if (self.choice not in self.probabilities or abs(sum(self.probabilities.values()) - 1) > 1e-6
                or self.probabilities[self.choice] != max(self.probabilities.values())):
            raise ValueError('invalid choice distribution')
        return self


class JudgeNoul(DomainModel):
    type: Literal['noul'] = 'noul'
    noul: JudgeProbability


class JudgeUsage(DomainModel):
    input_tokens: MainTokenCount | None = None
    output_tokens: MainTokenCount | None = None


class JudgeResult(DomainModel):
    status: Literal['ok', 'skipped', 'timed_out', 'failed', 'invalid']
    reason_code: Union[JudgeSkipReason, Literal['timeout', 'provider_error', 'invalid_response',
        'invalid_request', 'config_changed']] | None = None
    evidence: Literal['not_sent', 'sent_unknown', 'received']
    local_request_id: UUID
    input_hash: SHA256
    scope: ScopeSnapshot
    elapsed_ms: NonNegativeInt
    model: Literal['jev-1.13.0'] | None = None
    answers: Annotated[dict[JudgePurpose, Annotated[Union[JudgeChoice, JudgeNoul],
        Field(discriminator='type')]], Field(max_length=3)] = Field(default_factory=dict)
    provider_request_id: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=256)] | None = None
    usage: JudgeUsage | None = None

    @model_validator(mode='after')
    def result_evidence(self):
        if self.status == 'ok':
            if (self.reason_code is not None or self.evidence != 'received' or not self.answers
                    or self.model is None or self.elapsed_ms >= 2000):
                raise ValueError('usable judge result needs received validated answers')
            for purpose, answer in self.answers.items():
                if purpose == 'possible_result_guarantee':
                    if type(answer) is not JudgeNoul:
                        raise ValueError('fixed question answer type mismatch')
                else:
                    options = (set(get_args(AssistantSkill)) | {'unknown'} if purpose == 'primary_intent'
                               else set(get_args(JudgeMaterialKind)))
                    if type(answer) is not JudgeChoice or set(answer.probabilities) != options:
                        raise ValueError('fixed question options mismatch')
        elif self.answers or self.reason_code is None:
            raise ValueError('unusable judge result must not carry answers')
        if self.status == 'skipped' and (self.evidence != 'not_sent' or self.reason_code not in
                ('unconfigured', 'no_budget', 'no_egress', 'explicit_skill', 'not_needed', 'stale_scope')):
            raise ValueError('skipped judge cannot claim a request')
        if self.evidence != 'received' and (self.usage is not None or self.provider_request_id is not None
                                           or self.model is not None):
            raise ValueError('unknown or unsent judge cannot claim received metadata')
        return self


class RouteDecision(DomainModel):
    workflow: AssistantSkill | None
    source: Literal['explicit', 'jev', 'current']
    reason_code: Literal['explicit_skill', 'explicit_unavailable', 'jev_suggestion',
                         'no_suggestion', 'unavailable_suggestion']

    @model_validator(mode='after')
    def selection_source(self):
        if self.workflow is None:
            if self.source != 'current' or self.reason_code not in (
                    'explicit_unavailable', 'no_suggestion', 'unavailable_suggestion'):
                raise ValueError('no selected workflow must preserve current flow')
        elif (self.source, self.reason_code) not in (('explicit', 'explicit_skill'), ('jev', 'jev_suggestion')):
            raise ValueError('selected workflow needs explicit or judge source')
        return self


# Jev authorization is independent of the main model and never grants a workflow.
JudgeUSD = Annotated[ExactDecimal, Field(ge=0, le=1000000, max_digits=24, decimal_places=12)]


class JudgeSendApproval(DomainModel):
    request_id: UUID
    expected_scope: ScopeSnapshot
    expected_composer_revision: Annotated[int, Field(strict=True, ge=0)]
    content_sha256: SHA256
    purpose: Literal['primary_intent'] = 'primary_intent'


class NativeJudgeAuthorization(DomainModel):
    session_token: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=256)] = Field(repr=False)
    expected_config_version: UUID
    basis: JudgeSendApproval
    max_total_usd: Annotated[JudgeUSD, Field(gt=0)]
    valid_for_seconds: Annotated[int, Field(strict=True, ge=1, le=900)]


class NativeJudgeRevoke(DomainModel):
    session_token: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=256)] = Field(repr=False)


class JudgePermission(DomainModel):
    local_request_id: UUID
    purpose: JudgePurpose
    input_hash: SHA256


class JudgePolicy(DomainModel):
    policy_id: UUID
    workspace_id: UUID
    actor_id: UUID
    session_id: UUID
    recipient: Literal['https://api.typesafe.ai/v1/systemone'] = 'https://api.typesafe.ai/v1/systemone'
    config_sha256: SHA256
    permissions: Annotated[tuple[JudgePermission, ...], Field(min_length=1, max_length=100)]
    reserved_usd: Annotated[JudgeUSD, Field(gt=0)]
    max_total_usd: Annotated[JudgeUSD, Field(gt=0)]
    max_calls: Annotated[int, Field(strict=True, ge=1, le=100)]
    expires_at: UTCDatetime

    @model_validator(mode='after')
    def bounded_judge_policy(self):
        keys = {(p.local_request_id, p.purpose) for p in self.permissions}
        if len(keys) != len(self.permissions) or self.reserved_usd > self.max_total_usd:
            raise ValueError('invalid judge policy envelope')
        return self


class JudgeReceipt(DomainModel):
    result: JudgeResult
    cost_status: Literal['not_sent', 'unknown']
    occupied_usd: JudgeUSD
    unit: Literal['USD'] = 'USD'

    @model_validator(mode='after')
    def conservative_judge_cost(self):
        unsent = self.result.evidence == 'not_sent'
        if ((self.cost_status == 'not_sent') != unsent or
                (self.occupied_usd == 0) != unsent):
            raise ValueError('judge reservation cannot imply a settled vendor price')
        return self


class JudgeDecisionView(DomainModel):
    attempt_id: UUID
    run_id: UUID
    scope: ScopeSnapshot
    decision: RouteDecision
    audience: Literal['internal'] = 'internal'
    review_status: Literal['unverified'] = 'unverified'
    created_at: UTCDatetime


class JudgeAttemptView(DomainModel):
    id: UUID
    run_id: UUID
    message_id: UUID
    purpose: JudgePurpose
    scope: ScopeSnapshot
    state: Literal['reserved', 'sending', 'not_sent', 'sent_unknown', 'received']
    reserved_usd: JudgeUSD
    unit: Literal['USD'] = 'USD'
    receipt: JudgeReceipt | None = None
    decision: JudgeDecisionView | None = None


# Excerpts check their record/quote bytes, never legal support or applicability.
# registered_source_sha256 is the import identity, not a fresh whole-CSV checksum.
LibraryGeneration = Annotated[str, StringConstraints(strict=True, pattern=r'^[a-f0-9]{32}$')]
LibraryHash = Annotated[str, StringConstraints(strict=True, pattern=r'^[a-f0-9]{64}$')]
LibraryFilterText = Annotated[str, StringConstraints(strict=True, max_length=200)]


class AssistantLibraryQuery(LibraryQuery):
    text: LibraryFilterText = ''
    case_no: LibraryFilterText | None = None
    court: LibraryFilterText | None = None
    cause: LibraryFilterText | None = None
    document_type: LibraryFilterText | None = None
    province: LibraryFilterText | None = None
    limit: Annotated[int, Field(strict=True, ge=1, le=8)] = 5
    cursor: Annotated[str, StringConstraints(strict=True, max_length=2048)] | None = None


class CitationRef(DomainModel):
    citation_id: LibraryHash
    generation_id: LibraryGeneration
    record_id: LibraryHash
    version_id: LibraryHash
    source_id: LibraryHash
    registered_source_sha256: LibraryHash
    raw_sha256: LibraryHash
    body_sha256: LibraryHash
    kind: Literal['case_csv', 'law_markdown']
    title: Annotated[str, StringConstraints(strict=True, max_length=2000)]
    metadata: dict[str, Annotated[str, StringConstraints(strict=True, max_length=2000)] | None]
    fragment_id: LibraryHash | None
    fragment_role: Literal['paragraph', 'article_candidate', 'contents_candidate', 'quoted_candidate'] | None
    article: Annotated[str, StringConstraints(strict=True, max_length=200)] | None
    ambiguous: StrictBool
    start: NonNegativeInt
    end: PositiveInt
    line_start: PositiveInt
    line_end: PositiveInt
    quote: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=1200)]
    quote_sha256: LibraryHash
    match_field: Literal['body', 'title', 'metadata']
    match_start: NonNegativeInt | None
    match_end: PositiveInt | None
    match_in_quote: StrictBool
    source_match: Literal['record_quote_matched'] = 'record_quote_matched'
    support_status: Literal['unverified'] = 'unverified'
    applicability_status: Literal['unverified'] = 'unverified'

    @model_validator(mode='after')
    def exact_bounded_citation(self):
        if (self.end - self.start != len(self.quote) or self.line_end < self.line_start or
                hashlib.sha256(self.quote.encode('utf-8')).hexdigest() != self.quote_sha256):
            raise ValueError('CITATION_RANGE_OR_HASH_INVALID')
        body = self.match_field == 'body'
        if body != (self.match_start is not None and self.match_end is not None):
            raise ValueError('CITATION_MATCH_INVALID')
        if not body and (self.match_start is not None or self.match_end is not None):
            raise ValueError('CITATION_MATCH_INVALID')
        if body and self.match_end <= self.match_start:
            raise ValueError('CITATION_MATCH_INVALID')
        if self.match_in_quote != bool(body and self.start <= self.match_start < self.match_end <= self.end):
            raise ValueError('CITATION_MATCH_INVALID')
        if (self.fragment_id is None) != (self.fragment_role is None):
            raise ValueError('CITATION_FRAGMENT_INVALID')
        if self.fragment_id is None and (self.article is not None or self.ambiguous):
            raise ValueError('CITATION_FRAGMENT_INVALID')
        allowed = {'case_no', 'court', 'cause', 'province', 'decision_date', 'publication_date',
                   'filing_date', 'filename_date_candidate', 'region_candidate', 'legal_status'}
        if not set(self.metadata) <= allowed:
            raise ValueError('CITATION_METADATA_INVALID')
        return self


class LibraryCitationPage(DomainModel):
    query: AssistantLibraryQuery
    state: Literal['ready', 'timeout', 'not_ready', 'not_configured']
    generation_id: LibraryGeneration | None = None
    citations: Annotated[tuple[CitationRef, ...], Field(max_length=8)] = ()
    coverage: dict[str, NonNegativeInt] = Field(default_factory=dict)
    next_cursor: Annotated[str, StringConstraints(strict=True, max_length=2048)] | None = None
    omitted_hits: NonNegativeInt = 0

    @model_validator(mode='after')
    def consistent_citation_page(self):
        available = self.state in ('ready', 'timeout')
        if available != (self.generation_id is not None):
            raise ValueError('CITATION_PAGE_GENERATION_INVALID')
        if len(self.citations) + self.omitted_hits > self.query.limit:
            raise ValueError('CITATION_PAGE_LIMIT_INVALID')
        if any(item.generation_id != self.generation_id for item in self.citations):
            raise ValueError('CITATION_PAGE_GENERATION_INVALID')
        if not available and (self.citations or self.coverage or self.next_cursor or self.omitted_hits):
            raise ValueError('CITATION_PAGE_UNAVAILABLE_INVALID')
        return self


AssistantLibraryTool = Literal['legal_library.search', 'legal_library.read_original']


class AssistantLibraryToolCall(DomainModel):
    tool: AssistantLibraryTool
    expected_scope: ScopeSnapshot
    expected_composer_revision: NonNegativeInt
    query: AssistantLibraryQuery | None = None
    citation: CitationRef | None = None

    @model_validator(mode='after')
    def exact_library_tool_input(self):
        search = self.tool == 'legal_library.search'
        if search != (self.query is not None) or search == (self.citation is not None):
            raise ValueError('LIBRARY_TOOL_INPUT_INVALID')
        return self


class AssistantLibraryToolResult(DomainModel):
    tool: AssistantLibraryTool
    scope: ScopeSnapshot
    page: LibraryCitationPage | None = None
    citation: CitationRef | None = None

    @model_validator(mode='after')
    def exact_library_tool_result(self):
        search = self.tool == 'legal_library.search'
        if search != (self.page is not None) or search == (self.citation is not None):
            raise ValueError('LIBRARY_TOOL_RESULT_INVALID')
        return self


class LibraryHandlerRequest(DomainModel):
    tool: AssistantLibraryTool
    query: AssistantLibraryQuery | None = None
    saved_citation_id: UUID | None = None

    @model_validator(mode='after')
    def server_owned_library_reference(self):
        search = self.tool == 'legal_library.search'
        if search != (self.query is not None) or search == (self.saved_citation_id is not None):
            raise ValueError('LIBRARY_TOOL_INPUT_INVALID')
        return self


class LibraryHandlerEvent(DomainModel):
    call_id: UUID
    handler_id: AssistantLibraryTool
    handler_version: Literal['1'] = '1'
    request: LibraryHandlerRequest
    scope: ScopeSnapshot
    expected_composer_revision: NonNegativeInt
    citation_sha256: SHA256 | None = None

    @model_validator(mode='after')
    def exact_library_handler_event(self):
        if self.handler_id != self.request.tool or (
                (self.request.saved_citation_id is not None) != (self.citation_sha256 is not None)):
            raise ValueError('LIBRARY_HANDLER_EVENT_INVALID')
        return self


class LibraryHandlerCall(DomainModel):
    run_id: UUID
    event_seq: PositiveInt
    payload: LibraryHandlerEvent


class LibraryHandlerResult(DomainModel):
    result: AssistantLibraryToolResult
    citation_ids: Annotated[tuple[UUID, ...], Field(max_length=8)]

    @model_validator(mode='after')
    def exact_saved_citation_ids(self):
        count = len(self.result.page.citations) if self.result.page is not None else 1
        if count != len(self.citation_ids) or len(set(self.citation_ids)) != count:
            raise ValueError('LIBRARY_HANDLER_RESULT_INVALID')
        return self


class LibraryHandlerReceiptView(DomainModel):
    id: UUID
    run_id: UUID
    event_seq: PositiveInt
    handler_id: AssistantLibraryTool
    handler_version: Literal['1']
    request: LibraryHandlerRequest
    scope: ScopeSnapshot
    result: LibraryHandlerResult
    created_at: UTCDatetime

    @model_validator(mode='after')
    def matching_receipt_identity(self):
        if (self.handler_id != self.request.tool or self.handler_id != self.result.result.tool
                or self.scope != self.result.result.scope):
            raise ValueError('LIBRARY_HANDLER_RECEIPT_INVALID')
        if self.request.query is not None and self.request.query != self.result.result.page.query:
            raise ValueError('LIBRARY_HANDLER_RECEIPT_INVALID')
        return self


class LibraryHandlerExecution(DomainModel):
    receipt: LibraryHandlerReceiptView
    replayed: StrictBool


class SavedLibraryCitation(DomainModel):
    id: UUID
    receipt_id: UUID
    run_id: UUID
    scope: ScopeSnapshot
    citation: CitationRef
    created_at: UTCDatetime


class AssistantResearchAccepted(DomainModel):
    workflow: Literal['local-research-v1'] = 'local-research-v1'
    call_id: UUID
    request_sha256: SHA256


class AssistantResearchView(DomainModel):
    run: AssistantRunSummary
    receipts: Annotated[tuple[LibraryHandlerReceiptView, ...], Field(max_length=8)]


class AssistantResearchHistoryItem(DomainModel):
    message_id: UUID
    research: AssistantResearchView


class AssistantResearchHistoryView(DomainModel):
    scope: ScopeSnapshot
    items: Annotated[tuple[AssistantResearchHistoryItem, ...], Field(max_length=50)]


class MainContextSelection(DomainModel):
    expected_scope: ScopeSnapshot
    expected_composer_revision: NonNegativeInt
    citation_ids: Annotated[tuple[UUID, ...], Field(min_length=1, max_length=8)]
    # Explicit bounded-rounds preview shape; the default keeps the v1 template.
    max_rounds: Annotated[int, Field(strict=True, ge=1, le=4)] = 1
    # When given and the preview is ready, the response carries a matching send basis.
    request_id: UUID | None = None

    @field_validator('citation_ids')
    @classmethod
    def unique_context_selection(cls, value):
        if len(value) != len(set(value)):
            raise ValueError('duplicate selected citation')
        return value


class MainContextSource(DomainModel):
    saved_citation_id: UUID
    kind: Literal['case_csv', 'law_markdown']
    title: Annotated[str, StringConstraints(strict=True, max_length=2000)]
    version_id: LibraryHash
    quote: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=1200)]
    quote_sha256: LibraryHash
    start: NonNegativeInt
    end: PositiveInt
    line_start: PositiveInt
    line_end: PositiveInt
    article: Annotated[str, StringConstraints(strict=True, max_length=200)] | None
    ambiguous: StrictBool
    source_match: Literal['record_quote_matched'] = 'record_quote_matched'
    support_status: Literal['unverified'] = 'unverified'
    applicability_status: Literal['unverified'] = 'unverified'

    @model_validator(mode='after')
    def exact_context_source(self):
        if (self.end - self.start != len(self.quote) or self.line_end < self.line_start
                or hashlib.sha256(self.quote.encode('utf-8')).hexdigest() != self.quote_sha256):
            raise ValueError('CONTEXT_SOURCE_INVALID')
        return self


class MainContextManifest(DomainModel):
    format_version: Literal['saved-library-context-v1']
    question: AssistantText
    sources: Annotated[tuple[MainContextSource, ...], Field(min_length=1, max_length=8)]

    @model_validator(mode='after')
    def exact_context_manifest(self):
        identifiers = tuple(item.saved_citation_id for item in self.sources)
        if not self.question.strip() or len(identifiers) != len(set(identifiers)):
            raise ValueError('CONTEXT_MANIFEST_INVALID')
        return self


class MainContextSourceBinding(DomainModel):
    saved_citation_id: UUID
    citation_sha256: SHA256


class MainContextSendBasis(DomainModel):
    """Immutable description of proposed input, never an authorization grant."""
    input_format: Literal['library-context-v1', 'library-context-v2'] = 'library-context-v1'
    template_version: Literal['saved-library-context-system-v1',
                              'saved-library-context-system-v2'] = 'saved-library-context-system-v1'
    request_id: UUID
    expected_scope: ScopeSnapshot
    expected_composer_revision: NonNegativeInt
    system_sha256: SHA256
    manifest_sha256: SHA256
    source_bindings: Annotated[tuple[MainContextSourceBinding, ...], Field(min_length=1, max_length=8)]
    config_sha256: SHA256
    wire_sha256: SHA256

    @model_validator(mode='after')
    def unique_source_bindings(self):
        ids = tuple(item.saved_citation_id for item in self.source_bindings)
        if len(set(ids)) != len(ids):
            raise ValueError('CONTEXT_INPUT_INVALID')
        if (self.input_format == 'library-context-v1') != (
                self.template_version == 'saved-library-context-system-v1'):
            raise ValueError('CONTEXT_INPUT_INVALID')
        return self


class MainContextPreview(DomainModel):
    scope: ScopeSnapshot
    composer_revision: NonNegativeInt
    manifest: MainContextManifest
    manifest_sha256: SHA256
    system_text: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=4096)]
    state: Literal['not_configured', 'ready', 'input_too_large']
    model: Literal['deepseek-flash', 'deepseek-v4-pro'] | None
    config_sha256: SHA256 | None
    max_input_bytes: Annotated[int, Field(strict=True, ge=1, le=262144)] | None
    wire_payload_json: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=524288)] | None
    wire_sha256: SHA256 | None
    wire_bytes: PositiveInt | None
    sending_enabled: Literal[False] = False
    # Data for the native approval step, never a grant; present only on request.
    send_basis: MainContextSendBasis | None = None

    @model_validator(mode='after')
    def consistent_context_preview(self):
        from .config import canonical_json
        manifest = canonical_json(self.manifest.model_dump(mode='json'))
        if hashlib.sha256(manifest.encode('utf-8')).hexdigest() != self.manifest_sha256:
            raise ValueError('CONTEXT_PREVIEW_INVALID')
        configured = (self.model, self.config_sha256, self.max_input_bytes,
            self.wire_payload_json, self.wire_sha256, self.wire_bytes)
        if self.state == 'not_configured':
            if any(value is not None for value in configured):
                raise ValueError('CONTEXT_PREVIEW_INVALID')
            return self
        if any(value is None for value in configured):
            raise ValueError('CONTEXT_PREVIEW_INVALID')
        raw = self.wire_payload_json.encode('utf-8')
        body = json.loads(self.wire_payload_json)
        if (not isinstance(body, dict) or set(body) != {
                'model', 'messages', 'max_tokens', 'stream', 'thinking', 'response_format'}
                or canonical_json(body) != self.wire_payload_json or body['model'] != self.model
                or body['messages'] != [{'role':'system', 'content':self.system_text}, {'role':'user', 'content':manifest}]
                or type(body['max_tokens']) is not int or not 1 <= body['max_tokens'] <= 8192
                or body['stream'] is not False or body['thinking'] != {'type':'disabled'}
                or body['response_format'] != {'type':'json_object'}
                or len(raw) != self.wire_bytes or hashlib.sha256(raw).hexdigest() != self.wire_sha256
                or (self.state == 'ready') != (len(raw) <= self.max_input_bytes)):
            raise ValueError('CONTEXT_PREVIEW_INVALID')
        if self.send_basis is not None:
            basis = self.send_basis
            if (self.state != 'ready' or basis.expected_scope != self.scope
                    or basis.expected_composer_revision != self.composer_revision
                    or basis.system_sha256 != hashlib.sha256(
                        self.system_text.encode('utf-8')).hexdigest()
                    or basis.manifest_sha256 != self.manifest_sha256
                    or basis.config_sha256 != self.config_sha256
                    or basis.wire_sha256 != self.wire_sha256
                    or len(basis.source_bindings) != len(self.manifest.sources)
                    or any(binding.saved_citation_id != source.saved_citation_id for binding, source
                        in zip(basis.source_bindings, self.manifest.sources))):
                raise ValueError('CONTEXT_PREVIEW_INVALID')
        return self


class MainContextRequest(DomainModel):
    run_id: UUID
    message_id: UUID
    scope: ScopeSnapshot
    composer_revision: NonNegativeInt
    manifest: MainContextManifest
    basis: MainContextSendBasis

    @model_validator(mode='after')
    def exact_context_identity(self):
        from .config import canonical_json
        expected = self.basis.expected_scope.model_dump()
        expected['input_revision'] += 1
        raw = canonical_json(self.manifest.model_dump(mode='json'))
        if (self.scope.model_dump() != expected
                or self.composer_revision != self.basis.expected_composer_revision + 1
                or hashlib.sha256(raw.encode('utf-8')).hexdigest() != self.basis.manifest_sha256
                or tuple(item.saved_citation_id for item in self.manifest.sources)
                != tuple(item.saved_citation_id for item in self.basis.source_bindings)):
            raise ValueError('CONTEXT_INPUT_INVALID')
        return self


class MainContextPreparedInput(DomainModel):
    request: MainContextRequest
    wire_payload_json: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=524288)]

    @model_validator(mode='after')
    def exact_context_wire(self):
        if hashlib.sha256(self.wire_payload_json.encode('utf-8')).hexdigest() != self.request.basis.wire_sha256:
            raise ValueError('CONTEXT_INPUT_INVALID')
        return self


class MainContextCitation(DomainModel):
    saved_citation_id: UUID
    quote_sha256: SHA256


class MainContextCandidate(DomainModel):
    text: AssistantText
    citations: Annotated[tuple[MainContextCitation, ...], Field(max_length=8)] = ()

    @model_validator(mode='after')
    def unique_context_citations(self):
        ids = tuple(item.saved_citation_id for item in self.citations)
        if not self.text.strip() or len(ids) != len(set(ids)):
            raise ValueError('MODEL_OUTPUT_INVALID')
        return self


class MainContextToolCall(DomainModel):
    """One model-emitted plan item; the shape mirrors the fixed handler request."""
    tool: AssistantLibraryTool
    query: AssistantLibraryQuery | None = None
    saved_citation_id: UUID | None = None

    @model_validator(mode='after')
    def exact_planned_tool_call(self):
        search = self.tool == 'legal_library.search'
        if search != (self.query is not None) or search == (self.saved_citation_id is not None):
            raise ValueError('MODEL_OUTPUT_INVALID')
        return self


class MainContextToolPlan(DomainModel):
    """A non-final round outcome: bounded fixed-tool calls, never free actions."""
    calls: Annotated[tuple[MainContextToolCall, ...], Field(min_length=1, max_length=8)]


class MainContextReply(DomainModel):
    state: Literal['received', 'sent_unknown', 'failed_before_send']
    provider_request_id: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=256)] | None = None
    usage: MainUsage | None = None
    output: MainContextCandidate | None = None
    tool_plan: MainContextToolPlan | None = None
    error_code: Literal['BLOCKED_LIVE', 'PROVIDER_ERROR', 'MODEL_OUTPUT_INVALID'] | None = None

    @model_validator(mode='after')
    def consistent_context_reply(self):
        if self.output is not None and self.tool_plan is not None:
            raise ValueError('a round is either a final candidate or a tool plan')
        if self.tool_plan is not None and (self.state != 'received' or self.error_code is not None):
            raise ValueError('tool plan requires a received validated response')
        if self.output is not None and (self.state != 'received' or self.error_code is not None):
            raise ValueError('output requires a received validated response')
        if self.output is None and self.tool_plan is None and self.error_code is None:
            raise ValueError('failed response needs a fixed error code')
        if self.state != 'received' and (self.usage is not None or self.provider_request_id is not None):
            raise ValueError('unknown/unsent response cannot claim received usage')
        return self


class MainContextToolOutcomeCitation(DomainModel):
    """Bounded receipt citation projection fed back to the model; never live data."""
    saved_citation_id: UUID
    title: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=2000)]
    quote: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=1200)]
    quote_sha256: SHA256

    @model_validator(mode='after')
    def exact_outcome_citation(self):
        if hashlib.sha256(self.quote.encode('utf-8')).hexdigest() != self.quote_sha256:
            raise ValueError('CONTEXT_INPUT_INVALID')
        return self


class MainContextToolOutcome(DomainModel):
    """Deterministic projection of one persisted handler receipt."""
    receipt_id: UUID
    tool: AssistantLibraryTool
    citations: Annotated[tuple[MainContextToolOutcomeCitation, ...], Field(max_length=8)] = ()


class MainContextRoundExchange(DomainModel):
    """One executed intermediate round: the emitted plan plus its receipt projections."""
    round_no: Annotated[int, Field(strict=True, ge=1, le=3)]
    plan: MainContextToolPlan
    outcomes: Annotated[tuple[MainContextToolOutcome, ...], Field(min_length=1, max_length=8)]

    @model_validator(mode='after')
    def exact_round_exchange(self):
        if len(self.outcomes) != len(self.plan.calls):
            raise ValueError('CONTEXT_INPUT_INVALID')
        return self


class MainContextRoundsPreparedInput(DomainModel):
    """Immutable input of any v2 round; round 1 carries no exchanges."""
    request: MainContextRequest
    round_no: Annotated[int, Field(strict=True, ge=1, le=4)]
    exchanges: Annotated[tuple[MainContextRoundExchange, ...], Field(max_length=3)] = ()
    wire_payload_json: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=524288)]

    @model_validator(mode='after')
    def exact_rounds_wire(self):
        if self.round_no != len(self.exchanges) + 1:
            raise ValueError('CONTEXT_INPUT_INVALID')
        if tuple(item.round_no for item in self.exchanges) != tuple(range(1, self.round_no)):
            raise ValueError('CONTEXT_INPUT_INVALID')
        if self.round_no == 1 and (hashlib.sha256(self.wire_payload_json.encode('utf-8')).hexdigest()
                != self.request.basis.wire_sha256):
            raise ValueError('CONTEXT_INPUT_INVALID')
        return self


class MainContextSubmission(DomainModel):
    """Trusted web submission for one source-bound answer; format is server-fixed."""
    request_id: UUID
    expected_scope: ScopeSnapshot
    expected_composer_revision: NonNegativeInt
    content: AssistantText
    citation_ids: Annotated[tuple[UUID, ...], Field(min_length=1, max_length=8)]

    @field_validator('content')
    @classmethod
    def nonblank_context_question(cls, value):
        if not value.strip():
            raise ValueError('message text required')
        return value

    @field_validator('citation_ids')
    @classmethod
    def unique_context_submission(cls, value):
        if len(value) != len(set(value)):
            raise ValueError('duplicate selected citation')
        return value


class MainContextOutputView(DomainModel):
    id: UUID
    run_id: UUID
    scope: ScopeSnapshot
    audience: Literal['internal'] = 'internal'
    generation_kind: Literal['model_generated'] = 'model_generated'
    review_status: Literal['unverified'] = 'unverified'
    candidate: MainContextCandidate
    created_at: UTCDatetime


class MainContextAttemptView(DomainModel):
    id: UUID
    run_id: UUID
    scope: ScopeSnapshot
    input_format: Literal['library-context-v1', 'library-context-v2'] = 'library-context-v1'
    state: MainAttemptState
    reserved_usd: MainUSD
    unit: Literal['USD'] = 'USD'
    receipt: MainReceipt | None
    output: MainContextOutputView | None


class NativeContextAuthorization(DomainModel):
    session_token: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=256)] = Field(repr=False)
    expected_config_version: UUID
    basis: MainContextSendBasis
    max_total_usd: Annotated[MainUSD, Field(gt=0, le=1000000)]
    valid_for_seconds: Annotated[int, Field(strict=True, ge=1, le=900)]
    # Explicit bounded-rounds grant shape; the default keeps single-round bytes.
    max_rounds: Annotated[int, Field(strict=True, ge=1, le=4)] = 1


class MainGenerationHistoryItem(DomainModel):
    message_id: UUID
    attempt: MainAttemptView | MainContextAttemptView | MainProfileAttemptView | MainMaterialAttemptView


class MainGenerationHistoryView(DomainModel):
    scope: ScopeSnapshot
    items: Annotated[tuple[MainGenerationHistoryItem, ...], Field(max_length=50)]


ProfileField = Literal['title', 'contact', 'consultation', 'questions', 'materials',
                       'follow_up_at', 'follow_up_note', 'client_reply', 'internal_notes',
                       'principal_amount', 'interest_amount', 'payment_amount']


class ProfileMessageRef(DomainModel):
    kind: Literal['message']
    conversation_id: UUID
    message_id: UUID
    source_revision: PositiveInt
    start: NonNegativeInt
    end: NonNegativeInt
    quote: Annotated[AssistantText, Field(min_length=1)]
    quote_sha256: SHA256

    @model_validator(mode='after')
    def exact_quote(self):
        if self.end - self.start != len(self.quote) or hashlib.sha256(
                self.quote.encode('utf-8')).hexdigest() != self.quote_sha256:
            raise ValueError('profile message offsets/hash must match the exact quote')
        return self


class ProfileDocumentRef(DomainModel):
    kind: Literal['document']
    conversation_id: UUID
    attachment_id: UUID
    original_sha256: SHA256
    parse_revision: PositiveInt
    result_sha256: SHA256
    anchor: Anchor

    @model_validator(mode='after')
    def anchor_belongs_to_attachment(self):
        if self.anchor.document_version_id != self.attachment_id or not self.anchor.quote:
            raise ValueError('profile document reference requires its own nonempty anchor')
        return self


ProfileSourceRef = Annotated[Union[ProfileMessageRef, ProfileDocumentRef], Field(discriminator='kind')]


class ProfileDocumentSource(DomainModel):
    """A selected, parsed attachment supplied by a trusted source assembler."""
    conversation_id: UUID
    attachment_id: UUID
    original_name: IntakeLabel
    original_sha256: SHA256
    parse_revision: PositiveInt
    result_sha256: SHA256
    result: ParseResult


class ProfileSourceSnapshot(DomainModel):
    scope: ScopeSnapshot
    messages: Annotated[tuple[AssistantMessageView, ...], Field(max_length=200)] = ()
    documents: Annotated[tuple[ProfileDocumentSource, ...], Field(max_length=20)] = ()


class ProfileListValue(DomainModel):
    kind: Literal['list']
    value: Annotated[tuple[IntakeLabel, ...], Field(max_length=30)]


class ProfileMaterialsValue(DomainModel):
    kind: Literal['materials']
    value: Annotated[tuple[IntakeMaterial, ...], Field(max_length=30)]


def _profile_money(value: object) -> Decimal:
    # Check the exact tuple, not Decimal.normalize(), which uses ambient precision.
    if type(value) not in (str, int, Decimal) or len(str(value)) > 80:
        raise ValueError('bounded exact profile amount required')
    try:
        parsed = Decimal(value)
    except DecimalException as exc:
        raise ValueError('valid profile amount required') from exc
    if not parsed.is_finite() or parsed < 0:
        raise ValueError('finite nonnegative profile amount required')
    if parsed == 0:
        return Decimal(0)
    sign, raw_digits, exponent = parsed.as_tuple()
    digits = list(raw_digits)
    while digits[-1] == 0:
        digits.pop()
        exponent += 1
    places = max(0, -exponent)
    whole = max(0, len(digits) + exponent)
    if places > 8 or whole > 16 or whole + places > 24:
        raise ValueError('profile amount requires at most 16 whole and 8 fractional digits')
    return Decimal((sign, tuple(digits), exponent))


class ProfileMoneyValue(DomainModel):
    kind: Literal['money']
    value: Annotated[Decimal, BeforeValidator(_profile_money)]
    unit: Annotated[str, StringConstraints(pattern=r'^[A-Z]{3}$')]


ProfileValue = Annotated[Union[TextFactValue, NullFactValue, DatetimeFactValue,
                              ProfileListValue, ProfileMaterialsValue, ProfileMoneyValue],
                         Field(discriminator='kind')]


class ProfileEdit(DomainModel):
    """Trusted manual edit; protection does not mean factual verification."""
    field: ProfileField
    value: ProfileValue

    @model_validator(mode='after')
    def field_type_and_limits(self):
        expected = {'questions': 'list', 'materials': 'materials', 'follow_up_at': 'datetime',
                    'principal_amount': 'money', 'interest_amount': 'money', 'payment_amount': 'money'}
        if self.value.kind == 'null':
            return self
        if self.value.kind != expected.get(self.field, 'text'):
            raise ValueError('profile field/value type mismatch')
        if self.field in IntakeDraft.model_fields:
            IntakeDraft.model_validate({'title': '待整理咨询', self.field: self.value.value})
        return self


class ProfileProposal(ProfileEdit):
    origin: Literal['user_statement', 'document_statement', 'model_inference']
    verification: Literal['unverified'] = 'unverified'
    source_refs: Annotated[tuple[ProfileSourceRef, ...], Field(max_length=40)] = ()

    @model_validator(mode='after')
    def model_may_only_propose(self):
        if self.field == 'contact' and self.value.kind != 'null':
            raise ValueError('contact values require trusted local/manual input, never model inference')
        if self.value.kind != 'null' and (not self.source_refs or self.value.value in ('', ())):
            raise ValueError('known proposals require sources and nonempty values; unknown uses null')
        if self.value.kind == 'materials' and any(x.state == 'checked' for x in self.value.value):
            raise ValueError('model cannot check materials')
        required_kind = {'user_statement': 'message', 'document_statement': 'document'}.get(self.origin)
        if required_kind and any(r.kind != required_kind for r in self.source_refs):
            raise ValueError('profile origin must match its source kind')
        return self


class ProfilePatch(DomainModel):
    schema_version: Literal['assistant.profile_patch.v1'] = 'assistant.profile_patch.v1'
    scope: ScopeSnapshot
    base_profile_revision: NonNegativeInt
    changes: Annotated[tuple[ProfileProposal, ...], Field(max_length=60)] = ()


def _profile_verification(candidates, protected):
    values = []
    for value in [c.value for c in candidates if c.value.kind != 'null'] + (
            [protected] if protected is not None else []):
        if value not in values:
            values.append(value)
    return 'conflicted' if len(values) > 1 else 'unverified' if values else 'unknown'


class ProfileFieldState(DomainModel):
    field: ProfileField
    candidates: Annotated[tuple[ProfileProposal, ...], Field(max_length=60)] = ()
    protected_value: ProfileValue | None = None
    verification: Literal['unknown', 'unverified', 'conflicted']

    @model_validator(mode='after')
    def consistent_field(self):
        if any(x.field != self.field for x in self.candidates):
            raise ValueError('profile candidates must use their containing field')
        if self.protected_value is not None:
            ProfileEdit(field=self.field, value=self.protected_value)
        if self.verification != _profile_verification(self.candidates, self.protected_value):
            raise ValueError('profile verification must reflect its candidates and protected value')
        return self


class ProfileDraftState(DomainModel):
    scope: ScopeSnapshot
    revision: NonNegativeInt
    fields: Annotated[tuple[ProfileFieldState, ...], Field(max_length=12)] = ()

    @model_validator(mode='after')
    def historical_scope(self):
        if len({f.field for f in self.fields}) != len(self.fields) or (self.fields and self.revision == 0):
            raise ValueError('profile revision/fields are inconsistent')
        for field in self.fields:
            for candidate in field.candidates:
                for ref in candidate.source_refs:
                    limit = self.scope.input_revision if ref.kind == 'message' else self.scope.materials_revision
                    revision = ref.source_revision if ref.kind == 'message' else ref.parse_revision
                    if ref.conversation_id != self.scope.conversation_id or revision > limit:
                        raise ValueError('historical profile source exceeds its conversation snapshot')
        return self


class ProfileMergeResult(DomainModel):
    profile: ProfileDraftState
    changed: StrictBool
    projection: IntakeDraft | None


class ProfileCommitInput(DomainModel):
    request_id: UUID
    patch: ProfilePatch
    expected_intake_id: UUID | None = None
    expected_intake_revision: PositiveInt | None = None
    manual_edits: Annotated[tuple[ProfileEdit, ...], Field(max_length=12)] = ()
    project_intake: StrictBool = False

    @model_validator(mode='after')
    def target_and_edits(self):
        if (self.expected_intake_id is None) != (self.expected_intake_revision is None):
            raise ValueError('intake identity and revision must be supplied together')
        if len({edit.field for edit in self.manual_edits}) != len(self.manual_edits):
            raise ValueError('manual fields must be unique')
        return self


class ProfileCommitReceipt(DomainModel):
    conversation_id: UUID
    sequence: PositiveInt
    request_id: UUID
    profile_revision: NonNegativeInt
    profile_changed: StrictBool
    intake_id: UUID | None
    intake_revision: PositiveInt | None
    intake_sha256: SHA256 | None
    projection_changed: StrictBool
    consultation_origin: Literal['user', 'profile_summary']
    event_type: Literal['profile.saved', 'profile.unchanged']
    audience: Literal['internal'] = 'internal'
    created_at: UTCDatetime

    @model_validator(mode='after')
    def consistent_receipt(self):
        if len({self.intake_id is None, self.intake_revision is None, self.intake_sha256 is None}) != 1:
            raise ValueError('intake receipt requires identity, revision and digest')
        if self.profile_changed and self.profile_revision == 0 or self.projection_changed and self.intake_id is None:
            raise ValueError('changed receipt requires its saved revision')
        expected = 'profile.saved' if self.profile_changed or self.projection_changed else 'profile.unchanged'
        if self.event_type != expected:
            raise ValueError('event must reflect actual changes')
        return self


class ConversationHistoryMessage(DomainModel):
    message_id: UUID
    role: Literal['user', 'assistant']
    source_revision: PositiveInt
    content: AssistantText


ConversationHistory = Annotated[tuple[ConversationHistoryMessage, ...], Field(max_length=16)]


def _conversation_history(history, revision):
    if len(history) % 2 or len({item.message_id for item in history}) != len(history):
        raise ValueError('history requires unique completed question/answer pairs')
    previous = 0
    for question, answer in zip(history[::2], history[1::2]):
        if (question.role != 'user' or answer.role != 'assistant'
                or question.source_revision != answer.source_revision
                or not previous < question.source_revision <= revision
                or not question.content.strip() or not answer.content.strip()):
            raise ValueError('history order or revision invalid')
        previous = question.source_revision
    if len(json.dumps([item.model_dump(mode='json') for item in history],
                      ensure_ascii=False, separators=(',', ':')).encode('utf-8')) > 32768:
        raise ValueError('history exceeds its local byte budget')


class MainProfileRequest(MainRequest):
    """Saved current text, with explicitly bound prior context for template v2."""
    input_format: Literal['profile-text-v1'] = 'profile-text-v1'
    template_version: Literal['profile-text-system-v1', 'profile-text-system-v2'] = 'profile-text-system-v1'
    conversation_history: ConversationHistory = Field(default=(), exclude_if=lambda value: not value)
    source_revision: PositiveInt
    base_profile_revision: NonNegativeInt

    @model_validator(mode='after')
    def current_message_revision(self):
        if self.source_revision != self.scope.input_revision:
            raise ValueError('profile text must be the current saved user message')
        _conversation_history(self.conversation_history, self.source_revision - 1)
        if bool(self.conversation_history) != (self.template_version == 'profile-text-system-v2'):
            raise ValueError('history requires the v2 template')
        return self


class ProfileTextQuote(DomainModel):
    start: NonNegativeInt
    end: NonNegativeInt
    quote: Annotated[AssistantText, Field(min_length=1)]

    @model_validator(mode='after')
    def exact_length(self):
        if self.end - self.start != len(self.quote):
            raise ValueError('profile quote offsets must use Unicode code points')
        return self


class ProfileTextChange(ProfileEdit):
    origin: Literal['user_statement', 'model_inference']
    quotes: Annotated[tuple[ProfileTextQuote, ...], Field(max_length=40)]

    @field_validator('value', mode='before')
    @classmethod
    def explicit_wire_values(cls, value):
        # Narrow this new model protocol without changing shared/manual values.
        if isinstance(value, Mapping) and value.get('kind') in ('money', 'datetime'):
            raw = value.get('value')
            if type(raw) is not str:
                raise ValueError('profile wire money and datetime require explicit strings')
            if value['kind'] == 'datetime' and datetime.fromisoformat(raw).utcoffset() is None:
                raise ValueError('profile wire datetime requires an explicit ISO timezone')
        return value


class MainProfileModelOutput(MainCandidate):
    """Model wire input: no server IDs, hashes, permissions or review state."""
    citations: Annotated[tuple[MainCitation, ...], Field(max_length=0)]
    profile_changes: Annotated[tuple[ProfileTextChange, ...], Field(max_length=60)]


class MainProfileCandidate(MainCandidate):
    profile_patch: ProfilePatch


class MainProfileReply(MainReply):
    output: MainProfileCandidate | None = None


class MainProfileOutputView(MainOutputView):
    candidate: MainProfileCandidate


class MainProfileSaveView(DomainModel):
    outcome: Literal['applied', 'unchanged', 'blocked']
    reason_code: Literal['version_conflict', 'save_failed'] | None
    receipt: ProfileCommitReceipt | None

    @model_validator(mode='after')
    def consistent_save(self):
        if self.outcome == 'blocked':
            if self.reason_code is None or self.receipt is not None:
                raise ValueError('blocked save requires a reason and no receipt')
        elif (self.reason_code is not None or self.receipt is None
                or self.receipt.event_type != ('profile.saved' if self.outcome == 'applied' else 'profile.unchanged')):
            raise ValueError('save outcome requires its matching receipt')
        return self


class MainProfileAttemptView(MainAttemptView):
    input_format: Literal['profile-text-v1'] = 'profile-text-v1'
    output: MainProfileOutputView | None
    profile_save: MainProfileSaveView | None = None





class AssistantOutputSource(DomainModel):
    kind: Literal['model', 'profile']
    output_id: UUID | None = None
    profile_revision: Annotated[int, Field(strict=True,ge=1,le=2**63-1)] | None = None

    @model_validator(mode='after')
    def exact_saved_source(self):
        if self.kind == 'model':
            if self.output_id is None or self.profile_revision is not None:
                raise ValueError('model source requires only output_id')
        elif self.profile_revision is None or self.output_id is not None:
            raise ValueError('profile source requires only profile_revision')
        return self


class AssistantOutputSelection(DomainModel):
    source: AssistantOutputSource
    audience: Literal['client', 'internal']


class AssistantOutputExportInput(AssistantOutputSelection):
    expected_content_sha256: SHA256


class AssistantOutputOption(DomainModel):
    source: AssistantOutputSource
    label: NonEmpty
    audiences: tuple[Literal['client', 'internal'], ...]


class AssistantOutputList(DomainModel):
    conversation_id: UUID
    items: Annotated[tuple[AssistantOutputOption, ...], Field(max_length=20)]
    next_before: AssistantOutputSource | None = None


class AssistantOutputPreview(DomainModel):
    id: UUID
    conversation_id: UUID
    selection: AssistantOutputSelection
    title: NonEmpty
    source_label: NonEmpty
    text: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=262144)]
    notes: tuple[str, ...]
    citations: tuple[str, ...]
    review_status: Literal['unverified'] = 'unverified'
    content_sha256: SHA256


class ReceptionWorksheetBasis(DomainModel):
    expected_scope: ScopeSnapshot
    base_profile_revision: Annotated[int, Field(strict=True,ge=0,le=2**63-1)]


class ReceptionWorksheetPrepareInput(ReceptionWorksheetBasis):
    expected_composer_revision: Annotated[int, Field(strict=True,ge=0,le=2**63-1)]


class ReceptionWorksheetView(DomainModel):
    scope: ScopeSnapshot
    composer_revision: NonNegativeInt
    profile_revision: NonNegativeInt
    expected_intake_id: UUID | None
    expected_intake_revision: PositiveInt | None
    writable: StrictBool
    fields: Annotated[tuple[ProfileFieldState, ...], Field(max_length=5)]


class ReceptionQuestionSuggestion(DomainModel):
    question: Annotated[str, StringConstraints(strict=True,min_length=1,max_length=300)]
    reason: Annotated[str, StringConstraints(strict=True,min_length=1,max_length=300)]
    source_field: Literal['consultation'] = 'consultation'
    quote: Annotated[str, StringConstraints(strict=True,min_length=1,max_length=300)]
    materials: Annotated[tuple[IntakeLabel, ...], Field(max_length=5)] = ()


class ReceptionQuestionSuggestions(DomainModel):
    scope: ScopeSnapshot
    profile_revision: NonNegativeInt
    origin: Literal['template'] = 'template'
    model_called: Literal[False] = False
    items: Annotated[tuple[ReceptionQuestionSuggestion, ...], Field(max_length=10)]


class ReceptionPreparedTask(DomainModel):
    scope: ScopeSnapshot
    composer_revision: NonNegativeInt
    profile_revision: NonNegativeInt
    content: AssistantText
    model_called: Literal[False] = False


class MainProfileSendBasis(DomainModel):
    """Description of outbound bytes and local save intent, never permission."""
    input_format: Literal['profile-text-v1'] = 'profile-text-v1'
    template_version: Literal['profile-text-system-v1', 'profile-text-system-v2'] = 'profile-text-system-v1'
    conversation_history: ConversationHistory = Field(default=(), exclude_if=lambda value: not value)
    purpose: Literal['reply_and_profile_draft'] = 'reply_and_profile_draft'
    handler_id: Literal['profile.save'] = 'profile.save'
    handler_version: Literal['1'] = '1'
    request_id: UUID
    expected_scope: ScopeSnapshot
    expected_composer_revision: NonNegativeInt
    content_sha256: SHA256
    base_profile_revision: NonNegativeInt
    expected_intake_id: UUID | None
    expected_intake_revision: PositiveInt | None
    project_intake: StrictBool
    system_sha256: SHA256
    config_sha256: SHA256
    wire_sha256: SHA256
    wire_bytes: Annotated[int, Field(strict=True, ge=1, le=262144)]

    @model_validator(mode='after')
    def paired_intake_baseline(self):
        _conversation_history(self.conversation_history, self.expected_scope.input_revision)
        if bool(self.conversation_history) != (self.template_version == 'profile-text-system-v2'):
            raise ValueError('history requires the v2 template')
        if (self.expected_intake_id is None) != (self.expected_intake_revision is None):
            raise ValueError('profile save target requires identity and revision')
        if (self.expected_scope.scope_kind == 'intake'
                and self.expected_intake_id != self.expected_scope.scope_ref):
            raise ValueError('profile save target must match its intake scope')
        return self


class MainProfileSelection(DomainModel):
    request_id: UUID
    expected_scope: ScopeSnapshot
    expected_composer_revision: NonNegativeInt
    project_intake: StrictBool = False


class MainProfileSubmission(AssistantMessageInput):
    project_intake: StrictBool = False


class NativeProfileAuthorization(DomainModel):
    session_token: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=256)] = Field(repr=False)
    expected_config_version: UUID
    basis: MainProfileSendBasis
    max_total_usd: Annotated[MainUSD, Field(gt=0, le=1000000)]
    valid_for_seconds: Annotated[int, Field(strict=True, ge=1, le=900)]


class MainProfilePreparedInput(DomainModel):
    request: MainProfileRequest
    basis: MainProfileSendBasis
    composer_revision: PositiveInt
    wire_payload_json: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=262144)]

    @model_validator(mode='after')
    def exact_profile_submission(self):
        request, basis = self.request, self.basis
        expected = basis.expected_scope.model_copy(update={
            'input_revision': basis.expected_scope.input_revision + 1})
        if (request.scope != expected or self.composer_revision != basis.expected_composer_revision + 1
                or request.source_revision != expected.input_revision
                or request.source_sha256 != basis.content_sha256
                or request.base_profile_revision != basis.base_profile_revision
                or request.input_format != basis.input_format or request.template_version != basis.template_version
                or request.conversation_history != basis.conversation_history):
            raise ValueError('profile input differs from its submission basis')
        wire = self.wire_payload_json.encode('utf-8')
        if len(wire) != basis.wire_bytes or hashlib.sha256(wire).hexdigest() != basis.wire_sha256:
            raise ValueError('profile wire differs from its submission basis')
        return self


class TaskMediaInput(DomainModel):
    media_id: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=200)]
    name: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=240)]
    mime: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=200)]
    status: Literal['pending', 'unsupported', 'ready'] = 'pending'
    attachment_id: UUID | None = None
    sha256: SHA256 | None = None
    parse_revision: PositiveInt | None = None

    @model_validator(mode='after')
    def complete_ready_reference(self):
        if self.status == 'ready' and any(value is None for value in
                (self.attachment_id, self.sha256, self.parse_revision)):
            raise ValueError('ready media requires an attachment, hash and parse revision')
        if self.attachment_id is None and (self.sha256 is not None or self.parse_revision is not None):
            raise ValueError('media metadata requires an attachment')
        return self


class TaskInboxEventInput(DomainModel):
    event_id: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=200)]
    text: Annotated[str, StringConstraints(strict=True, max_length=20000)] = ''
    task_id: UUID | None = None
    reply_to_event_id: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=200)] | None = Field(
        default=None, exclude_if=lambda value: value is None)
    start_new: StrictBool = False
    media: Annotated[tuple[TaskMediaInput, ...], Field(max_length=20)] = ()

    @model_validator(mode='after')
    def usable_event(self):
        if not self.text.strip() and not self.media:
            raise ValueError('an event requires text or media')
        if self.start_new and (self.task_id is not None or self.reply_to_event_id is not None):
            raise ValueError('explicit task and new task are mutually exclusive')
        if len({item.media_id for item in self.media}) != len(self.media):
            raise ValueError('media IDs must be unique within the event')
        return self


class TaskInboxBatchInput(DomainModel):
    expected_cursor: NonNegativeInt
    next_cursor: PositiveInt
    events: Annotated[tuple[TaskInboxEventInput, ...], Field(min_length=1, max_length=100)]

    @model_validator(mode='after')
    def increasing_cursor(self):
        if self.next_cursor <= self.expected_cursor:
            raise ValueError('cursor must advance')
        if len({event.event_id for event in self.events}) != len(self.events):
            raise ValueError('duplicate event IDs in a batch')
        return self


class TaskChannelBindingView(DomainModel):
    id: UUID
    conversation_id: UUID
    channel: Literal['synthetic', 'weixin_personal'] = 'synthetic'
    cursor: NonNegativeInt
    created_at: UTCDatetime


class TaskInboxEventView(DomainModel):
    id: UUID
    binding_id: UUID
    event_id: NonEmpty
    text: str
    task_id: UUID | None
    reply_to_event_id: str | None = Field(default=None,exclude_if=lambda value: value is None)
    start_new: StrictBool
    media: tuple[TaskMediaInput, ...]
    association: Literal['assigned', 'unassigned']
    created_at: UTCDatetime


class TaskManifestMedia(TaskMediaInput):
    result_sha256: SHA256 | None = None
    reading_status: Literal['readable', 'partial', 'needs_baseline', 'failed'] | None = None
    excluded: StrictBool = False
    exclusion_reason: NonEmpty | None = None


class TaskManifestEvent(DomainModel):
    id: UUID
    event_id: NonEmpty
    payload_sha256: SHA256
    text: str
    media: tuple[TaskManifestMedia, ...]


class TaskDraftManifest(DomainModel):
    draft_id: UUID
    conversation_id: UUID
    scope: ScopeSnapshot
    revision: PositiveInt
    instruction: str
    main_attachment_id: UUID | None
    events: tuple[TaskManifestEvent, ...]
    review_status: Literal['unverified'] = 'unverified'
    synthetic: Literal[True] = True


class TaskMediaResolutionInput(DomainModel):
    event_id: UUID
    media_id: NonEmpty
    action: Literal['resolve', 'exclude']
    replacement: TaskMediaInput | None = None
    reason: Annotated[NonEmpty, Field(max_length=1000)] | None = None

    @model_validator(mode='after')
    def explicit_resolution(self):
        if self.action == 'resolve':
            if (self.replacement is None or self.replacement.status != 'ready'
                    or self.replacement.media_id != self.media_id):
                raise ValueError('resolution requires a ready reference with the same media ID')
        elif self.replacement is not None or self.reason is None:
            raise ValueError('exclusion requires a reason and no replacement')
        return self


class TaskMediaResolutionView(TaskMediaResolutionInput):
    id: UUID
    revision: PositiveInt
    created_at: UTCDatetime


TaskExecutionState = Literal['prepared', 'creating_matter', 'awaiting_facts', 'queued',
    'running', 'completed', 'failed', 'blocked']


class TaskExecutionView(DomainModel):
    id: UUID
    draft_id: UUID
    revision: PositiveInt
    manifest_sha256: SHA256
    manifest: TaskDraftManifest
    state: TaskExecutionState
    matter_id: UUID | None = None
    job_id: UUID | None = None
    review_run_id: UUID | None = None
    document_versions: Mapping[UUID, SHA256] = Field(default_factory=dict)
    source_versions: Mapping[UUID, UUID] = Field(default_factory=dict)
    prepare_request_id: UUID | None = None
    review_request_id: UUID | None = None
    review_input_sha256: SHA256 | None = None
    error: Annotated[str, StringConstraints(strict=True, max_length=200)] | None = None
    created_at: UTCDatetime
    updated_at: UTCDatetime


class TaskDraftView(DomainModel):
    id: UUID
    conversation_id: UUID
    parent_draft_id: UUID | None
    revision: PositiveInt
    state: Literal['collecting', 'paused', 'cancelled', 'frozen']
    instruction: str
    main_attachment_id: UUID | None
    events: tuple[TaskInboxEventView, ...]
    media_resolutions: tuple[TaskMediaResolutionView, ...]
    manifest_sha256: SHA256
    blockers: tuple[str, ...]
    execution: TaskExecutionView | None
    created_at: UTCDatetime
    updated_at: UTCDatetime


class TaskDraftListView(DomainModel):
    binding: TaskChannelBindingView | None
    items: tuple[TaskDraftView, ...]
    unassigned_events: tuple[TaskInboxEventView, ...]


class TaskInboxBatchReceipt(DomainModel):
    binding: TaskChannelBindingView
    events: tuple[TaskInboxEventView, ...]
    drafts: tuple[TaskDraftView, ...]


class TaskDraftUpdateInput(DomainModel):
    expected_revision: PositiveInt
    action: Literal['update', 'assign', 'pause', 'resume', 'cancel'] = 'update'
    instruction: Annotated[str, StringConstraints(strict=True, max_length=20000)] | None = None
    event_ids: Annotated[tuple[UUID, ...], Field(max_length=100)] = ()
    main_attachment_id: UUID | None = None
    media_resolutions: Annotated[tuple[TaskMediaResolutionInput, ...], Field(max_length=100)] = ()

    @model_validator(mode='after')
    def explicit_changes(self):
        if len(set(self.event_ids)) != len(self.event_ids):
            raise ValueError('duplicate event IDs')
        if self.action == 'assign' and not self.event_ids:
            raise ValueError('assignment requires event IDs')
        if self.action != 'assign' and self.event_ids:
            raise ValueError('event IDs are only accepted by assignment')
        if self.action != 'update' and (self.instruction is not None or self.main_attachment_id is not None):
            raise ValueError('content changes require update')
        if self.media_resolutions and self.action != 'update':
            raise ValueError('media resolution requires update')
        if len({(item.event_id,item.media_id) for item in self.media_resolutions}) != len(self.media_resolutions):
            raise ValueError('duplicate media resolutions')
        return self


class TaskFreezeInput(DomainModel):
    expected_revision: PositiveInt
    manifest_sha256: SHA256


class TaskExecutionPrepareInput(DomainModel):
    matter_id: UUID
    request_id: UUID


class TaskExecutionCreateInput(DomainModel):
    request_id: UUID
    matter: MatterCreateInput


class TaskExecutionContext(DomainModel):
    execution: TaskExecutionView
    facts: FactSnapshot | None = None
    parses: tuple[ParseResult, ...] = ()
    review: ReviewRun | None = None


class TaskExecutionReviewInput(DomainModel):
    request_id: UUID
    review: ReviewStartInput


class WeixinOfflineScope(DomainModel):
    """Local preview scope; this does not authenticate a remote Weixin account."""
    bot_account_id: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=256)]
    sender_peer_id: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=256)]
    owner_id: UUID
    session_id: UUID
    binding_id: UUID
    expected_scope: ScopeSnapshot
    task_cursor: NonNegativeInt
    upstream_cursor: Annotated[str, StringConstraints(strict=True, max_length=262144)]

    @field_validator('bot_account_id', 'sender_peer_id')
    @classmethod
    def exact_nonblank_identity(cls, value):
        if not value.strip() or any(character.isspace() or ord(character) < 32 for character in value):
            raise ValueError('exact nonblank identity required')
        return value


class WeixinOfflinePlan(DomainModel):
    """Read-only translation, never a durable inbox or cursor receipt."""
    scope: WeixinOfflineScope
    response_sha256: SHA256
    next_upstream_cursor: Annotated[str, StringConstraints(strict=True, max_length=262144)]
    batch: TaskInboxBatchInput | None
    event_payload_hashes: Annotated[dict[str, SHA256], Field(max_length=100)]

    @model_validator(mode='after')
    def exact_planned_events(self):
        expected = {event.event_id for event in self.batch.events} if self.batch else set()
        if set(self.event_payload_hashes) != expected:
            raise ValueError('message hashes must identify exactly the planned events')
        if self.batch and (self.batch.expected_cursor != self.scope.task_cursor
                or self.batch.next_cursor != self.scope.task_cursor + 1):
            raise ValueError('planned task cursor differs from preview scope')
        return self


def _weixin_identity(value: str) -> str:
    if not value or any(character.isspace() or ord(character) < 32 for character in value):
        raise ValueError('exact nonblank identity required')
    return value


WeixinIdentity = Annotated[str, StringConstraints(strict=True, min_length=1, max_length=256),
    AfterValidator(_weixin_identity)]
WeixinCursor = Annotated[str, StringConstraints(strict=True, max_length=262144)]
WeixinInboxReason = Literal['sender_unbound', 'binding_revoked', 'scope_stale', 'scope_denied',
    'recipient_mismatch', 'message_unsupported', 'message_invalid', 'event_conflict',
    'previously_blocked', 'replayed']


def _weixin_revocation(value):
    fields = (value.revoked_at, value.revoked_by, value.revoke_reason)
    if any(item is not None for item in fields):
        if (any(item is None for item in fields) or value.revoked_at < value.created_at
                or not value.revoke_reason.strip()):
            raise ValueError('revocation requires actor, reason and a later timestamp')
    return value


class WeixinAccountSnapshot(DomainModel):
    """Credential-free synthetic identity and committed account cursor, without authentication."""
    id: UUID
    workspace_id: UUID
    owner_id: UUID
    bot_account_id: WeixinIdentity
    mode: Literal['synthetic', 'weixin_personal'] = 'synthetic'
    initial_cursor: WeixinCursor
    checkpoint_revision: NonNegativeInt
    upstream_cursor: WeixinCursor
    created_at: UTCDatetime
    revoked_at: UTCDatetime | None = None
    revoked_by: UUID | None = None
    revoke_reason: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=200)] | None = None

    @model_validator(mode='after')
    def complete_revocation(self):
        return _weixin_revocation(self)


class WeixinPeerBindingSnapshot(DomainModel):
    """Historical exact peer-to-conversation mapping; no remote credential or session."""
    id: UUID
    account_id: UUID
    sender_peer_id: WeixinIdentity
    task_binding_id: UUID
    scope: ScopeSnapshot
    scope_sha256: SHA256
    created_at: UTCDatetime
    revoked_at: UTCDatetime | None = None
    revoked_by: UUID | None = None
    revoke_reason: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=200)] | None = None

    @model_validator(mode='after')
    def complete_scope_and_revocation(self):
        from .config import canonical_json
        raw = canonical_json(self.scope.model_dump(mode='json')).encode('utf-8')
        if hashlib.sha256(raw).hexdigest() != self.scope_sha256:
            raise ValueError('scope hash does not match the historical scope')
        return _weixin_revocation(self)


class WeixinInboxDescriptor(DomainModel):
    """A durable synthetic outcome; accepted descriptions grant no task or file capability."""
    id: UUID
    poll_id: UUID
    ordinal: Annotated[int, Field(strict=True, ge=1, le=100)]
    sender_peer_id: WeixinIdentity | None = None
    upstream_message_id: Annotated[str, StringConstraints(strict=True, pattern=r'^(0|[1-9][0-9]{0,19})$')] | None = None
    source_event_id: Annotated[str, StringConstraints(strict=True, pattern=r'^wx1:[a-f0-9]{64}$')] | None = None
    source_sha256: SHA256
    status: Literal['accepted_pending_dispatch', 'blocked', 'duplicate']
    reason: WeixinInboxReason | None = None
    mapping_id: UUID | None = None
    prior_descriptor_id: UUID | None = None
    payload: TaskInboxEventInput | None = None

    @model_validator(mode='after')
    def complete_safe_outcome(self):
        source = (self.sender_peer_id, self.upstream_message_id, self.source_event_id)
        if any(value is not None for value in source) and any(value is None for value in source):
            raise ValueError('source identity requires exact peer, message ID and event ID')
        if self.upstream_message_id is not None and int(self.upstream_message_id) > 2**64-1:
            raise ValueError('source message ID exceeds uint64')
        if self.status == 'accepted_pending_dispatch':
            if (self.mapping_id is None or self.source_event_id is None or self.payload is None
                    or self.reason is not None or self.prior_descriptor_id is not None):
                raise ValueError('accepted outcome requires mapped source and safe payload only')
            self._safe_payload()
        elif self.status == 'duplicate':
            if (self.prior_descriptor_id is None or self.source_event_id is None
                    or self.payload is not None or self.reason != 'replayed'):
                raise ValueError('duplicate outcome requires a prior source and no payload')
        elif self.payload is not None or self.reason is None or self.reason == 'replayed':
            raise ValueError('blocked outcome requires a fixed reason and no payload')
        if self.prior_descriptor_id is not None and (self.source_event_id is None
                or self.status == 'blocked' and self.reason not in ('event_conflict', 'previously_blocked')):
            raise ValueError('prior descriptor is only valid for an identified repeat')
        if self.status == 'blocked' and self.reason in ('event_conflict', 'previously_blocked') and self.prior_descriptor_id is None:
            raise ValueError('repeated blocked outcome requires its original descriptor')
        return self

    def _safe_payload(self):
        import re
        import unicodedata
        from pathlib import PureWindowsPath

        value = self.payload
        if value.event_id != self.source_event_id or value.task_id is not None or value.start_new:
            raise ValueError('inbox payload cannot select or start a task')
        if value.reply_to_event_id is not None and re.fullmatch(r'wx1:[a-f0-9]{64}', value.reply_to_event_id) is None:
            raise ValueError('reply must use a source event namespace')
        mime = {'.pdf':'application/pdf', '.docx':'application/vnd.openxmlformats-officedocument.wordprocessingml.document'}
        for item in value.media:
            name = item.name
            if (item.status != 'pending' or item.attachment_id is not None or item.sha256 is not None
                    or item.parse_revision is not None or PureWindowsPath(name).suffix.lower() not in mime
                    or mime[PureWindowsPath(name).suffix.lower()] != item.mime
                    or name in ('.', '..') or name[-1:] in (' ', '.') or PureWindowsPath(name).is_reserved()
                    or any(character in '/\\:<>"|?*' or unicodedata.category(character).startswith('C') for character in name)
                    or re.fullmatch(re.escape(self.source_event_id)+r':(?:[0-9]|1[0-9])', item.media_id) is None):
                raise ValueError('inbox media is only a safe pending DOCX/PDF description')


class WeixinPollReceipt(DomainModel):
    """Complete immutable poll accounting; its digest includes every ordered outcome."""
    id: UUID
    account_id: UUID
    request_id: UUID
    request_sha256: SHA256
    response_sha256: SHA256
    expected_revision: NonNegativeInt
    next_revision: PositiveInt
    expected_cursor: WeixinCursor
    next_cursor: WeixinCursor
    descriptor_count: Annotated[int, Field(strict=True, ge=0, le=100)]
    receipt_sha256: SHA256
    created_at: UTCDatetime
    descriptors: Annotated[tuple[WeixinInboxDescriptor, ...], Field(max_length=100)]

    @model_validator(mode='after')
    def complete_hashed_poll(self):
        from .config import canonical_json
        if (self.next_revision != self.expected_revision + 1
                or self.descriptor_count != len(self.descriptors)
                or tuple(value.ordinal for value in self.descriptors) != tuple(range(1, self.descriptor_count+1))
                or any(value.poll_id != self.id for value in self.descriptors)
                or len({value.id for value in self.descriptors}) != len(self.descriptors)):
            raise ValueError('poll requires all ordered descriptors and one checkpoint revision')
        raw = canonical_json(self.model_dump(mode='json', exclude={'receipt_sha256'})).encode('utf-8')
        if hashlib.sha256(raw).hexdigest() != self.receipt_sha256:
            raise ValueError('poll receipt hash mismatch')
        return self


class WeixinAccountCreateInput(DomainModel):
    """An explicit local synthetic account; owner and workspace are server-owned."""
    bot_account_id: WeixinIdentity
    initial_cursor: WeixinCursor = ''


class WeixinPeerBindInput(DomainModel):
    sender_peer_id: WeixinIdentity
    task_binding_id: UUID
    expected_scope: ScopeSnapshot


class WeixinRevokeInput(DomainModel):
    reason: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=200)]

    @field_validator('reason')
    @classmethod
    def nonblank_reason(cls, value):
        if not value.strip():
            raise ValueError('revocation reason must not be blank')
        return value


class WeixinPollInput(DomainModel):
    request_id: UUID
    expected_revision: NonNegativeInt
    expected_cursor: WeixinCursor


class WeixinDispatchReceipt(DomainModel):
    """Immutable TaskInbox acknowledgement; assignment and draft state may change later."""
    id: UUID
    descriptor_id: UUID
    account_id: UUID
    mapping_id: UUID
    actor_id: UUID
    task_binding_id: UUID
    task_event_id: UUID
    source_event_id: Annotated[str, StringConstraints(strict=True, pattern=r'^wx1:[a-f0-9]{64}$')]
    payload_sha256: SHA256
    expected_task_cursor: NonNegativeInt
    next_task_cursor: PositiveInt
    created_at: UTCDatetime
    receipt_sha256: SHA256

    @model_validator(mode='after')
    def complete_hashed_dispatch(self):
        from .config import canonical_json
        if self.next_task_cursor != self.expected_task_cursor + 1:
            raise ValueError('dispatch advances the local task cursor exactly once')
        raw = canonical_json(self.model_dump(mode='json', exclude={'receipt_sha256'})).encode('utf-8')
        if hashlib.sha256(raw).hexdigest() != self.receipt_sha256:
            raise ValueError('dispatch receipt hash mismatch')
        return self


def _weixin_refresh_reason(value):
    if not value.strip() or value != value.strip():
        raise ValueError('explicit refresh reason must be nonblank and trimmed')
    return value


class WeixinPeerRefreshInput(DomainModel):
    request_id: UUID
    expected_grant_revision: NonNegativeInt
    expected_scope_sha256: SHA256
    expected_scope: ScopeSnapshot
    reason: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=200),
                      AfterValidator(_weixin_refresh_reason)]


class WeixinPeerScopeGrant(DomainModel):
    """Immutable explicit authorization for newer versions of the same local target."""
    id: UUID
    mapping_id: UUID
    request_id: UUID
    actor_id: UUID
    revision: PositiveInt
    previous_scope_sha256: SHA256
    scope: ScopeSnapshot
    scope_sha256: SHA256
    checkpoint_revision: NonNegativeInt
    created_at: UTCDatetime
    reason: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=200),
                      AfterValidator(_weixin_refresh_reason)]
    grant_sha256: SHA256

    @model_validator(mode='after')
    def complete_hashed_authorization(self):
        from .config import canonical_json
        scope = canonical_json(self.scope.model_dump(mode='json')).encode('utf-8')
        raw = canonical_json(self.model_dump(mode='json', exclude={'grant_sha256'})).encode('utf-8')
        if hashlib.sha256(scope).hexdigest() != self.scope_sha256:
            raise ValueError('authorization scope hash mismatch')
        if hashlib.sha256(raw).hexdigest() != self.grant_sha256:
            raise ValueError('authorization grant hash mismatch')
        return self


class WeixinConversationAuthorizationView(DomainModel):
    """Current desktop projection, without account identities or grant reasons."""
    mode: Literal['synthetic'] = 'synthetic'
    state: Literal['unbound', 'current', 'refresh_required', 'target_changed', 'revoked', 'archived', 'restored_blocked']
    current_scope: ScopeSnapshot
    authorized_scope: ScopeSnapshot | None
    grant_revision: NonNegativeInt
    scope_sha256: SHA256 | None

    @model_validator(mode='after')
    def complete_authorization_projection(self):
        from .config import canonical_json
        if self.authorized_scope is None:
            if (self.state not in ('unbound', 'archived', 'restored_blocked')
                    or self.scope_sha256 is not None or self.grant_revision != 0):
                raise ValueError('unbound projection cannot invent authority')
            return self
        raw = canonical_json(self.authorized_scope.model_dump(mode='json')).encode('utf-8')
        if self.state == 'unbound' or hashlib.sha256(raw).hexdigest() != self.scope_sha256:
            raise ValueError('bound projection requires its exact scope hash')
        same_target = all(getattr(self.current_scope, key) == getattr(self.authorized_scope, key) for key in (
            'workspace_id', 'conversation_id', 'scope_kind', 'scope_ref', 'binding_revision'))
        newer = (same_target and self.current_scope != self.authorized_scope
            and self.current_scope.input_revision >= self.authorized_scope.input_revision
            and self.current_scope.materials_revision >= self.authorized_scope.materials_revision)
        if (self.state == 'current' and self.current_scope != self.authorized_scope
                or self.state == 'refresh_required' and not newer):
            raise ValueError('projection state must describe the exact current scope')
        return self


class WeixinPeerGeneration(DomainModel):
    """Immutable target history only; no runtime authority or dispatch capability."""
    id: UUID
    root_mapping_id: UUID
    generation: PositiveInt
    request_id: UUID
    actor_id: UUID
    task_binding_id: UUID
    scope: ScopeSnapshot
    scope_sha256: SHA256
    previous_generation_sha256: SHA256 | None
    previous_scope_sha256: SHA256
    checkpoint_revision: NonNegativeInt
    created_at: UTCDatetime
    reason: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=200),
                      AfterValidator(_weixin_refresh_reason)]
    generation_sha256: SHA256

    @model_validator(mode='after')
    def complete_hashed_generation(self):
        from .config import canonical_json
        if (self.generation == 1) != (self.previous_generation_sha256 is None):
            raise ValueError('only the first generation omits its predecessor hash')
        scope = canonical_json(self.scope.model_dump(mode='json')).encode('utf-8')
        raw = canonical_json(self.model_dump(mode='json', exclude={'generation_sha256'})).encode('utf-8')
        if hashlib.sha256(scope).hexdigest() != self.scope_sha256:
            raise ValueError('generation scope hash mismatch')
        if hashlib.sha256(raw).hexdigest() != self.generation_sha256:
            raise ValueError('generation hash mismatch')
        return self


class WeixinPeerGenerationInput(DomainModel):
    request_id: UUID
    expected_generation: NonNegativeInt
    expected_previous_generation_sha256: SHA256 | None
    expected_previous_scope_sha256: SHA256
    expected_checkpoint_revision: NonNegativeInt
    task_binding_id: UUID
    expected_scope: ScopeSnapshot
    reason: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=200),
                      AfterValidator(_weixin_refresh_reason)]

    @model_validator(mode='after')
    def complete_generation_predecessor(self):
        if (self.expected_generation == 0) != (self.expected_previous_generation_sha256 is None):
            raise ValueError('only generation zero omits its predecessor hash')
        return self


class WeixinGenerationReceiptView(DomainModel):
    """Historical HTTP metadata; its full-record digest is an opaque receipt."""
    mode: Literal['synthetic'] = 'synthetic'
    state: Literal['history_only'] = 'history_only'
    generation: PositiveInt
    request_id: UUID
    scope: ScopeSnapshot
    scope_sha256: SHA256
    previous_generation_sha256: SHA256 | None
    previous_scope_sha256: SHA256
    checkpoint_revision: NonNegativeInt
    created_at: UTCDatetime
    generation_sha256: SHA256

    @model_validator(mode='after')
    def complete_historical_receipt(self):
        from .config import canonical_json
        if (self.generation == 1) != (self.previous_generation_sha256 is None):
            raise ValueError('only the first generation omits its predecessor hash')
        raw = canonical_json(self.scope.model_dump(mode='json')).encode('utf-8')
        if hashlib.sha256(raw).hexdigest() != self.scope_sha256:
            raise ValueError('receipt scope hash mismatch')
        return self


class WeixinGenerationHeadView(DomainModel):
    """A coherent historical CAS snapshot, without current execution authority."""
    mode: Literal['synthetic'] = 'synthetic'
    state: Literal['history_only'] = 'history_only'
    generation: NonNegativeInt
    generation_sha256: SHA256 | None
    scope: ScopeSnapshot
    scope_sha256: SHA256
    checkpoint_revision: NonNegativeInt

    @model_validator(mode='after')
    def complete_historical_head(self):
        from .config import canonical_json
        if (self.generation == 0) != (self.generation_sha256 is None):
            raise ValueError('only generation zero omits its generation hash')
        raw = canonical_json(self.scope.model_dump(mode='json')).encode('utf-8')
        if hashlib.sha256(raw).hexdigest() != self.scope_sha256:
            raise ValueError('head scope hash mismatch')
        return self


class WeixinGenerationPreview(DomainModel):
    """Hypothetical translation; never an intake receipt or runtime authorization."""
    mode: Literal['synthetic'] = 'synthetic'
    state: Literal['preview_only'] = 'preview_only'
    head: WeixinGenerationHeadView
    plan: WeixinOfflinePlan

    @model_validator(mode='after')
    def same_preview_target(self):
        if self.head.scope != self.plan.scope.expected_scope:
            raise ValueError('preview scope differs from persistent generation head')
        return self


class WeixinDescriptorGeneration(DomainModel):
    """Immutable parent links for one original accepted nonzero-generation source."""
    descriptor_id: UUID
    generation_id: UUID
    generation_sha256: SHA256
    task_binding_id: UUID
    scope_sha256: SHA256
    payload_sha256: SHA256
    provenance_sha256: SHA256

    @model_validator(mode='after')
    def complete_provenance_hash(self):
        from .config import canonical_json
        raw=canonical_json(self.model_dump(mode='json',exclude={'provenance_sha256'})).encode('utf-8')
        if hashlib.sha256(raw).hexdigest()!=self.provenance_sha256:
            raise ValueError('descriptor generation provenance hash mismatch')
        return self


class WeixinGenerationDispatchInput(DomainModel):
    descriptor_id: UUID


class WeixinGenerationDispatchReceiptView(DomainModel):
    """Redacted acknowledgement; the full-record digest is an opaque receipt."""
    mode: Literal['synthetic'] = 'synthetic'
    state: Literal['recorded'] = 'recorded'
    descriptor_id: UUID
    conversation_id: UUID
    task_event_id: UUID
    expected_task_cursor: NonNegativeInt
    next_task_cursor: PositiveInt
    created_at: UTCDatetime
    receipt_sha256: SHA256

    @model_validator(mode='after')
    def complete_dispatch_projection(self):
        if self.next_task_cursor != self.expected_task_cursor + 1:
            raise ValueError('dispatch projection advances the task cursor exactly once')
        return self


class EvidenceStatementRef(DomainModel):
    kind: Literal['statement']
    profile_revision: PositiveInt
    start: NonNegativeInt
    end: NonNegativeInt
    quote: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=12000)]

    @model_validator(mode='after')
    def exact_span(self):
        if self.end - self.start != len(self.quote):
            raise ValueError('statement offsets must cover the exact quote')
        return self


class EvidenceManualExcerpt(DomainModel):
    kind: Literal['manual_excerpt']
    attachment_id: UUID
    original_sha256: SHA256
    location: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=300)]
    quote: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=4000)]


EvidenceSource = Annotated[Union[EvidenceStatementRef, ProfileDocumentRef, EvidenceManualExcerpt], Field(discriminator='kind')]


class EvidenceFact(DomainModel):
    id: UUID
    category: Literal['agreement', 'disbursement', 'repayment', 'other']
    content: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=2000)]
    event_date: date | None = None
    review_state: Literal['pending', 'reviewed', 'disputed'] = 'pending'
    note: Annotated[str, StringConstraints(strict=True, max_length=1000)] = ''
    source: EvidenceSource

    @field_validator('content')
    @classmethod
    def not_blank(cls, value):
        if not value.strip():
            raise ValueError('fact content is required')
        return value


class EvidenceCommitInput(DomainModel):
    request_id: UUID
    expected_scope: ScopeSnapshot
    expected_profile_revision: NonNegativeInt
    base_revision: NonNegativeInt
    rows: Annotated[tuple[EvidenceFact, ...], Field(max_length=100)]

    @field_validator('rows')
    @classmethod
    def distinct_rows(cls, values):
        if len({r.id for r in values}) != len(values):
            raise ValueError('fact IDs cannot repeat')
        return values


class EvidenceSnapshot(DomainModel):
    scope: ScopeSnapshot
    profile_revision: NonNegativeInt
    revision: PositiveInt
    rows: Annotated[tuple[EvidenceFact, ...], Field(max_length=100)]
    created_at: UTCDatetime


class EvidenceReceipt(DomainModel):
    conversation_id: UUID
    request_id: UUID
    revision: PositiveInt
    snapshot_sha256: SHA256
    created_at: UTCDatetime


class EvidenceMaterial(DomainModel):
    attachment: AssistantAttachmentView
    selected: StrictBool
    parse_revision: PositiveInt | None = None
    reading_status: Literal['readable', 'partial', 'needs_baseline', 'failed'] | None = None


class EvidenceWorksheetView(DomainModel):
    scope: ScopeSnapshot
    profile_revision: NonNegativeInt
    revision: NonNegativeInt
    rows: Annotated[tuple[EvidenceFact, ...], Field(max_length=100)]
    saved_scope: ScopeSnapshot | None = None
    statement: str | None = None
    writable: StrictBool
    materials: tuple[EvidenceMaterial, ...]
    historical_ids: tuple[UUID, ...] = ()


class FollowupFactRef(DomainModel):
    evidence_revision: PositiveInt
    fact_id: UUID


class FollowupMaterialRef(DomainModel):
    attachment_id: UUID
    original_sha256: SHA256
    parse_revision: PositiveInt | None


class FollowupItem(DomainModel):
    id: UUID
    title: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=300)]
    reason: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=1000)]
    impact: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=1000)]
    next_action: Annotated[str, StringConstraints(strict=True, max_length=1000)] = ''
    due_date: date | None = None
    status: Literal['open', 'requested', 'received', 'completed', 'cancelled'] = 'open'
    result: Annotated[str, StringConstraints(strict=True, max_length=2000)] = ''
    facts: Annotated[tuple[FollowupFactRef, ...], Field(max_length=10)] = ()
    materials: Annotated[tuple[FollowupMaterialRef, ...], Field(max_length=10)] = ()

    @model_validator(mode='after')
    def grounded_item(self):
        if any(not x.strip() for x in (self.title,self.reason,self.impact)):
            raise ValueError('follow-up title, reason and impact are required')
        if not self.facts and not self.materials:
            raise ValueError('follow-up requires an existing fact or material')
        if (len({x.fact_id for x in self.facts})!=len(self.facts)
                or len({x.attachment_id for x in self.materials})!=len(self.materials)):
            raise ValueError('follow-up links cannot repeat')
        if self.status in ('completed','cancelled') and not self.result.strip():
            raise ValueError('closed follow-up requires its handling result')
        return self


class FollowupCommitInput(DomainModel):
    request_id: UUID
    expected_scope: ScopeSnapshot
    expected_profile_revision: NonNegativeInt
    expected_evidence_revision: NonNegativeInt
    base_revision: NonNegativeInt
    items: Annotated[tuple[FollowupItem, ...], Field(max_length=100)]

    @field_validator('items')
    @classmethod
    def distinct_items(cls, values):
        if len({x.id for x in values})!=len(values):
            raise ValueError('follow-up IDs cannot repeat')
        return values


class FollowupSnapshot(DomainModel):
    scope: ScopeSnapshot
    profile_revision: NonNegativeInt
    evidence_revision: NonNegativeInt
    revision: PositiveInt
    items: Annotated[tuple[FollowupItem, ...], Field(max_length=100)]
    created_at: UTCDatetime


class FollowupReceipt(DomainModel):
    conversation_id: UUID
    request_id: UUID
    revision: PositiveInt
    snapshot_sha256: SHA256
    created_at: UTCDatetime


class FollowupAttention(DomainModel):
    item_id: UUID
    reasons: tuple[str, ...]


class FollowupWorksheetView(DomainModel):
    scope: ScopeSnapshot
    profile_revision: NonNegativeInt
    evidence_revision: NonNegativeInt
    revision: NonNegativeInt
    items: Annotated[tuple[FollowupItem, ...], Field(max_length=100)]
    writable: StrictBool
    facts: Annotated[tuple[EvidenceFact, ...], Field(max_length=100)]
    materials: tuple[EvidenceMaterial, ...]
    attention: tuple[FollowupAttention, ...] = ()


class WeixinPendingQuery(DomainModel):
    target_conversation_id: UUID
    cursor: UUID | None = None
    limit: Annotated[int, Field(strict=True, ge=1, le=20)] = 20


class WeixinPendingDescriptorView(DomainModel):
    """Fixed-target metadata, without message content or channel identifiers."""
    descriptor_id: UUID
    conversation_id: UUID
    received_at: UTCDatetime
    has_text: StrictBool
    media_count: Annotated[int, Field(strict=True, ge=0, le=20)]


class WeixinPendingPage(DomainModel):
    mode: Literal['synthetic'] = 'synthetic'
    read_only: Literal[True] = True
    conversation_id: UUID
    items: Annotated[tuple[WeixinPendingDescriptorView, ...], Field(max_length=20)]
    next_cursor: UUID | None = None


BusinessWorkflow = Literal['sales', 'case', 'contract', 'court']


class BusinessInput(AssistantDraftInput):
    request_id: UUID
    workflow: BusinessWorkflow | None = None
    task_id: UUID | None = None
    new_task: StrictBool = False

    @model_validator(mode='after')
    def usable_business_input(self):
        if not self.content.strip() or self.new_task and self.task_id is not None:
            raise ValueError('business input requires text and one task selection')
        return self


class BusinessEvidenceRef(DomainModel):
    revision: PositiveInt
    snapshot_sha256: SHA256
    fact_ids: Annotated[tuple[UUID, ...], Field(max_length=100)]
    historical_ids: Annotated[tuple[UUID, ...], Field(max_length=100)] = ()


class BusinessResult(DomainModel):
    schema_version: Literal['business-local-v1'] = 'business-local-v1'
    mode: Literal['local_preparation'] = 'local_preparation'
    review_status: Literal['unverified'] = 'unverified'
    run_id: UUID
    message_id: UUID
    request_id: UUID
    task_id: UUID | None
    workflow: BusinessWorkflow | None
    scope: ScopeSnapshot
    state: Literal['completed', 'awaiting_input', 'blocked']
    text: AssistantText
    intake_id: UUID | None = None
    contract_draft_id: UUID | None = None
    source_refs: Annotated[tuple[ProfileDocumentRef, ...], Field(max_length=100)] = ()
    evidence: BusinessEvidenceRef | None = None
    created_at: UTCDatetime


class BusinessAccepted(DomainModel):
    request: BusinessInput
    scope: ScopeSnapshot
    workflow: BusinessWorkflow | None
    task_id: UUID | None


class BusinessResultRecord(DomainModel):
    result: BusinessResult
    result_sha256: SHA256


class MainMaterialSource(DomainModel):
    source_id: SHA256
    reference: ProfileDocumentRef | ProfileMessageRef

    @model_validator(mode='after')
    def source_identity(self):
        raw = json.dumps(self.reference.model_dump(mode='json'), ensure_ascii=False, sort_keys=True, separators=(',', ':'))
        if hashlib.sha256(raw.encode('utf-8')).hexdigest() != self.source_id:
            raise ValueError('MATERIAL_SOURCE_INVALID')
        return self


class MainMaterialFile(DomainModel):
    attachment_id: UUID
    name: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=300)]
    original_sha256: SHA256
    parse_revision: PositiveInt
    result_sha256: SHA256
    reading_status: Literal['readable', 'partial']
    pages: tuple[PositiveInt, ...]
    parts: tuple[NonEmpty, ...]
    unread_parts: tuple[NonEmpty, ...]
    quality_issues: tuple[NonEmpty, ...]


class MainMaterialManifest(DomainModel):
    input_format: Literal['material-business-v1'] = 'material-business-v1'
    workflow: BusinessWorkflow
    stable_task_id: UUID
    parent_business_run_id: UUID
    question: AssistantText
    materials: Annotated[tuple[MainMaterialFile, ...], Field(max_length=20)]
    sources: Annotated[tuple[MainMaterialSource, ...], Field(min_length=1, max_length=2000)]
    conversation_history: ConversationHistory = Field(default=(), exclude_if=lambda value: not value)

    @model_validator(mode='after')
    def exact_material_selection(self):
        messages = [item for item in self.sources if isinstance(item.reference, ProfileMessageRef)]
        current = messages[0].reference if messages else None
        _conversation_history(self.conversation_history, current.source_revision - 1 if current else 0)
        context = messages[1:]
        if context:
            if (self.workflow != 'court' or len(context) > 8
                    or len({item.reference.message_id for item in messages}) != len(messages)
                    or any(item.reference.source_revision >= current.source_revision for item in context)
                    or len(json.dumps([item.model_dump(mode='json') for item in context], ensure_ascii=False, separators=(',', ':')).encode('utf-8'))
                        + len(json.dumps([item.model_dump(mode='json') for item in self.conversation_history], ensure_ascii=False, separators=(',', ':')).encode('utf-8')) > 32768):
                raise ValueError('MATERIAL_MANIFEST_INVALID')
        files = {item.attachment_id:item for item in self.materials}
        if not self.question.strip() or len(files) != len(self.materials) or len({x.source_id for x in self.sources}) != len(self.sources):
            raise ValueError('MATERIAL_MANIFEST_INVALID')
        if not self.materials and self.workflow != 'sales':
            raise ValueError('MATERIAL_MANIFEST_INVALID')
        for item in self.sources:
            ref = item.reference
            if isinstance(ref, ProfileMessageRef):
                if ref.start != 0 or ref is current and ref.quote != self.question:
                    raise ValueError('MATERIAL_MANIFEST_INVALID')
                continue
            material = files.get(ref.attachment_id)
            if material is None or (ref.original_sha256, ref.parse_revision, ref.result_sha256) != (
                    material.original_sha256, material.parse_revision, material.result_sha256):
                raise ValueError('MATERIAL_MANIFEST_INVALID')
        return self


class MainMaterialSelection(DomainModel):
    request_id: UUID
    expected_scope: ScopeSnapshot
    expected_composer_revision: NonNegativeInt
    parent_business_run_id: UUID


class MainMaterialSendBasis(MainMaterialSelection):
    input_format: Literal['material-business-v1'] = 'material-business-v1'
    manifest: MainMaterialManifest
    manifest_sha256: SHA256
    system_sha256: SHA256
    config_sha256: SHA256
    wire_sha256: SHA256
    wire_bytes: Annotated[int, Field(strict=True, ge=1, le=262144)]


class MainMaterialRequest(DomainModel):
    run_id: UUID
    message_id: UUID
    scope: ScopeSnapshot
    basis: MainMaterialSendBasis


class MainMaterialPreparedInput(DomainModel):
    request: MainMaterialRequest
    wire_payload_json: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=262144)]

    @model_validator(mode='after')
    def exact_material_input(self):
        basis = self.request.basis
        expected = basis.expected_scope.model_copy(update={'input_revision':basis.expected_scope.input_revision + 1})
        raw = self.wire_payload_json.encode('utf-8')
        if self.request.scope != expected or len(raw) != basis.wire_bytes or hashlib.sha256(raw).hexdigest() != basis.wire_sha256:
            raise ValueError('MATERIAL_INPUT_INVALID')
        return self


class MainMaterialCandidate(DomainModel):
    text: AssistantText
    citations: Annotated[tuple[SHA256, ...], Field(min_length=1, max_length=100)]

    @model_validator(mode='after')
    def unique_citations(self):
        if not self.text.strip() or len(set(self.citations)) != len(self.citations):
            raise ValueError('MATERIAL_OUTPUT_INVALID')
        return self


class MainMaterialReply(MainReply):
    output: MainMaterialCandidate | None = None


class MainMaterialOutputView(MainOutputView):
    candidate: MainMaterialCandidate
    manifest: MainMaterialManifest


class MainMaterialAttemptView(MainAttemptView):
    input_format: Literal['material-business-v1'] = 'material-business-v1'
    output: MainMaterialOutputView | None


class NativeMaterialAuthorization(DomainModel):
    session_token: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=256)] = Field(repr=False)
    expected_config_version: UUID
    basis: MainMaterialSendBasis
    max_total_usd: Annotated[MainUSD, Field(gt=0, le=1000000)]
    valid_for_seconds: Annotated[int, Field(strict=True, ge=1, le=900)]




MainGenerationHistoryItem.model_rebuild()
MainGenerationHistoryView.model_rebuild()
