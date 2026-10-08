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
from typing import Annotated, Literal, Mapping, Union
from uuid import UUID

from pydantic import (
    AfterValidator, AwareDatetime, BaseModel, BeforeValidator, ConfigDict,
    Field, JsonValue, StringConstraints, field_serializer, field_validator,
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


class HumanDecision(DomainModel):
    decision: HumanDecisionKind
    reason: NonEmpty
    actor_id: UUID
    decided_at: UTCDatetime
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
    page: Annotated[int, Field(strict=True, ge=1, le=200)]
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
    candidate_source: Literal['manual_synthetic']
    real_model_calls: Literal[0] = 0
    qcc_calls: Literal[0] = 0
    model_inference: Literal['NOT_RUN'] = 'NOT_RUN'

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
    read_only: Literal[True] = True


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
    source: Literal['manual_synthetic']
    submitted_by: UUID
    submitted_at: UTCDatetime
    real_model_calls: Literal[0] = 0
    qcc_calls: Literal[0] = 0
    model_inference: Literal['NOT_RUN'] = 'NOT_RUN'


class ReviewProposal(DomainModel):
    id: UUID
    matter_id: UUID
    run_id: UUID
    policy_sha256: SHA256
    context_sha256: SHA256
    input_sha256: SHA256
    input: AssistedReviewInput
    finding_ids: tuple[UUID, ...]
    execution_receipt: ManualCandidateReceipt
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


class WorkingDraftConfirmationInput(DomainModel):
    bundle_id: UUID
    bundle_manifest_sha256: SHA256
    decision_snapshot_sha256: SHA256
    audience: Audience
    acknowledged_unresolved_finding_ids: Annotated[tuple[UUID, ...], Field(max_length=128)]
    reason: Annotated[NonEmpty, Field(max_length=2000)]

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
