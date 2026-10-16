# CH-00A shared boundaries before chat storage

Base: `7b58b92865f0370687427d987fbc8fa42a96c205`. This is an incremental prerequisite to CH-01 in the approved [v2.1 specification](chat-first-architecture-v2.1.md), not a replacement plan. The first loading/locale slice has been committed after all 1,905 distinct Python cases, targeted desktop checks and independent review.

The current application module owns HTTP request guards and all storage initialization. Other routes and backup verification import that application to reuse these functions. Move those existing responsibilities to explicit shared modules without changing their behavior. Avoid a new dependency injection framework or plugin registry.

## Scope and ownership

- Root: move the existing complete storage initializer to `storage_bootstrap.py`; update non-HTTP consumers and server startup imports, preserve the old application import as a compatibility alias. Verify the existing exact schema is unchanged and backup schema calculation no longer imports the HTTP application.
- Request-boundary subagent: move same-origin, authenticated actor and bounded strict-JSON functions from the application to a shared Web module; migrate route consumers while keeping old import aliases. Preserve checks and limits exactly, verify existing API security and an isolated-import test.
- Migration design reviewer: read-only audit of CH-01 ordered upgrades and old backup compatibility. Do not add assistant tables until the supported-schema/reference and restore paths are ready together. Preserve both existing schema-hash algorithms.

## Verification and stopping point

Use isolated subprocess tests to observe imports and actual schema/trigger output. Run the existing upgrade, backup, security and route regressions affected by the moved functions. No real workspace upgrade, model request, library import or installed-app replacement. Independent review is required before local commit. Existing source/default checks and the prior full result remain evidence for their exact source revision; do not attribute them to later source changes.

CH-01 remains open after this extraction. Its next change must add ordered known-schema upgrades and preserve valid old `.qxbak` restoration, followed by conversation data and authorization. An unchanged-schema extraction must not pretend to provide those new capabilities.

## Execution result

Shared modules extracted and compatibility aliases retained. Targeted suites passed 69 and 99 cases (167 distinct); exact raw and normalized schemas match the baseline. A newly frozen backend passed five synthetic protocol groups including restart, backup and quarantined restore. Independent Spec and Standards reviews found no issues. Development checks passed; full-suite and Electron installer acceptance were not repeated for this extraction. See [actual evidence](../testing/chat-first/20261017/README.md).
