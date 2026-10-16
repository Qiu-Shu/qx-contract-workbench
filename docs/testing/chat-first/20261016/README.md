# Chat-first CH-00B first slice — actual evidence, 2026-10-16

Status: first slice verified for local commit. Full Python regression completed with 1,903 passed and 2 environment-dependent skips; the two skipped DuckDB cases then passed using the existing isolated runtime. All 1,905 distinct collected cases are covered without an unresolved failure. No new NSIS installer, deployment or installed-app replacement has been made for this slice. CH-01 and later chat/Jev/archive tasks have not been implemented yet.

## Source and authority

Baseline Q: `c0f9ae466344e5d585c04d6a9e3ff959a2b7b798`, branch `codex/contract-review-v2`. The user explicitly resumed unattended implementation during the v2.1 document review. The original Desktop v2.0 is unchanged (SHA256 `7e76dee9b5a53eb615b0184c082d376baadf2d29668984c753383fbff25fcfc5`). Revised v2.1 SHA256 is `2c11ec459232e666e0df7690826d62c106e4e457299b8613404aee2f621b6e1f`; the Desktop and repository copies match.

Scope: two static PDF imports are deferred to the existing PDF branches, and the fixed Electron builder keeps zh-CN, zh-TW and en-US resources. No parser limits, permissions, original-file rules, model policy, database schema or existing page behavior changed. All runtime checks use independently synthetic data in new ignored directories.

## Results actually obtained

| Check | Exit / observed result |
|---|---|
| New isolated-process tests + affected parsing/upload/reparse regression | 144 passed, no failures/errors/skips, exit 0, 75.59 s; includes 4 new tests |
| Existing Node desktop unit tests | 4 passed, exit 0 |
| New Python frozen backend | PyInstaller 6.22.3 build completed, exit 0; independent output directory |
| Same-backend Electron directory builds | All-language and selected-language builds each exit 0 |
| Packaged desktop synthetic workflow | 14 checks passed, exit 0; login, DOCX import, original anchors, workpaper Word download, restart and data retention |
| Language startup checks | zh-CN, zh-TW, en-US, fr-FR requested; all four setup windows usable; fr-FR resolved to zh-CN on this machine |
| Spec review | 0 findings within this slice |
| Standards review | 0 hard violations / suggestions within this slice |
| Full Python suite | 1,903 passed / 2 skipped, 0 failures/errors, exit 0; pytest 1,629.46 s (JUnit suite 1,629.266 s) |
| Isolated DuckDB supplement | The exact two skipped cases passed, exit 0, 1.58 s; synthetic inputs only |
| Schema/default/source/dependency development checks | All four exit 0; existing production-approval warnings remain |

The synthetic Word download was 40,815 bytes with SHA256 `7d340cfd01787bbe3682a0623f556d5dbd100a5fb91002defa3afff3a17e0037`. Original-page screenshot was visually inspected: Chinese text and original-anchor controls rendered normally. The existing script's 100/125/150% observations are application zoom, not Windows system DPI validation. No actual client document was processed.

The language check confirms actual launch and setup usability under those requested locales, not translation of every Chromium native string. The source Electron distribution still has all 55 locale files (50,643,459 bytes); only new output directories were filtered.

## Package comparison

See [package-comparison.json](package-comparison.json). Both builds use the same newly frozen backend and business source; exact inventories are retained under `.local/chat-first-20261016/packaging/inventories.json`.

- Before: 612 files, **482,252,029 bytes**.
- After: 560 files, **433,371,088 bytes**.
- Removed: 52 unused locale files, **48,880,941 bytes (46.62 MiB)**.
- Added or changed shared files: **0**. All **538 backend files** are byte-identical. Electron and Chromium licenses, ICU data and executable are retained.

These are unpacked distribution byte sums. They are not a measurement of compressed installer reduction, disk allocation or process memory. The earlier installed 0.4.1 has a different file inventory (including installer artifacts), so its total is not used as the exact A/B denominator. The candidate still reports 0.4.1 and is a private comparison build, not a newly released installer.

