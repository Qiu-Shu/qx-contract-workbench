"""Hash-bound admitted fictional materials shared by entry and backup."""
import hashlib
import json
from pathlib import Path
from ..config import PROJECT_ROOT
from ..domain import SyntheticAssistedPolicy
from ..security import ServiceError

SEED_MANIFEST=PROJECT_ROOT/'tests/fixtures/assisted-v1/manifest.json'
SEED_MANIFEST_SHA256='16a8d213a16e6741459085fe72409b36849a410595d1043ee9ad1ea193feedce'


def load_seed_policy(*,manifest_path=SEED_MANIFEST):
    """Only the author-registered inventory, not a client 'fictional' assertion."""
    try:
        raw=Path(manifest_path).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=SEED_MANIFEST_SHA256:
            raise ValueError('inventory differs')
        inventory=json.loads(raw)
        cases=inventory['cases']
        if len(cases)!=12 or {c['contract_type'] for c in cases}!={'sales','service','lease','nda'}:
            raise ValueError('seed scope differs')
        for case in cases:
            relative=Path(case['path'])
            path=(PROJECT_ROOT/relative).resolve()
            approved=(PROJECT_ROOT/'tests/fixtures/assisted-v1').resolve()
            if relative.is_absolute() or not path.is_relative_to(approved) or not approved.is_relative_to(PROJECT_ROOT.resolve()):
                raise ValueError('seed location differs')
            data=path.read_bytes()
            if len(data)!=case['bytes'] or hashlib.sha256(data).hexdigest()!=case['sha256'] or case['fictional'] is not True:
                raise ValueError('seed bytes differ')
        return SyntheticAssistedPolicy(policy_id='assisted-v1-fiction-only',purpose='assisted_draft',
            document_hashes=tuple(c['sha256'] for c in cases),candidate_source='manual_synthetic')
    except (ValueError,TypeError,KeyError,OSError):
        raise ServiceError('DATA_POLICY_UNAPPROVED',409) from None
