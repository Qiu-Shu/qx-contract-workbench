# Fresh-context whole-change review — 2026-10-08

Baseline: ef17c5837720ed86d232a4ffa01d7947e6b0607c through current working tree, including untracked source/tests. Read-only source/index/HEAD; no child agents or real OCR runs. Source observed while parent continued documented final evidence and empty-region DTO handling.

## Strengths

- Backend independently validates current document/hash, permissions, policy, and persisted source integrity; distinct source_verification provenance does not manufacture PDF_SPAN anchors.
- Source records and candidate records are append-only, the source/fact mutation uses savepoints, and draft consumption re-enters current-source validation.
- Runtime asset and environment inventories fail closed, the native launch uses a fresh zero-capability AppContainer and a preconfigured Job Object, and cleanup includes suspended-process failure paths.
- Synthetic acceptance records correct, incorrect, blocked, and error denominators separately; component PNG evidence is not relabeled as PDF end-to-end evidence.

## Important findings

### R1 — OCR holds the entire database write lock during slow inference

Location: src/cn_contract/web/pdf_review.py:24–25; src/cn_contract/documents/ocr_candidates.py:68. The route runs OCR inside write()'s existing database session/savepoint. Database begins every session with BEGIN IMMEDIATE (persistence.py:180), so asset verification/rendering/inference hold the database-wide lock. The worker can run 60 seconds while SQLite waits only 15 seconds. Ordinary reads, logout, and membership revocation can therefore fail with database-is-locked while another page is recognized. This prevents timely authorization changes and makes unrelated work unusable.

Actual bounded reproduction: review/test_ocr_concurrency_probe.py substitutes a waiting worker only (no OCR), starts the HTTP OCR request, then attempts to revoke its member using a second database session. The member deletion failed after 16.41 seconds with database is locked. Command: .venv/Scripts/python.exe -m pytest -q -s -p no:cacheprovider .audit-local/ocr-proofreading-20261008/review/test_ocr_concurrency_probe.py --basetemp=.audit-local/ocr-proofreading-20261008/review/pytest-tmp. Exit 0, 1 reproduction assertion passed, 18.25 seconds. PYTHONDONTWRITEBYTECODE=1.

Fix: short preflight transaction, OCR without a database transaction, then a new atomic postflight transaction revalidating session/member/document/policy and writing the candidate and idempotency response. Preserve request identity through a server-owned value; do not trust stale Actor authorization.

Focused tests: block the worker on an event; prove a second connection can read another matter, revoke membership/logout, or replace the document while it waits. After release, revoked/superseded requests must fail without a candidate or reusable successful idempotency response. Test concurrent duplicate idempotency requests.

### R2 — Zero-origin CropBox still produces a false source highlight

Location: src/cn_contract/web/static/pdf-review.mjs:53–56. The guard treats page.view beginning at (0,0) as compatible with parser anchors, but a CropBox can start at (0,0) and have a smaller top edge than MediaBox. Anchors use top-origin MediaBox coordinates; subtracting their y from CropBox height shifts the highlight while the bounds guard still passes.

Actual reproduction: review/crop_probe.py creates a valid synthetic MediaBox 612x792 / CropBox [0,0,612,700] PDF. The parser gives bbox [72,182.484,236.688,194.484], while actual PDFium-rendered text begins at y=91 points. Current guard accepts and viewer formula draws at y=182.484, about 91.484 points below the text. Command: .venv/Scripts/python.exe .audit-local/ocr-proofreading-20261008/review/crop_probe.py. Exit 0. Artifacts: zero-origin-crop.pdf and crop-observation.json. No browser-render pass claimed.

Fix: verify the anchor coordinate frame against MediaBox and CropBox and transform correctly, or explicitly fall back to manual positioning whenever equivalence is unproven. Checking only lower-left crop coordinates is insufficient.

Focused tests: actual PDF with zero-origin shortened CropBox, nonzero-origin CropBox, rotations, and repeated text; compare highlight with rendered text or assert explicit no-highlight/manual fallback.

### R3 — Zoom/rotation silently drops the user's selected OCR source link

Location: src/cn_contract/web/static/pdf-review.mjs:134–137 (submission at172–173). Each render calls showProofreading(), which replaces the candidate select's children and inserts the empty manual-source option first. On the same document/page the rest of the form remains filled, including the page-check checkbox, but the selected OCR run disappears. A lawyer who selects an OCR candidate then zooms/rotates or locates a block can submit the same visible values with candidate_id/candidate_sha256 silently null. This discards the explicitly chosen OCR lineage from the immutable record.

Reproduction from source inspection: load a page with a candidate; choose it; fill source values; zoom, rotate, or locate a candidate; submit. The select has defaulted to the empty option while other fields persist. Actual browser reproduction was not performed because the parent's current client is blocked.

Fix: preserve selected candidate ID on same document/page when it is still present and valid; reset only when page/document changes or the selected record is no longer valid, making invalidation explicit.

Focused test: select a candidate, fill/check source form, zoom/rotate/locate, then verify submitted candidate ID and hash are unchanged. Also prove changing pages clears the link and stale/missing candidates cannot be retained.

## Minor

None separately raised.

## Declined to judge

- Production/legal approval and real-data readiness: explicitly outside this fictional engineering stage; no production claim.
- Real handwriting quality: acceptance handwriting uses vector strokes and explicitly makes no human-handwriting quality claim.
- Final source binding, Git byte closure, documentation status, full-suite results, and final PDF-rendered48 count: parent is actively completing them; known pending evidence was not treated as a newly discovered code bug.
- Complete current browser OCR/source-form/work-draft journey and real network observation: current browser client is blocked; previous limited viewer observation and static code review do not establish this journey.
- Full PDF decoder sandboxing before the OCR worker: existing parser/PDFium execution is a separately documented project limitation outside this worker-isolation increment; this review does not certify native PDF decoder containment.
- Upstream package legal sufficiency/security audit: checked runtime gating/declared scope, not an independent legal or full upstream code audit.

## Assessment

Ready to merge: No, pending R1–R3 fixes and the parent's planned final evidence closure. No Critical finding demonstrated. Three Important findings affect availability/authorization operations, source location accuracy, and source traceability. The rest of the reviewed boundaries show deliberate fail-closed and append-only design, but this is not production certification.
