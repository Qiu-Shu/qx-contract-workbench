# Independent bounded OCR rendering review

Reviewed 2026-10-09 (Asia/Shanghai), against BASE `e8756cef30d4c2b94e686271ae006ec7f7eecd96`, current uncommitted work. Read-only review; no OCR worker launched, no dependency/cache/asset/product changes, no external calls. This report is the sole reviewer-created file.

## Findings

- Critical: none identified.
- Important: none identified in the reviewed production change.
- Minor: `tests/unit/test_ocr_page_rendering.py:72`–`:87`: the real rotated-page test renders a blank page and its final mapping assertions are algebraic round trips (`bw*(w/bw)==w`). It does not assert an expected rotated page size or verify a visible feature's location, so an orientation/offset regression could evade this test. Consider retaining a small synthetic CropBox/colored-rectangle test in the suite. This is a regression-coverage improvement, not an observed production defect: the independent concrete-coordinate probe below passed all four rotations exactly.

## Evidence and reasoning

1. `ocr_candidates.py:45`–`:55`: finite positive dimensions are required; the 4096-point early side guard follows directly from the existing scale-2 longest-side limit of 8192. Finite huge inputs therefore fail before multiplication, and no previously accepted scale-2 page is excluded by that guard. Each attempted scale checks both ceil-rounded sides and pixel product before `render`. Scale 4 is preferred only within the unchanged cap; otherwise scale 2 uses exactly the old acceptance condition.
2. Independently ran `.venv/Scripts/python.exe -m pytest tests/unit/test_ocr_page_rendering.py -q --tb=short`: exit 0, **19 passed in 0.64s**. Confirmed previously recorded render RED and huge-dimension RED receipts have exit 1; did not overwrite or rerun their historical state.
3. Independently ran an in-memory synthetic PDF geometry probe via `.venv/Scripts/python.exe -`: exit 0, **4/4 probes passed**, no model import/prediction. MediaBox `[0,0,160.25,120.5]`, nonzero CropBox `[20,15,140.25,95.5]`, native rotations 0/90/180/270, visible red rectangle `[40,35,70,55]`. At rotation 0/180 bitmap dimensions were 481x322 and source dimensions 120.25x80.5; at 90/270 these swapped. Observed raster bounds transformed with actual `w/bw,h/bh` were exactly the expected page bounds: 0=`(20,40.5,50,60.5)`, 90=`(20,20,40,50)`, 180=`(70.25,20,100.25,40)`, 270=`(40.5,70.25,60.5,100.25)`.
4. `predict_page`, `decode_output`, DTO validators, and `ocrViewportPolygon` all use actual returned bitmap/page dimensions rather than a hardcoded scale. Parent's concurrent integration-stub update at `tests/integration/test_pdf_proofreading.py:214` correctly removes a stale `.5` transform; the revocation/database assertions remain unchanged. Reviewed this final one-line behavior adjustment to the stub.
5. Independently compared fixture PDF, manifest, asset lock, and worker source bytes to BASE: **4/4 unchanged**. PDF SHA-256 `017866f3c56b2fad241fc048e6440e30314db41bef53391eabd7bc706117ae9b`; manifest `324b06d8b242dd3e702a83eae4cd71d48da3c8358f5f5235c0c92c9e1d1df25a`; asset lock `f64178ccbd67fc75c6757ff0185fb6d672b97c17028fb26218a049a73105a73b`; worker `a2294afa2220e59ffedf9ee5b863988416ea55aa21a27a6491bf9e4fbaf428a2`.
6. Inspected `run_fixed_48.py`: fixed original hash asserted, pages 1–48 asserted, original rendered through product `page_bitmap`; expected strings are consulted after returned OCR output for scoring, never supplied to the worker or used to rewrite text. Output creation uses a fresh directory, per-page errors/blocks are retained, and final original/manifest byte equality is asserted. Same-set development scope is explicit.
7. At inspection time only six fixed-run result files existed. Independently checked all **18/18 blocks remain `unverified`**, including confidence up to `0.9992027878761292`. DTO/decoder changes are absent; confidence does not grant confirmation.
8. Source binding already inventories `src/cn_contract/documents/ocr_candidates.py` and `ocr_process.py`. Updating binding hashes after all edits and verifying the controlled entry remains a required parent closeout action; the acknowledged in-progress stale hash is not presented here as a final defect.

## Declined to judge / outstanding parent receipts

- Final 48-page accuracy, per-category counts, timing, and quality gate: full sequential run was still in progress. Six result files do not establish a 48-page conclusion. No duplicate OCR run launched.
- Final related-suite rerun after stub repair, source-binding regeneration/entry checks, byte-preserving commit verification, documentation totals, and final memory record: pending parent completion, not claimed passed by this review.
- Browser visual/interaction behavior, general OCR accuracy, unseen/real contracts, legal correctness, Word layout, real remote models/QCC, production isolation/readiness: outside this bounded change and not newly validated.
- Increased-resolution resource use is still bounded by the existing limits; this review does not claim universal per-page throughput or absence of timeout on arbitrary complex PDFs.

Conclusion: no blocker found in the production rendering fix. Keep the minor durable-test improvement and the explicit outstanding receipts separate from claims of completed quality or production validation.
