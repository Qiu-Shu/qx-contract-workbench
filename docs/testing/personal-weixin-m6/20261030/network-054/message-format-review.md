# Independent ordinary-message compatibility review

Date: 2026-10-30. Workspace: `D:/Documents/ChatGPT/律所项目`.
Fixed range: `b999455..0806545` (`0806545c22fa1a8eb631d5b143f690579371313d`).
Requirement source: `message-format-brief.md`. Reviewed the supplied commit/stat/U10 diff and implementation evidence; checked the named existing `_integer`, `_message_id`, and event-construction helpers to resolve exact-type/range/reference concerns. No wider repository review.

## Spec

**PASS — 0 actionable findings.**

- Optional `root_id` / `parent_id` pass through `_integer` before `_message_id`: exact Python integers only, with inclusive 0 through UINT64_MAX bounds. The decoded task event does not use these values for scope, task selection or reply references. Existing `ref_msg` remains authoritative.
- The shared `_item` gate permits each newly observed control field only when its exact type is `list` and it is empty. It applies to ordinary and directly quoted items. Other unknown message/item/quoted-item keys still reach the existing fail-closed `_keys` gate; no prior identity, group, deletion, completion or text/file check was removed.
- Added unit cases cover boundary and malformed metadata, empty controls, wrong-type/nonempty controls at both item locations, unknown keys and explicit-reference semantics. Existing-ingress runtime coverage checks translation into the fixed conversation, durable duplicate suppression and unchanged historical blocked receipts/descriptors, with automatic analysis both off and on.
- The supplied diff contains exactly four current-version substitutions to 0.5.4 across the three requested desktop metadata/test files. It contains no dependency, transport, frontend, installer or TLS change.

## Quality / Standards

**PASS — 0 actionable findings.**

- The production change is confined to the existing strict decoder, reuses the established validators and consolidates the empty-control rule in one helper. It adds no DTO, persistence shape, sender or queue.
- Exact type checks preserve bool/string/float rejection before uint64 canonicalization. Empty-control validation does not consume or execute controls. The existing event constructor and reference namespace are unchanged.
- The runtime test seeds a historical rejection through the actual ingress, restores the allowlist before current ingestion, and checks both immutable original rows and subsequent blocked replay links. Assertions distinguish collection-only behavior from fake model execution and do not claim that automatic-analysis off disables the existing canned response.
- The fixtures use fictional values and mocked HTTP/model boundaries. No actionable security regression, unrelated scope expansion or maintainability concern was found in this diff.

## Verification and limits

This reviewer inspected the saved RED/GREEN/regression evidence rather than rerunning suites. The recorded log tails show **3 expected RED failures**, **63 focused passes / 187 deselected**, **513 scoped regression passes**, and the metadata check's **three files / four approved replacements / unchanged dependency trees** result. The metadata checker itself compares the complete package/lock JSON and exact upgrade-test replacement against the fixed base. The broad regression preceded the final tests-only fixture/OFF refinements; the final 63-case focused run covers those refinements. Counts overlap and are not additive.

Read-only inspection commands exited 0. Only this review report was created; no product, index, Git, account, network or model operation was performed. The controller separately reports all five rebuilt frozen-module local/loopback probes passing; those probes were not rerun here.

Approval is for this scoped compatibility patch. Actual installed-phone message acceptance remains pending. Earlier TLS approval and broad M6 acceptance were outside this review.
