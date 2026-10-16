# Chat-first module boundaries

Design baseline: [v2.1 specification](chat-first-architecture-v2.1.md), sections 6.4-6.6, 12.6-12.8. This map records intended interfaces, not completed modules.

| Owner | Responsibility | Dependency boundary |
|---|---|---|
| Electron | Windows and owned backend lifecycle | HTTP/local settings, not business SQL or provider secrets |
| web/app.py | Composition and existing route compatibility | Wires a new thin web/assistant.py; no new chat business engine here |
| assistant/service.py | Authenticated commands and short transactions | Accepts session/store/provider interfaces, not FastAPI Request |
| assistant/runner.py | Finite task states, budget, cancellation | Calls bounded tools/providers outside DB write transactions |
| assistant/attachments.py | Conversation-owned immutable intake and parse references | Reuses documents parsers; no fake matter or new parser copy |
| assistant/profiles.py | Sourced proposals and atomic intake projection | Current revisions and human field protection; no provider HTTP |
| assistant/outputs.py | Audience-specific versions and export | No mixed internal/customer payload or whole DOM export |
| assistant/providers | Remote format/transport and attempt receipts | No authority to confirm legal facts or bypass permissions |
| integrations/chiheng_adapter.py | Fixed protocol to independent C runtime | C owns atomic append receipt, Q owns current user authorization |
| domain.py | Business DTOs and pure validation | No IO or reverse import from Web/assistant |

Existing `intake/service.py -> web.services` coupling is known. New code should receive these application operations from the composition layer; only the shared business functions touched by implementation should move down to a non-Web application boundary. A whole-tree reorganization is not a prerequisite.

New frontend modules separate state, API/events, composer, messages and panels. They share one small same-origin client and established CSP; they do not add another framework, authentication system or conversation store.

First measured loading improvement: current `web.app -> documents.ingest -> pdf_adapter -> pdfplumber/pdfminer` is eager. Deferring the PDF import to the existing format branches preserves the API and lets DOCX-only work avoid those imports. It does not remove PDF from the package or demonstrate full desktop startup gains.

Packaging stays explicit. Full legal datasets, development environments and private workspaces remain outside the installer. Language selection is handled by the fixed upstream builder, not ad hoc deletion. OCR and Chiheng retain their existing isolation rather than being merged into the main Python process.