## Loading observation

Five fresh Python imports of `cn_contract.web.app` before and after, with OS caches not cleared:

| Metric | Before median | After median |
|---|---:|---:|
| Import time | 0.8270686 s | 0.7475610 s |
| Process working set | 88,494,080 B | 81,915,904 B |
| Windows PrivateUsage | 76,124,160 B | 68,636,672 B |

See [import-before.json](import-before.json), [import-after.json](import-after.json), [environment.json](environment.json), and [lazy-loading.md](lazy-loading.md). This is an import micro-observation, not Electron startup or whole-process-tree idle/peak memory. First PDF use still incurs its initialization cost. The PDF engine remains in the package; frozen DOCX was exercised, frozen PDF ingestion was not directly exercised through the desktop's currently DOCX-only material policy.

## Deviations and failures preserved

1. Initial new tests reported 4 failures: 3 valid eager-import failures and 1 test mistake comparing two different Pydantic model classes. That comparison was corrected to full field values. The mistaken failure is not counted as a valid feature RED. Raw logs/JUnit remain in `.local/chat-first-20261016/lazy-loading/`.
2. Initial direct Electron packaging failed (exit 1) because it omitted the existing project npm shim. Reusing the PATH setup from `scripts/build_desktop.ps1` made the build succeed; no new npm dependency or source workaround was introduced. Both logs are retained.
3. Windows exposes only a WSL bash launcher, not the Git Bash expected by SDD shell helpers. The same plan identity/progress contract is recorded using native files at `.superpowers/sdd/2026-10-16-chat-first-execution/`; no WSL installation or checkout recreation was performed.

## WorkBuddy collaboration

Current-session status and task `wb-1a1e417f75ab` completed successfully, with four scoped Read events covering package configuration, desktop README, fixed builder implementation and the boundary map. No shell, private-data read, model product call or external connector was requested by this task. WorkBuddy confirmed the exact locale field/matching logic and need to retain a fallback; this was independently checked against the installed builder and actual output inventory.

Two limits in its prose are corrected here: its package.json observation occurred before the field was added; and unlinking one ordinary hard link does **not** delete another pathname. We do not repeat its contrary hard-link warning. The unchanged source-distribution inventory and isolated output builds are the applicable evidence.

## Completed full regression — do not rerun unchanged source

Started 2026-10-16 23:01:24 Asia/Shanghai, exec session **11689**, launcher PID **2644**, Python worker PID **26228**. Command:

```powershell
.\.venv\Scripts\python.exe -X utf8 -m pytest -q --tb=short --junitxml=.local/chat-first-20261016/full-results.xml
```

Output is `.local/chat-first-20261016/full-tests.log`; session 11689 completed with exit 0. The two skipped cases were `tests.integration.test_library_pilot::test_pilot_readonly_mapping_or_explicit_mismatch[False/True]`, reason `explicit isolated DuckDB test runtime required`. The launcher and worker have exited. On 2026-10-17 local time, supplemented using the existing runtime:

```powershell
$env:QX_PILOT_PYTHON='D:/Documents/裁判文书数据库试点2025/.venv/Scripts/python.exe'
.\.venv\Scripts\python.exe -X utf8 -m pytest tests/integration/test_library_pilot.py -q --junitxml=.local/chat-first-20261016/pilot-results.xml
```

This supplement does not rerun the full suite or read the real pilot data: both cases create independent synthetic CSV/DuckDB fixtures. [Regression summary](regression-summary.json) records exact distinct-case reconciliation and log digests; original JUnit/logs are retained under `.local/chat-first-20261016/`. The four final development commands were `python -m cn_contract.cli schema --check`, `python scripts/verify_defaults.py`, `python scripts/verify_sources.py --mode development`, and `python scripts/verify_runtime_dependencies.py --mode development`, each using the project interpreter with `-X utf8` and exit 0. No production approval is implied.

Next: record the local commit, then implement CH-01 with ordered schema compatibility and backup constraints. Do not overwrite the active 0.4.1 installation or claim the chat-first application is already delivered.
