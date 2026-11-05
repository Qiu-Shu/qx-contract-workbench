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


class Calculation(Input):
    minuend: Money
    subtrahends: list[Money]


class Party(Input):
    role: Literal['plaintiff', 'defendant', 'applicant', 'respondent', 'client', 'issuer', 'recipient']
    name: str
    citation: Citation


class LitigationBrief(Input):
    parties: list[Party] | None = None
    claim_kind: Literal['payment', 'return', 'undetermined'] = 'undetermined'
    claim_amount: Money | None = Field(default=None, description='原文金额及其引文；不能在这里放算式索引。')
    calculation_index: StrictInt | None = Field(default=None, description='与claim_amount互斥；本次calculations的0起始索引，直接放在brief中。')


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
