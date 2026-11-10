"""All media input and snapshot contracts. Host identities never come from a body."""
from datetime import datetime, timezone
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, TypeAdapter, field_validator

Identifier = Annotated[str, Field(pattern=r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')]
Digest = Annotated[str, Field(pattern=r'^[0-9a-f]{64}$')]
Text = Annotated[str, Field(min_length=1, max_length=20000)]
Visibility = Literal['owner_only', 'workspace']


class DomainModel(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True, strict=True)


class MediaActorContext(DomainModel):
    workspace_id: Identifier
    user_id: Identifier
    is_admin: StrictBool = False


class MediaRevisionRef(DomainModel):
    kind: Literal['profile', 'memory', 'source', 'event', 'project', 'brief', 'script', 'shooting_plan', 'review', 'feedback', 'conversation']
    entity_id: Identifier
    revision: Annotated[StrictInt, Field(ge=1)]
    content_sha256: Digest


class MediaProfileInput(DomainModel):
    regions: Annotated[list[Text], Field(min_length=1, max_length=20)]
    primary_business: Text
    secondary_business: list[Text] = Field(default_factory=list, max_length=20)
    audience: Text
    style: Text


class MediaMemoryInput(DomainModel):
    profile_ref: MediaRevisionRef
    category: Literal['identity', 'experience', 'opinion', 'style_sample', 'client_question']
    original: Text
    summary: Text
    confirmation: Literal['unconfirmed', 'confirmed', 'revoked'] = 'unconfirmed'


class MediaShootConstraints(DomainModel):
    capture_mode: Literal['phone_tripod', 'assisted'] = 'phone_tripod'
    camera_count: Annotated[StrictInt, Field(ge=1, le=10)] = 1
    people_count: Annotated[StrictInt, Field(ge=1, le=20)] = 1
    location: Text = 'office'
    equipment: list[Text] = Field(default_factory=lambda: ['phone', 'tripod'])
    available_minutes: Annotated[StrictInt, Field(ge=1, le=1440)] = 20


class MediaProjectInput(DomainModel):
    profile_ref: MediaRevisionRef
    title: Text
    platform: Text = '通用'
    audience: Text
    target_duration_ms: Annotated[StrictInt, Field(ge=10000, le=180000)] = 60000
    constraints: MediaShootConstraints = Field(default_factory=MediaShootConstraints)


INPUT_MODELS = {'profile': MediaProfileInput, 'memory': MediaMemoryInput, 'project': MediaProjectInput}


class MediaFeedbackInput(DomainModel):
    project_ref: MediaRevisionRef
    status: Literal['adopted', 'ignored', 'published']
    note: Annotated[str, Field(max_length=2000)] = ''


INPUT_MODELS['feedback'] = MediaFeedbackInput


class MediaSourceRefreshRequest(DomainModel):
    kind: Literal['source_refresh']
    request_id: Identifier
    source_ids: Annotated[list[Text], Field(min_length=1, max_length=20)]
    query: Text


class MediaInterviewRequest(DomainModel):
    kind: Literal['interview']
    request_id: Identifier
    profile_ref: MediaRevisionRef
    purpose: Literal['media_interview']
    model_authorized: StrictBool = False
    max_tokens: Annotated[StrictInt, Field(ge=128, le=16384)] = 4096


class MediaGenerateRequest(DomainModel):
    kind: Literal['brief', 'script', 'shooting_plan']
    request_id: Identifier
    project_ref: MediaRevisionRef
    input_refs: Annotated[list[MediaRevisionRef], Field(max_length=100)]
    purpose: Literal['media_content']
    model_authorized: StrictBool = False
    max_tokens: Annotated[StrictInt, Field(ge=128, le=16384)] = 4096
    expected_output_revision: Annotated[StrictInt, Field(ge=0)] = 0
    output_ref: MediaRevisionRef | None = None


class MediaExportRequest(DomainModel):
    kind: Literal['export']
    request_id: Identifier
    project_ref: MediaRevisionRef
    mode: Literal['draft', 'approved']
    expected_refs: Annotated[list[MediaRevisionRef], Field(min_length=1, max_length=100)]
    review_ref: MediaRevisionRef | None = None


class MediaSearchRequest(DomainModel):
    kind: Literal['source_search']
    request_id: Identifier
    query: Annotated[str, Field(min_length=1,max_length=128)]
    count: Annotated[StrictInt, Field(ge=1,le=10)] = 5
    purpose: Literal['media_sources']
    model_authorized: StrictBool = False


class MediaFetchRequest(DomainModel):
    kind: Literal['source_fetch']
    request_id: Identifier
    source_ref: MediaRevisionRef
    purpose: Literal['media_sources']
    model_authorized: StrictBool = False


MediaJobInput = Annotated[MediaSourceRefreshRequest | MediaInterviewRequest | MediaGenerateRequest |
                         MediaExportRequest | MediaSearchRequest | MediaFetchRequest, Field(discriminator='kind')]
JOB_INPUT = TypeAdapter(MediaJobInput)


class MediaSourceImport(DomainModel):
    title: Text
    url: str | None = None
    source_kind: Literal['news', 'law', 'video', 'manual']
    content_origin: Literal['user_transcript', 'user_notes', 'metadata']
    text: Annotated[str, Field(max_length=20000)] = ''
    published_at: str | None = None
    event_at: str | None = None

    @field_validator('published_at', 'event_at')
    @classmethod
    def utc_date(cls, value):
        if value is None: return value
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None: raise ValueError('UTC_DATE_REQUIRED')
        return parsed.astimezone(timezone.utc).isoformat()


class MediaSourceItem(MediaSourceImport):
    content_origin: Literal['user_transcript', 'user_notes', 'metadata', 'fetched_page', 'platform_transcript']
    content_scope: Literal['metadata', 'excerpt', 'full_text']
    verification: Literal['unverified', 'verified'] = 'unverified'
    fetched_at: str | None = None
    heat: Annotated[StrictInt, Field(ge=0)] | None = None
    source_id: str | None = None
    discovery_note: Annotated[str, Field(max_length=2000)] = ''


INPUT_MODELS['source'] = MediaSourceItem


class MediaClaim(DomainModel):
    id: Identifier
    text: Text
    source_ref: MediaRevisionRef
    evidence_quote: Text
    status: Literal['unconfirmed', 'confirmed'] = 'unconfirmed'
    kind: Literal['fact', 'law'] = 'fact'
    law_name: str | None = None
    law_status: Literal['draft', 'pending', 'effective', 'repealed', 'unverified'] | None = None
    applicability: str | None = None
    effective_at: str | None = None


class MediaRegionEvidence(DomainModel):
    region_key: Text
    relation: Literal['local_event', 'local_rule', 'national_local_angle', 'other_region', 'unknown']
    source_ref: MediaRevisionRef
    evidence_quote: Text
    status: Literal['unconfirmed', 'confirmed'] = 'unconfirmed'
    confirmed_by: Identifier | None = None


class MediaEventInput(DomainModel):
    title: Text
    source_refs: Annotated[list[MediaRevisionRef], Field(min_length=1, max_length=30)]
    claims: Annotated[list[MediaClaim], Field(max_length=100)]
    regions: Annotated[list[MediaRegionEvidence], Field(max_length=30)] = Field(default_factory=list)
    business_tags: list[Text] = Field(default_factory=list)
    event_at: str | None = None
    published_at: str | None = None
    correction_note: str = ''

    _utc_dates = field_validator('event_at','published_at')(MediaSourceImport.utc_date.__func__)


INPUT_MODELS['event'] = MediaEventInput


class MediaBriefSnapshot(DomainModel):
    project_ref: MediaRevisionRef
    profile_ref: MediaRevisionRef
    event_ref: MediaRevisionRef | None = None
    angle: Text
    audience: Text
    claims: Annotated[list[MediaClaim], Field(max_length=100)]
    memory_refs: Annotated[list[MediaRevisionRef], Field(max_length=30)]
    pending: list[Text]


class MediaScriptSegment(DomainModel):
    id: Identifier
    text: Text
    kind: Literal['fact', 'law', 'opinion', 'opening', 'advice', 'closing']
    claim_refs: list[Identifier]
    memory_refs: list[MediaRevisionRef]


class MediaScriptSnapshot(DomainModel):
    project_ref: MediaRevisionRef
    brief_ref: MediaRevisionRef
    titles: Annotated[list[Text], Field(min_length=3, max_length=3)]
    segments: Annotated[list[MediaScriptSegment], Field(min_length=1, max_length=30)]
    caption: Annotated[str, Field(max_length=20000)]
    cover_text: Text
    timing_basis: Literal['estimated'] = 'estimated'


class MediaInterviewQuestions(DomainModel):
    questions: Annotated[list[Text], Field(min_length=1, max_length=3)]


class MediaValidationResult(DomainModel):
    blocking_errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


INPUT_MODELS.update(brief=MediaBriefSnapshot,script=MediaScriptSnapshot)


class MediaShotInstruction(DomainModel):
    id: Identifier
    script_segment_ids: Annotated[list[Identifier], Field(min_length=1)]
    estimated_duration_ms: Annotated[StrictInt, Field(ge=1000, le=180000)]
    shot_size: Literal['close', 'medium', 'wide', 'detail']
    camera_position: Text
    subject_action: Text
    spoken_cue: Text
    movement_intent: Literal['static', 'pan', 'tilt', 'push_in', 'pull_out', 'tracking']
    lighting_note: Text
    audio_note: Text
    props: list[Text]
    equipment_required: list[Text]
    simple_alternative: Text


class MediaShootingPlanSnapshot(DomainModel):
    project_ref: MediaRevisionRef
    script_ref: MediaRevisionRef
    constraints: MediaShootConstraints
    timing_basis: Literal['estimated']
    planned_duration_ms: Annotated[StrictInt, Field(ge=10000, le=180000)]
    shots: Annotated[list[MediaShotInstruction], Field(min_length=1, max_length=30)]
    shooting_checklist: Annotated[list[Text], Field(min_length=1, max_length=50)]


class MediaReviewSnapshot(DomainModel):
    project_ref: MediaRevisionRef
    approved_refs: Annotated[list[MediaRevisionRef], Field(min_length=3, max_length=200)]
    dependencies_digest: Digest
    reviewer: Identifier
    approved_at: str


INPUT_MODELS.update(shooting_plan=MediaShootingPlanSnapshot,review=MediaReviewSnapshot)


class MediaConversationDetails(DomainModel):
    title: Text | None = None
    audience: Text | None = None
    regions: list[Text] | None = Field(default=None, min_length=1, max_length=20)
    primary_business: Text | None = None
    style: Text | None = None
    platform: Text | None = None
    target_duration_ms: Annotated[StrictInt, Field(ge=10000, le=180000)] | None = None
    constraints: MediaShootConstraints | None = None


class MediaConversationPending(DomainModel):
    target: Literal['source', 'memory', 'package']
    entity_id: Identifier | None = None
    fingerprint: Digest
    user_seq: Annotated[StrictInt, Field(ge=0)]


class MediaConversationSnapshot(DomainModel):
    session_id: Annotated[str, Field(pattern=r'^[A-Za-z0-9_-]{1,128}$')]
    details: MediaConversationDetails = Field(default_factory=MediaConversationDetails)
    profile_id: Identifier | None = None
    project_id: Identifier | None = None
    project_revision: Annotated[StrictInt, Field(ge=0)] = 0
    source_ids: list[Identifier] = Field(default_factory=list, max_length=100)
    memory_ids: list[Identifier] = Field(default_factory=list, max_length=100)
    job_ids: list[Identifier] = Field(default_factory=list, max_length=100)
    review_id: Identifier | None = None
    pending: MediaConversationPending | None = None


INPUT_MODELS['conversation'] = MediaConversationSnapshot


def utc_stamp():
    return datetime.now(timezone.utc).isoformat()
