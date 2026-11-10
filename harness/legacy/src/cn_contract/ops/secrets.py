"""Scan explicitly supplied publish candidates; never echo a secret value."""
import re
import subprocess
from pathlib import Path
from io import BytesIO
from zipfile import ZipFile, BadZipFile
from ..domain import SecretFinding, SecretScanReport

PATTERNS = (
    ('SYNTHETIC_CANARY', re.compile(rb'SYNTHETIC_SECRET_DO_NOT_USE_[A-Za-z0-9_-]+')),
    ('PRIVATE_KEY', re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----')),
    ('CREDENTIAL_ASSIGNMENT', re.compile(rb'(?im)^\s*(?:QCC_API_KEY|OPENAI_API_KEY|API_TOKEN|CLIENT_SECRET|DATABASE_PASSWORD)\s*[=:]\s*[\"\']?(?!ref:|\$\{|<reference|server-reference|$)[A-Za-z0-9_+/=-]{12,}')),
    ('BEARER_CREDENTIAL', re.compile(rb'(?i)authorization\s*[=:]\s*[\"\']?Bearer\s+[A-Za-z0-9_.-]{16,}')),
)


def scan_candidates(candidates):
    if not isinstance(candidates, dict) or len(candidates) > 10000:
        raise ValueError('EXPLICIT_CANDIDATE_SCOPE_REQUIRED')
    findings = []
    for index, (name, raw) in enumerate(candidates.items(), start=1):
        if not isinstance(name, str) or not name or not isinstance(raw, bytes) or len(raw) > 64*1024*1024:
            raise ValueError('CANDIDATE_LIMIT')
        label = name
        if any(pattern.search(name.encode('utf-8')) for _, pattern in PATTERNS) or any(ord(c) < 32 for c in name):
            label = 'redacted-candidate-'+str(index)
        # Paths and reasons only; neither matched bytes nor the surrounding line.
        inspected = [raw, name.encode('utf-8')]
        if raw.startswith(b'PK'):
            try:
                with ZipFile(BytesIO(raw)) as archive:
                    entries = archive.infolist()
                    if len(entries) > 1024 or sum(e.file_size for e in entries) > 64*1024*1024 or any(e.file_size > 8*1024*1024 or e.file_size/max(e.compress_size, 1) > 100 for e in entries):
                        raise ValueError('ZIP_SCAN_LIMIT')
                    inspected.extend(archive.read(e) for e in entries)
            except (BadZipFile, RuntimeError, ValueError, EOFError, OSError):
                findings.append(SecretFinding(path=label, reason='ARCHIVE_SCAN_BLOCKED'))
        for reason, pattern in PATTERNS:
            if any(pattern.search(data) for data in inspected):
                findings.append(SecretFinding(path=label, reason=reason))
    return SecretScanReport(ok=not findings, findings=tuple(findings), checked_files=len(candidates))


def scan_staged(repository):
    """Read Git index blobs, including staged bytes differing from working files."""
    root = Path(repository).resolve(strict=True)
    args = ['git', '-C', str(root)]
    result = subprocess.run(args+['diff', '--cached', '--name-only', '--diff-filter=ACMR', '-z'], capture_output=True, check=True, timeout=30)
    candidates = {}
    for raw_name in result.stdout.split(b'\0'):
        if not raw_name:
            continue
        name = raw_name.decode('utf-8', errors='strict')
        if name.startswith(('/', '\\')) or '..' in name.split('/') or ':' in name:
            raise ValueError('INVALID_INDEX_PATH')
        blob = subprocess.run(args+['show', ':'+name], capture_output=True, check=True, timeout=30)
        candidates[name] = blob.stdout
    return scan_candidates(candidates)
