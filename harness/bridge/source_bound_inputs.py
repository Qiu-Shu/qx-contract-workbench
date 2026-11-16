"""Expose the source-bound tools' existing nested contracts to MCP callers."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt


class Input(BaseModel):
    model_config = ConfigDict(extra='forbid')


class MaterialCitation(Input):
    path: str
    quote: str
    sha256: str
    chunk: StrictInt


class Citation(MaterialCitation):
    start: StrictInt | None = None
    end: StrictInt | None = None


class Excerpt(Input):
    section: Literal['parties', 'requests', 'facts', 'sections']
    citation: Citation


class Money(Input):
    citation: Citation
    amount: str


class EmploymentCitation(Input):
    path: str
    quote: str
    sha256: str | None = None
    chunk: StrictInt | None = None
    start: StrictInt | None = None
    end: StrictInt | None = None
    status: Literal['matched','unmatched','ambiguous','unverified'] | None = None
    source_kind: str | None = None


class EmploymentParameters(Input):
    contract_pay: Money | None = None
    grade_pay: Money | None = None
    minimum_pay: Money | None = None
    probation_pay: Money | None = None
    penalty: Money | None = None
    loss: Money | None = None
    monthly_compensation: Money | None = None
    monthly_pay: Money | None = None


class EmploymentFinding(Input):
    fact: str = Field(min_length=1,max_length=20000)
    basis: str = Field(min_length=1,max_length=20000)
    source: str = Field(min_length=1,max_length=20000)
    risk: str = Field(min_length=1,max_length=20000)
    action: str = Field(min_length=1,max_length=20000)
    topic: str | None = None
    pending: str | None = None
    citations: list[EmploymentCitation] | None = Field(default=None,max_length=20)
    rule: Literal['probation_pay','noncompete_comparison'] | None = None
    parameters: EmploymentParameters | None = None
    drafts: list[Literal['probation_clause','attendance_inquiry','noncompete_inquiry']] | None = Field(
        default=None,min_length=1,max_length=3,
        description='程序候选类型，可同时选多个；替代自由action，原稿保留内部核对。法律分析仍未作语义核验。')


class Calculation(Input):
    minuend: Money
    subtrahends: list[Money]


class Party(Input):
    role: Literal['plaintiff', 'defendant', 'appellant', 'appellee', 'applicant', 'respondent', 'client', 'issuer', 'recipient']
    name: str
    citation: Citation


class LitigationBrief(Input):
    parties: list[Party] | None = None
    claim_kind: Literal['payment', 'return', 'undetermined'] = 'undetermined'
    claim_amount: Money | None = Field(default=None, description='原文金额及其引文；不能在这里放算式索引。')
    calculation_index: StrictInt | None = Field(default=None, description='与claim_amount互斥；本次calculations的0起始索引，直接放在brief中。')


class LitigationIssue(Input):
    claim: Citation
    supporting: list[Citation] = Field(default_factory=list, max_length=10)
    opposing: list[Citation] = Field(default_factory=list, max_length=10)
    legal_basis: list[Citation] = Field(default_factory=list, max_length=10)


class LitigationClaim(Input):
    request: Citation
    issue_indices: list[StrictInt] = Field(default_factory=list, max_length=20)


class ClaimElement(Input):
    key: str
    supporting: list[Citation] = Field(default_factory=list,max_length=10)
    opposing: list[Citation] = Field(default_factory=list,max_length=10)


class ClaimReview(Input):
    claim_index: StrictInt
    basis: Literal['sale_price','private_loan','unjust_enrichment','service_fee']
    elements: list[ClaimElement] = Field(default_factory=list,max_length=5)


class ProcedureItem(Input):
    key: str
    citations: list[Citation] = Field(default_factory=list,max_length=10)


class RemedyReview(Input):
    decision_kind: Literal['civil_judgment','civil_order','labor_final','labor_nonfinal','labor_mixed','unknown']
    actor: Literal['party','worker','employer','unknown']
    classification_citations: list[Citation] = Field(default_factory=list,max_length=10)
    service_citation: Citation | None = None


class ProcedureReview(Input):
    route: Literal['civil_first_instance','labor_arbitration','civil_appeal','labor_award_remedy','jurisdiction_objection']
    items: list[ProcedureItem] = Field(default_factory=list,max_length=7)
    remedy: RemedyReview | None = None


class LegalReview(Input):
    claims: list[ClaimReview] = Field(default_factory=list,max_length=20)
    procedure: ProcedureReview | None = None


class SourceGroup(Input):
    subject_entry: StrictInt
    entries: list[StrictInt] = Field(min_length=1, max_length=40)


class RegisterCitation(MaterialCitation):
    case_id: str | None = None


class RegisterEntry(Input):
    field: str
    citation: RegisterCitation


class Deadline(Input):
    entry: StrictInt
    date: str
    year_basis: Literal['explicit', 'same_as_reference_assumption']


class ComplianceTracking(Input):
    as_of: str
    as_of_entry: StrictInt
    deadlines: list[Deadline]
