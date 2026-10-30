# Windows 0.5.2 packaging independent review

Review date: 2026-10-30. Workspace: `D:/Documents/ChatGPT/律所项目`.

**Spec: PASS. Quality: Approved.** No actionable findings in this packaging change. This approval is limited to the frozen candidate packaging/install-review gate; it does not approve production, real Weixin/model use, or close existing native issues.

## Scope and method

- BASE `87526fe27c749030fc435750cb6f3e5a843a7eb9`; HEAD `e8284cf71f18dfde08d602ec9249f928125af4c8`. Independently confirmed HEAD is BASE's direct child and the index is empty.
- Read `package-brief.md`, `package-report.md`, and the supplied `review-87526fe..e8284cf.diff` once. Reviewed the six changed paths: `desktop/README.md`, `desktop/backend.spec`, `desktop/package-lock.json`, `desktop/package.json`, `desktop/tests/upgrade.cjs`, and `scripts/build_desktop.ps1`.
- Used the task's explicit narrow review instructions over the general code-review skill's additional agents/diff collection. No source/index/Git edits, extra agents, suite/build reruns, application launches, installation, or live calls. Only this review document was added.
- Evidence root: `.local/personal-weixin-m6/20261030-candidate-052/`. Read raw build/test exit records, relevant log results, manifests, resource validators, first-failure records, and supplemental UI harness/report. Root separately reviewed the packaged 15/10/7/7 acceptance reports and screenshot.

## Spec findings

None.

- Version is exact `0.5.2` in package metadata, both lockfile root entries, and the upgrade assertion. Dependency pins, publisher, business/runtime source and frontend remain unchanged. The reused `electronDist`/copy helper agrees with the existing local build approach. The extra nested Weixin-details click follows the adopted frontend and retains the business assertions.
- README distinguishes current candidate capabilities from historical 0.5.0 behavior and explicitly limits real-connection/production claims. No requirement to restore the old UI was introduced.
- The `backend.spec` enumeration excludes generated `__pycache__`, `.pyc`, and `.pyo` files while preserving relative target directories. Independently read and byte-compared **all 129 configured source assets** against the final unpacked backend: zero missing/different files. This includes the warm PNG, dual-mode frontend and personal-Weixin assets. The retained first failure names the two generated fixture caches; final inspection evidence reports zero banned paths.
- Independently rehashed historical originals against the prelaunch manifests: old-install fixture **49 files / 6,908,523 bytes**, historical model-output fixture **55 files / 9,429,580 bytes**, zero changes or extra files. Replay command uses only the clone; its model-credentials directory has **0 files**. Existing saved-output replay reports **0 model POSTs**. Supplemental packaged UI reports no external requests or model/Weixin-start POSTs.
- Independently verified **251/251** immutable `frontend-merge-baseline/manifest.json` backup blobs. From authoritative `restoration.json`, **193/193** nonowned restored WIP files remain byte-identical (197 restored minus four owned packaging paths). Original data and unrelated WIP were preserved.

## Quality findings

None.

- Build-r2 exit record is 0; its log builds version 0.5.2 using the local Electron distribution and existing Python build environment. Desktop log records **409 passed, 0 failed/cancelled/skipped/todo**. The four development-gate logs support their stated results; runtime still reports `native_build_verified=false`, and source production approvals remain warnings.
- Recorded actual packaged checks are 15 fresh acceptance, 10 upgrade, 7 historical-output replay, and 7 supplemental UI checks, all PASS. These are separate overlapping checks, not summed unique capabilities. First UI failure remains recorded; r2 opens the actual responsive menu before logout and retains bridge-revocation assertions. Its 1424/374 pixel measured content widths are distinguished from requested outer widths and the test-only minimum-window override.
- ASAR evidence checks the explicit 26-file allowlist, 25 runtime files byte-equal to source, and six sanitized package fields including 0.5.2. Python archive evidence identifies the five required M6/qrcode modules. Independently confirmed the final three locales are exactly `en-US.pak`, `zh-CN.pak`, and `zh-TW.pak`.
- Source-input manifest has **737 files**, SHA256 `86f0dc9550789f7471ac70b73e576c85f91f476ef5bcdaaec061812ca602f58b`. Independently rehashed every current input: all sizes/hashes match. Compared each named input with the frozen HEAD blob: 734 byte-identical and three differing only in CRLF/LF; no missing or semantic content differences. This ties the manifest to the reviewed frozen source rather than unrelated working changes.

## Independently verified final artifacts

Every byte count and SHA256 below matches `artifact-manifest.json` and `package-report.md`.

| Artifact | Bytes | SHA256 |
|---|---:|---|
| `dist/desktop/Qunxing-Workbench-0.5.2-Setup.exe` | 148630065 | `5d7063885777b3ee6369ef5f2e1037c7e35979268a147bebd658360679a0662e` |
| `dist/desktop/Qunxing-Workbench-0.5.2-Setup.exe.blockmap` | 155127 | `e9f0df9aa2649d9a516b83fc41e89a30c0b3db399c957db187053af43fd6fcf2` |
| `dist/desktop/win-unpacked/群兴法律工作台验证版.exe` | 247033856 | `f4341c9cb5f3bb8169fc537682bfd7254ce3f9d19a726c123f776888584a3a53` |
| `dist/desktop/win-unpacked/resources/app.asar` | 174022 | `d823960bf09c9e47a684ba834f494318d3ea668e4bab103d89b7bafe04e24c33` |
| `dist/desktop/win-unpacked/resources/backend/qx-backend.exe` | 16543909 | `08bc7b34243806d815e739e1b67ad981bf67bead083f934f041864b1bf1a08cb` |

Also independently confirmed the old 0.5.1 installer remains SHA256 `bc380a2273b7f41c5e5b08d3910316b6d5bc82879a22fb4e4ee3dfd4ff0b87c3`, and the existing installed 0.5.1 ASAR remains SHA256 `ac91453a2548aeed801bab7a9375b81f94d70f6e2078fb4d93eb74cd5e1a6de9`.

All independent read-only probes completed with exit 0: source/HEAD/artifact provenance; historical originals/129 assets/locales; backup/WIP preservation; signature and saved-result inspection. No test/build result was regenerated or overwritten.

## Limits and installation handoff

This review clears the independent packaging review gate for **these exact artifact hashes**. Root still owns the actual installer/default-profile acceptance and any live scan; neither was performed by this reviewer. Hash/source/packaged-offline evidence does not prove NSIS installation behavior, external Weixin protocol, current provider availability, or legal output quality.

Independently checked final installer and executable signatures: both **NotSigned**. Existing `WIN-PATH-02`, native AV, second-machine/nonAdministrator, production/source approval and global `native_build_verified` gates remain open. These are accurately disclosed existing limits; no new packaging regression was established. No broad Python rerun or live/native reproduction was performed.
