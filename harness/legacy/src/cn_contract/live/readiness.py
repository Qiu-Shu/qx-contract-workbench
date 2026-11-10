"""Read server bytes as diagnostics; no real evidence trust root grants GO."""
from datetime import datetime, timezone
import hashlib
from pathlib import Path, PureWindowsPath

from ..config import PROJECT_ROOT
from ..domain import ReadinessEvidence, ReadinessDecision, ReleaseConfig
from ..security import ServiceError
from ..ops.backup import checked_file
from ..ops.secrets import scan_candidates


def assess_go_live(evidence: ReadinessEvidence, *, database=None, actor=None, matter_id=None):
    evidence = ReadinessEvidence.model_validate_json(evidence.model_dump_json())
    reasons = {
        'real_evidence_trust': 'NOT_IMPLEMENTED',
        'legal_gold': 'PENDING_TWO_REAL_REVIEWERS',
        'license': 'SOURCE_RUNTIME_BUILD_PRODUCTION_APPROVAL_PENDING',
        'rules': 'REAL_LAW_AND_LAWYER_APPROVAL_PENDING',
        'provider': 'OFFICIAL_SCHEMA_ACCOUNT_PRICE_BILLS_ADAPTER_PENDING',
        'environment': 'CN_HOST_OS_TLS_DATA_POLICY_KEY_CUSTODY_PENDING',
        'capabilities': '84_CURRENT_CAPABILITIES_NOT_ESTABLISHED_GUARDS_ARE_SEPARATE',
        'shadow': 'NOT_RUN_REAL_COST_AND_LAWYER_MINUTES_UNKNOWN',
        'visual': 'HISTORICAL_WORD_UI_SCOPE_ONLY_CURRENT_NOT_RUN',
    }
    decision = 'BLOCKED'
    if database is not None or actor is not None or matter_id is not None:
        if database is None or actor is None or matter_id is None:
            raise ServiceError('AUTHORIZATION_REQUIRED', 401)
        from ..queries import ledger, storage
        with storage.factory_transaction(database, actor, matter_id) as db:
            storage.authorize_query(actor, matter_id, db, write=False)
            # A persisted billing incident survives later approval revocation;
            # missing budget evidence must never erase this hard veto.
            incident = storage.latest('incident', matter_id, db)
            if incident:
                decision = 'NO_GO'
                reasons['engineering_ledger'] = 'HARD_FAIL_BILLING_INCIDENT'
            try:
                state = ledger.read_budget(matter_id, actor, db=db)
            except ServiceError as error:
                if error.code not in {'BUDGET_UNAPPROVED', 'PLAN_EXPIRED'}: raise
                reasons['current_budget'] = 'BUDGET_APPROVAL_UNAVAILABLE'
            else:
                if state['incident']:
                    decision = 'NO_GO'
                    reasons['engineering_ledger'] = 'HARD_FAIL_BILLING_INCIDENT'
                elif not incident:
                    reasons['engineering_ledger'] = 'NO_INCIDENT_IN_THIS_AUTHORIZED_CASE_ONLY'
    hashes, currentness, counts = {}, {}, {}
    # These are fixed server files and the existing production gates, never
    # caller refs promoted into approval groups. No duplicated license logic.
    from ..ops.release import build_release_manifest
    try:
        release = build_release_manifest(ReleaseConfig(source_lock_ref='sources/upstream.lock.json',
            config_ref='config/defaults.json', rule_version_refs=(), test_evidence_refs=(), deployment_evidence_refs=()))
        hashes.update({'server/source_lock': release.source_lock_sha256, 'server/config': release.config_sha256})
        currentness.update({name: 'CURRENT_SERVER_BYTES_PRODUCTION_APPROVAL_PENDING' for name in hashes})
        counts = {'source': sum(b.startswith('SOURCE:') for b in release.blockers),
            'runtime': sum(b.startswith('RUNTIME:') for b in release.blockers), 'total': len(release.blockers)}
        reasons['server_release'] = 'CURRENT_FIXED_SERVER_GATES_READ_PRODUCTION_BLOCKED'
    except (OSError, ValueError, RuntimeError):
        reasons['server_release'] = 'CURRENT_FIXED_SERVER_GATES_UNAVAILABLE_BLOCKED'
    # Caller refs are never authorization records. Diagnostic hashes are
    # indexed by category/ordinal; unsafe names or file content are not echoed.
    for category in ReadinessEvidence.model_fields:
        refs = getattr(evidence, category)
        if not refs: reasons[category] = 'MISSING'
        for index, ref in enumerate(refs):
            label = f'{category}/{index}'
            try:
                if len(ref) > 4096 or any(ord(c) < 32 for c in ref): raise ValueError('UNSAFE_REF')
                # Reject UNC/URLs/ADS/outside lexical roots before resolve,
                # stat or open. Data cannot initiate a remote filesystem probe.
                win = PureWindowsPath(ref)
                if str(win.drive).startswith('\\\\') or ':' in ref[len(win.drive):]: raise ValueError('UNSAFE_REF')
                path = Path(ref)
                path = path if path.is_absolute() else PROJECT_ROOT/path
                if not path.absolute().is_relative_to(PROJECT_ROOT): raise ValueError('UNSAFE_REF')
                raw = checked_file(path, PROJECT_ROOT)
                if not scan_candidates({ref: raw}).ok:
                    raise ValueError('SECRET_CANDIDATE_BLOCKED')
                hashes[label] = hashlib.sha256(raw).hexdigest()
                currentness[label] = 'HASH_BOUND_ONLY_UNREGISTERED_UNAPPROVED_CURRENT_SCOPE_UNKNOWN'
            except (OSError, ValueError, RuntimeError):
                currentness[label] = 'UNAVAILABLE_OR_UNSAFE_NOT_AUTHORITY'
    return ReadinessDecision(decision=decision, reasons=reasons, evidence=None,
        evidence_hashes=hashes, evidence_currentness=currentness, server_gate_counts=counts,
        assessed_at=datetime.now(timezone.utc))
