# Chat-first execution ledger and first delivery slice

User authority: on 2026-10-16 the user explicitly resumed unattended work, after confirming both code decoupling and installer/startup footprint are priorities. Enter sends; Shift+Enter adds a newline, with Chinese IME protection. The existing `codex/contract-review-v2` branch remains the integration branch. Do not resume real-material cloud transmission or treat this as deployment approval.

Specification: [chat-first-architecture-v2.1.md](chat-first-architecture-v2.1.md). Original design supplied by the user is preserved on their Desktop. The revised specification is a design baseline; execution evidence belongs here and in `docs/testing/chat-first/`.

## Global constraints

- Reuse existing authentication, immutable originals, versioning, parser checks and independent Chiheng environment. Business DTOs remain in `src/cn_contract/domain.py`.
- Development and ordinary CI use independent synthetic documents only. Do not touch the running installed application, real workspace, library import processes or existing MCP processes.
- Respect the user's explicit existing-branch preference. No extra checkout/environment or dependency installation is needed for this slice. Baseline HEAD: `c0f9ae466344e5d585c04d6a9e3ff959a2b7b798`.
- Code responsibilities, installation bytes, process import time, and real desktop startup are different measurements. No unmeasured performance claims.
- The app goal card was observed as paused; the current tool cannot resume that status. The user's new instruction authorizes work, and the existing hourly heartbeat has successfully been set ACTIVE with the new task order. Do not claim the goal card itself changed.

## Pre-flight interface checks

| Producer / consumer | Ruling |
|---|---|
| Ingest / PDF adapter | Keep the existing parse_pdf call signature and importable package; move import to the PDF branches, not a dynamic plugin loader. PyInstaller must still collect it. |
| Electron builder / packaged app | Use installed builder's supported electronLanguages configuration; keep Chinese simplified/traditional and en-US fallback. Keep licenses and all supported business capabilities. |
| Specification / existing repo rules | domain.py owns business DTOs; app.py only wires new modules. Existing feature branch takes precedence over generic worktree recommendations. |
| Benchmark / product claim | Import subprocess measurements do not represent full Electron startup. A locale-only package comparison must use identical backend inputs. |

### Task 1: Freeze the revised specification and baseline

Files: this plan, architecture specification, boundary map, sanitized baseline evidence.

Expected: original Desktop v2.0 unchanged; v2.1 has both independent review corrections; current Q/C revisions and active-process categories recorded without command-line secrets.

### Task 2: Defer PDF dependency loading

Files: `src/cn_contract/documents/ingest.py`, a focused isolated-process test file, synthetic local evidence.

Expected RED: importing core web/ingest or using DOCX prematurely loads PDF dependencies. Expected GREEN: DOCX works without loading them; first real synthetic PDF use still validates and parses through the existing adapter. Run affected parser/security regressions. Benchmark five fresh subprocess imports before/after; retain exact samples.

### Task 3: Reduce unused Electron language resources

Files: `desktop/package.json`, desktop documentation and comparison evidence.

Expected: the fixed builder accepts the declared language list, packaged output retains zh-CN, zh-TW and en-US, required licenses and all backend bytes. Build in a new ignored output directory, without replacing the active installation. Check actual packaged Chinese UI and a synthetic DOCX workflow; compare byte inventory with the baseline and distinguish installed from compressed sizes.

### Task 4: Review, regress, and record the slice

Run existing Node suite and applicable Python regressions, plus the full Python suite once after final code. Preserve actual failures and skips. Independent source review checks deferred-import semantics, freezing, language fallback, fixture-only scope and immutable-data rules. Commit only verified source/docs/tests; no generated package, private data or credentials.

## Plan-wide status

- CH-00: research baseline and v2.1 review complete; execution evidence being recorded.
- CH-00A: shared storage bootstrap and HTTP request guards extracted and verified in 00c12b7; broader business separation remains. Do not call all decoupling complete.
- CH-00B: first resource/loading slice verified; broader capability packaging and full-process measurements remain.
- CH-01: first four-table storage/service slice, fixed schema versions, native upgrade and legacy backup compatibility verified on 2026-10-17; HTTP/worker/streaming consumers remain. See the current execution entry below.
- CH-02 through CH-11: remain pending. Follow the specification's dependency order; do not redo old T00-T13 work or library imports.

## Review focus

No new model permission, no parser checks removed, no dependence on preloaded test modules, no optional dependency accidentally omitted by PyInstaller, no resources removed outside the supported build process, no performance numbers extrapolated to unseen hardware. The original desktop/backup/library paths must remain usable.

## Execution log

- 2026-10-16: resumed by explicit user message; hourly heartbeat update succeeded. Main branch and existing local environments reused. Two document reviewers identified five specification corrections, all incorporated before implementation. WorkBuddy status connected in this session; that status alone is not a completed review task.
- 2026-10-16: Tasks 2/3 implementation and targeted/frozen desktop checks obtained; exact results and full-suite process continuation are in [first-slice evidence](../testing/chat-first/20261016/README.md). Full regression pending, so Task 4 and local commit remain open. Current WorkBuddy scoped review completed; its hard-link unlink claim was rejected by independent review.
- 2026-10-17: Task 4 verification closed: full suite 1,903 passed / 2 isolated-runtime skips, then the exact 2 DuckDB cases passed in the existing runtime; 1,905 distinct cases covered. Schema/default/source/dependency development checks all exit 0. First-slice source has not changed since independent review and the completed full run; proceed with local commit and CH-01.
- 2026-10-17: 00c12b7 completed shared storage/request extraction, 167 distinct affected tests and 5 frozen checks. Current CH-01 storage slice then passed 293 targeted regressions and 8 actual frozen-backend checks, four development gates and independent Spec/Standards review. Four tables and five local services now preserve conversation input/scope/idempotency; queued runs do not execute. Known old archives validate before staging upgrades; restored runs are blocked. No new installer, homepage, model, attachments or real-data migration. Evidence: [CH-01 storage](../testing/chat-storage/20261017/README.md). Next: thin HTTP/runner boundaries, then homepage and pre-case attachments; do not treat the storage slice as complete CH-01 or product delivery.
