"""Offline source provenance checks; never fetch code or grant production approval."""
import argparse
import hashlib
import json
import re
import unicodedata
from pathlib import Path
from typing import Literal, NamedTuple

REQUIRED_IDS = {f'G{i:02}' for i in range(1, 14)}
STATUSES = {'candidate', 'read_verified', 'license_reviewed', 'tested', 'production_approved', 'rejected'}
RUNTIME_DIRS = ('src', 'prompts', 'rules', '.agents/skills', 'scripts', 'plugins')
SHA256 = re.compile(r'^[0-9a-f]{64}$')
COMMIT = re.compile(r'^[0-9a-f]{40}$')


class VerificationResult(NamedTuple):
    ok: bool
    errors: list[str]
    warnings: list[str]
    checked_sources: int


def normalized_text(text: str) -> str:
    return unicodedata.normalize('NFC', ' '.join(text.split()))


def _local_path(root: Path, target: str) -> Path:
    if not isinstance(target, str) or not target or Path(target).is_absolute():
        raise ValueError('relative evidence path required')
    resolved = (root / target).resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise ValueError('evidence escapes project')
    return resolved


def _restricted_paths(root: Path, source: dict) -> list[str]:
    """Fingerprint matching is a defense in depth, not a claim of license clearance."""
    hashes = set(source.get('restricted_file_sha256', []))
    hashes.update(f['sha256'] for f in source.get('files', [])
                  if isinstance(f, dict) and isinstance(f.get('sha256'), str)
                  and not Path(str(f.get('path', ''))).name.lower().startswith(('license', 'copying')))
    fingerprints = set(source.get('restricted_content_fingerprints', []))
    window = source.get('fingerprint_window', 80)
    if source.get('restricted_fingerprint_file'):
        evidence = _local_path(root, source['restricted_fingerprint_file'])
        raw = evidence.read_bytes()
        if hashlib.sha256(raw).hexdigest() != source.get('restricted_fingerprint_sha256'):
            raise ValueError('fingerprint evidence tampered')
        payload = json.loads(raw.decode('utf-8-sig'))
        fingerprints.update(payload['sha256_windows'])
        window = payload['window_characters']
    if not isinstance(window, int) or not 8 <= window <= 256:
        raise ValueError('invalid fingerprint window')
    violations = []
    for directory in RUNTIME_DIRS:
        base = _local_path(root, directory)
        if not base.exists():
            continue
        for path in base.rglob('*'):
            if not path.is_file():
                continue
            if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
                violations.append(path.relative_to(root).as_posix())
                continue
            raw = path.read_bytes()
            matched = hashlib.sha256(raw).hexdigest() in hashes
            if fingerprints and not matched:
                try:
                    text = normalized_text(raw.decode('utf-8-sig'))
                except UnicodeDecodeError:
                    text = ''
                matched = any(hashlib.sha256(text[i:i + window].encode()).hexdigest() in fingerprints
                              for i in range(max(0, len(text) - window + 1)))
            if matched:
                violations.append(path.relative_to(root).as_posix())
    return violations


