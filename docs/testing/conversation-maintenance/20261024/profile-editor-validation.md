# Profile manual maintenance validation — 2026-10-24

All fixtures and browser data were synthetic. No production workspace was opened. No model was invoked.

## Focused checks

- `node --test scripts/test_assistant_profile_panel.mjs scripts/test_assistant_profile_generation.mjs scripts/test_assistant_transport_input.mjs scripts/test_assistant_generation_entry.mjs`: exit 0, 99 passed (34 profile panel tests).
- `TMPDIR=/private/tmp /tmp/qx-audit-20261024-venv/bin/python -m pytest -q tests/integration/test_assistant_profile_routes.py tests/integration/test_assistant_profile_store.py tests/integration/test_assistant_profile_history.py tests/unit/test_assistant_profiles.py --basetemp=/private/tmp/qx-profile-focused-final-20261024`: exit 0, 135 passed.
- Scoped `git diff --check`: exit 0.
- Initial UI tests: 7 new cases failed because editing controls did not exist; implementation made them pass. Initial HTTP checks exposed two rejected null payloads; corrected null serialization to the existing required `{kind: "null", value: null}` contract and reran successfully.

## Actual browser flow

Headed Chromium via Playwright CLI against an isolated server at `127.0.0.1:18768`, workspace `/private/tmp/qx-profile-ui-ksig3jk3/workspaces/main`:

1. Logged in as synthetic lawyer, saved a synthetic conversation draft, opened an empty profile.
2. Opened manual maintenance, chose contact, entered synthetic contact text, saved once. Real backend returned receipt; saved protected contact rendered.
3. Opened maintenance again, explicitly cleared contact, saved once. Protected null rendered as lawyer-cleared.
4. Read revision 1: previous protected contact remained visible and editor was absent.
5. Inspected desktop editing screenshot and 390×844 mobile cleared-profile screenshot. Text and controls fit the side panel; no horizontal clipping observed.
6. Browser closed and synthetic server stopped. Database readback: 2 profile revisions, 2 receipts, 0 model attempts.

Screenshots:

- [Contact editor](profile-edit-contact-20261024.png)
- [Saved protected contact](profile-saved-contact-20261024.png)
- [Protected clear on mobile](profile-cleared-mobile-20261024.png)

One console error was the existing `/favicon.ico` 404. No application error was observed. Two CLI reference-selection mistakes were corrected from fresh snapshots; neither changed application state.

## Behavior covered

Current-only editing; historical/recovery/archived views do not expose editors. All 12 supported fields, material status rows, exact string money, local datetime converted to UTC, contact, explicit protected null. Fresh conversation scope and intake baseline captured; profile revision uses the displayed current snapshot. Manual save uses the existing commit route with no proposals and `project_intake=false`; it leaves reception registration unchanged. Later automatic proposals retain manual protected values, including clear. Version conflicts reread current state; unknown writes query the original receipt and never repeat the POST. Unknown request recovery is retained within the page session, including panel close/reopen and conversation switches; no new browser storage was introduced.
