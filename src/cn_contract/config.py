"""Strict development settings loaded from the single defaults file."""
from decimal import Decimal
import hashlib
import json
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, PrivateAttr, field_validator

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULTS_PATH = PROJECT_ROOT / 'config/defaults.json'
SPEC_DEFAULTS_SHA256 = '0e4acba46c67b731cd9662d7b118217ddc55047ab69315961c7f78dfcfa9c887'


def _exact_decimal(value):
    if isinstance(value, (float, bool)):
        raise ValueError('EXACT_DECIMAL_REQUIRED')
    return value


def canonical_json(value) -> str:
    """Sorted compact JSON with exact finite decimal number tokens."""
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError('NONFINITE_CONFIG_NUMBER')
        return format(value, 'f')
    if isinstance(value, dict):
        return '{' + ','.join(json.dumps(k, ensure_ascii=False) + ':' + canonical_json(value[k])
                              for k in sorted(value)) + '}'
    if isinstance(value, (list, tuple)):
        return '[' + ','.join(canonical_json(item) for item in value) + ']'
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


class Settings(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    _config_sha256: str = PrivateAttr(default='')
    spec_version: Literal['2.0']
    jurisdiction_default: Literal['CN-mainland']
    review_language: Literal['zh-CN']
    full_review_types: tuple[Literal['sales', 'service', 'lease', 'nda'], ...]
    tech_overlay_default: Literal['disabled_until_approved']
    qcc_enabled_default: Literal[False]
    qcc_transport_preference: Literal['official_mcp_python_sdk']
    qcc_case_budget_credits: Annotated[Decimal, BeforeValidator(_exact_decimal), Field(ge=0, le=20, allow_inf_nan=False)]
    qcc_max_calls: Annotated[int, Field(strict=True, ge=1, le=6)]
    qcc_default_pages_per_tool: Literal[1]
    qcc_auto_related_entities: Literal[0]
    qcc_approved_extra_entities_max: Annotated[int, Field(strict=True, ge=0, le=2)]
    qcc_approved_relation_depth_max: Annotated[int, Field(strict=True, ge=0, le=1)]
    qcc_unknown_price: Literal['block']
    qcc_paid_auto_retries: Literal[0]
    cross_matter_cache_default: Literal[False]
    model_provider_default: Literal['mock']
    model_json_repair_max: Annotated[int, Field(strict=True, ge=0, le=1)]
    worker_concurrency_default: Literal[1]
    upload_max_file_mib: Annotated[int, Field(strict=True, ge=1, le=50)]
    upload_max_matter_files: Annotated[int, Field(strict=True, ge=1, le=20)]
    upload_max_matter_mib: Annotated[int, Field(strict=True, ge=1, le=200)]
    parse_max_pages_per_file: Annotated[int, Field(strict=True, ge=1, le=200)]
    archive_uncompressed_max_mib: Annotated[int, Field(strict=True, ge=1, le=200)]
    archive_max_ratio: Annotated[int, Field(strict=True, ge=1, le=100)]
    input_formats: tuple[Literal['docx', 'pdf'], ...]
    zip_contract_upload: Literal[False]
    docm_upload: Literal[False]
    regression_cases: Literal[84]
    production_autosend: Literal[False]
    source_commit_lock_required: Literal[True]

    @field_validator('full_review_types')
    @classmethod
    def _types(cls, value):
        if value != ('sales', 'service', 'lease', 'nda'):
            raise ValueError('FULL_REVIEW_SCOPE_CHANGE_REQUIRES_APPROVAL')
        return value

    @field_validator('input_formats')
    @classmethod
    def _formats(cls, value):
        if value != ('docx', 'pdf'):
            raise ValueError('INPUT_FORMAT_SCOPE_CHANGE_REQUIRES_APPROVAL')
        return value

    @property
    def config_sha256(self) -> str:
        return self._config_sha256


def _unique_keys(pairs):
    output = {}
    for key, value in pairs:
        if key in output:
            raise ValueError(f'DUPLICATE_CONFIG_KEY:{key}')
        output[key] = value
    return output


def load_settings(path: Path = DEFAULTS_PATH) -> Settings:
    payload = json.loads(Path(path).read_text(encoding='utf-8-sig'), parse_float=Decimal,
                         object_pairs_hook=_unique_keys,
                         parse_constant=lambda value: (_ for _ in ()).throw(ValueError('NONFINITE_CONFIG_NUMBER')))
    settings = Settings.model_validate(payload)
    settings._config_sha256 = hashlib.sha256(canonical_json(payload).encode('utf-8')).hexdigest()
    return settings