def verify_manifest(path: Path, mode: Literal['development', 'release']) -> VerificationResult:
    errors, warnings = [], []
    if mode not in {'development', 'release'}:
        return VerificationResult(False, ['MODE_INVALID'], [], 0)
    path = Path(path)
    root = path.parent.parent if path.parent.name == 'sources' else path.parent
    try:
        manifest = json.loads(path.read_text(encoding='utf-8-sig'))
        sources = manifest['sources']
        if manifest.get('schema_version') != '2.0' or not isinstance(sources, list):
            raise ValueError('schema version or sources invalid')
        if any(not isinstance(s, dict) or not isinstance(s.get('id'), str) for s in sources):
            raise ValueError('source record invalid')
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return VerificationResult(False, [f'MANIFEST_INVALID:{type(exc).__name__}'], [], 0)
    identifiers = [s['id'] for s in sources]
    if set(identifiers) != REQUIRED_IDS or len(identifiers) != len(REQUIRED_IDS):
        errors.append('SOURCE_SET_INCOMPLETE:expected_exactly_G01_to_G13')
    for source in sources:
        sid = source['id']
        source_error_start = len(errors)
        if not isinstance(source.get('status'), str) or source.get('status') not in STATUSES:
            errors.append(f'SOURCE_STATUS_INVALID:{sid}')
        files = source.get('files')
        if not isinstance(files, list) or any(not isinstance(f, dict) for f in files):
            errors.append(f'FILES_INVALID:{sid}')
            files = []
        checked_hashes = set()
        license_hashes = set()
        for entry in files:
            digest = entry.get('sha256', '')
            if not isinstance(digest, str) or not SHA256.fullmatch(digest):
                errors.append(f'FILE_HASH_INVALID:{sid}')
            if entry.get('usage') not in ('code', 'text', 'method') or not entry.get('path'):
                errors.append(f'FILE_METADATA_INVALID:{sid}')
            try:
                local = _local_path(root, entry.get('local_target'))
            except (ValueError, TypeError):
                errors.append(f'EVIDENCE_PATH_INVALID:{sid}')
                continue
            if not local.is_file():
                errors.append(f'FILE_MISSING:{sid}:{entry.get("path")}')
            elif hashlib.sha256(local.read_bytes()).hexdigest() != digest:
                errors.append(f'FILE_HASH_MISMATCH:{sid}:{entry.get("path")}')
            else:
                checked_hashes.add(digest)
                if (entry.get('usage') == 'text'
                        and Path(str(entry.get('path', ''))).name.lower().startswith(('license', 'copying'))):
                    license_hashes.add(digest)
        included = source.get('included_in_runtime', False)
        if type(included) is not bool:
            errors.append(f'ADOPTION_INVALID:{sid}')
            included = True
        for entry in files:
            try:
                target = _local_path(root, entry.get('local_target'))
            except (ValueError, TypeError):
                continue
            if any(target.is_relative_to((root / directory).resolve()) for directory in RUNTIME_DIRS):
                if included is False:
                    errors.append(f'ADOPTION_CONFLICT:{sid}:runtime_target_marked_excluded')
                included = True
        if source.get('adoption') in ('runtime_dependency', 'runtime_tool', 'incorporated_code',
                                     'incorporated_text', 'incorporated_method') and not included:
            errors.append(f'ADOPTION_CONFLICT:{sid}:runtime_adoption_marked_excluded')
            included = True
        if source.get('adoption') == 'reference_only' and included:
            errors.append(f'ADOPTION_CONFLICT:{sid}')
        if (included and mode == 'release') or source.get('status') == 'production_approved':
            commit = source.get('commit')
            if not isinstance(commit, str) or not COMMIT.fullmatch(commit):
                errors.append(f'SOURCE_UNLOCKED:{sid}')
            if not files:
                errors.append(f'TARGET_EVIDENCE_MISSING:{sid}')
            license_hash = source.get('license_text_sha256')
            if (not source.get('license_expression') or not isinstance(license_hash, str)
                    or license_hash not in license_hashes):
                errors.append(f'LICENSE_EVIDENCE_MISSING:{sid}')
            if source.get('dependency_review') not in ('reviewed', 'not_applicable'):
                errors.append(f'DEPENDENCY_REVIEW_PENDING:{sid}')
            if source.get('model_license_review') not in ('reviewed', 'not_applicable'):
                errors.append(f'MODEL_LICENSE_REVIEW_PENDING:{sid}')
            if (source.get('status') != 'production_approved' or not source.get('approved_by')
                    or not source.get('approved_at') or not source.get('approved_scope')):
                errors.append(f'PRODUCTION_APPROVAL_MISSING:{sid}')
        elif source.get('status') != 'production_approved':
            warnings.append(f'NOT_PRODUCTION_APPROVED:{sid}')
        approval_valid = source.get('status') == 'production_approved' and len(errors) == source_error_start
        if sid == 'G11' and not approval_valid:
            try:
                for violation in _restricted_paths(root, source):
                    errors.append(f'LICENSE_BLOCKED:{sid}:{violation}')
            except (ValueError, TypeError, KeyError, OSError):
                errors.append(f'LICENSE_SCAN_FAILED:{sid}')
            if included:
                errors.append(f'LICENSE_BLOCKED:{sid}:unapproved_runtime_adoption')
    return VerificationResult(not errors, errors, warnings, len(sources))


def main() -> int:
    parser = argparse.ArgumentParser(description='Offline upstream source and license gate')
    parser.add_argument('--manifest', type=Path, default=Path(__file__).resolve().parents[1] / 'sources/upstream.lock.json')
    parser.add_argument('--mode', choices=['development', 'release'], default='development')
    args = parser.parse_args()
    result = verify_manifest(args.manifest, args.mode)
    print(json.dumps(result._asdict(), ensure_ascii=False, indent=2))
    return 0 if result.ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
