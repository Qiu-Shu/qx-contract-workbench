# CH-06B2a — Independent Spec review (final, after archive correction)

Baseline: `13f53bf986fb672834d2952c0276b52ea41b3d9c` → frozen working tree. Specifications: `docs/plans/2026-10-20-library-chat-execution.md` and B2 readiness. Review date: 2026-10-20.

**Open actionable findings: 0.** One confirmed P2 archive gap and one compatibility regression during its correction have been independently rechecked and closed. The earlier zero-findings conclusion was withdrawn after the archive probe; that history is retained in `spec-archive-review.md` and the original evidence.

The P2 concerned “恢复副本可读历史、不可执行”: invalid `research.accepted` identity previously passed qxbak creation/restoration, then made research history unreadable. A shared pure persisted validator now covers runtime and archive paths, including missing/renamed/isolated research markers. Valid old B1 histories remain separate and do not acquire execution authority. History classification uses the validator, not a raw marker substring from query text.

Independent evidence:

- Initial authorization/shutdown probes: **3 passed, 3.30s**.
- Original archive observation: **1 passed, 3.63s**, exit 0, proving the defect existed; this file remains unchanged.
- First-patch compatibility probe: **1 failed, 3 passed, 8.06s**, exit 1, retained as `spec-archive-fix-red.*`.
- Final correction: **4 passed, 8.46s**, exit 0, `spec-archive-fix-green.*`: call-ID and request-digest corruption rejected at creation/restoration; revoked session/newer draft/offline history remains restorable; legacy keyword text remains data. Restore validation was never bypassed.

Other reviewed boundaries remain intact: explicit local fixed query, no model/Jev execution, atomic trusted registration, no old-request adoption, same task admission/draining, current/historical authorization, read-only restore, unknown-request lookup without resend, scope epochs, literal-text source panel and keyboard focus, ordinary model permission unchanged.

Final inputs: **21 changed/new product hashes**, **4 fix hashes verified**, **13 frontend freeze hashes matched**, captured in `spec-final-inputs.json`. Reviewed the final CSS delta and browser evidence/screenshot, without presenting implementer browser runs as independent execution.

Not run by this reviewer: full suite, real library/models/network, live browser, installed/frozen package, physical IME or OS scaling. No product writes. This is slice-level Spec closure, not overall production acceptance.
