# CH-01 assistant storage implementation

Workspace: `D:\Documents\ChatGPT\律所项目`. Baseline supplied by root: `00c12b780a08db26da4937859837fd53b045af46`. Synthetic tests only; no provider calls, private materials, network calls, commit or push.

## Delivered scope

- `assistant/schema.py`: fixed `assistant-v1`, four tables, three explicit indexes, seven immutable triggers. Exports `STATEMENTS`, `expected_objects()` and `initialize_storage(database)`. No assistant ORM registration or initialized flag. Schema SHA256 `0979aeba4fce1d1aff0772ebb9e4e57437f14e85ce3e9df3d903f9a08e1ec26e`.
- Business DTOs are only in `domain.py`; strict revisions, UUIDs, unknown-field rejection, immutable views, bounded text and approved skill vocabulary. `ScopeSnapshot` retains the seven approved fields. `ErrorCode.ASSISTANT_BUSY` added for a second unfinished run.
- Commands use caller-owned short SQLite transactions. They recheck current session, current roles, owner, server native workspace identity, current intake owner/current converted matter and optional projected intake. Lawyer roles only in this slice; assistant/admin conversation actions are not provided. Admin ownership does not imply matter access.
- Every write checks `ops.storage.require_active`. Restored current authorized reads remain possible. History is immutable in SQLite, not just hidden from the UI.
- Original user text is preserved, including whitespace. Draft writes only advance composer revision. Sending advances input and composer revisions and clears the matching draft. Editing the next draft does not change a queued run snapshot.
- Same conversation/request key and identical content reuse one message/run; changed content conflicts. SQLite serialization plus the active-run unique index prevents parallel second runs. A competing different key explicitly returns `ASSISTANT_BUSY` even if the first send advanced the input revision.
- Empty attachment selection only; nonempty IDs fail `NOT_SUPPORTED`/422 until CH-03. A saved run is `queued`, with no selected provider/model, no assigned budget and no invented response.

## Callable contract

`actor` is the existing `domain.Actor`. `db` is an existing `Database.session()` SQLAlchemy session; none of these functions commits or performs external work.

```python
create_conversation(actor, request: AssistantConversationCreateInput, db) -> AssistantConversationView
read_conversation(actor, identifier: UUID, db) -> AssistantConversationView
save_draft(actor, identifier: UUID, request: AssistantDraftInput, db) -> AssistantConversationView
save_message(actor, identifier: UUID, request: AssistantMessageInput, db) -> AssistantRunView
get_run(actor, identifier: UUID, db) -> AssistantRunView
quarantine_runs(db) -> int
```

Creation input: `request_id`, optional `display_title`, `scope_kind` (`conversation`, `intake`, `matter`) and `scope_ref` (null only for conversation). Workspace/owner cannot be supplied by callers. Native `local_workspace_identity` must already exist with exactly one valid UUID; this service never creates or guesses it.

Draft input: `expected_scope` (complete seven-field snapshot), `expected_composer_revision`, `content`. Message input additionally includes `request_id`, optional `requested_skill` and `attachment_ids=()`. Message body cannot be whitespace-only. Text is at most 20,000 characters. Passing an unchecked Pydantic `model_copy` does not bypass revalidation.

Conversation view contains `.scope.conversation_id`, `.scope` revisions, `.composer_revision`, `.draft_input`, timestamps and immutable message records. The run snapshot has the newly accepted input revision; its SHA256 binds actor, actual server workspace, conversation and full request, including expected scope/versions/content/skill.

`quarantine_runs` is an internal trusted restore operation. Call it only inside the already verified and upgraded staging database transaction, before committing the restore. It deliberately fails on a missing assistant schema. It changes queued/preparing/routing/retrieving/generating/persisting/awaiting_input runs to `blocked`, appends `restore.quarantined` at `MAX(seq)+1`, preserves input history, returns the changed count, and is repeat-safe. It does not require an already written restore fence because the caller may add that fence later in the same transaction. It is not a user/HTTP operation.

## Actual checks

1. Initial existence RED: 1 assertion failure because no assistant package existed. The shell wrapper ended after printing the log, so its outer exit was 0; the pytest failure is recorded in `storage-red.xml` and `storage-red.log`.
2. Full behavior suite before service implementation: 10 DTO tests passed, 34 fixture errors because `assistant.service` did not exist; exit 1 (`storage-behavior-red.*`). These are missing-implementation errors, not 34 proven business failures.
3. First service GREEN: 44 passed, 16.68 seconds, exit 0 (`storage-green.*`).
4. Expanded assistant plus existing domain regression: 160 passed, 19.30 seconds, exit 0 (`storage-targeted.*`).
5. Tightened competing-send contract produced one actual behavior RED: expected busy but got stale-version conflict, 1 failed, 1.26 seconds, exit 1 (`storage-busy-red.*`). After current authorization/idempotency, busy now precedes input-version conflict; no permission check is skipped.
6. Final same focused command: **160 passed, 21.05 seconds, exit 0**; 49 assistant cases plus 111 existing domain cases, no skips/errors/failures (`storage-final.xml`, `storage-final.log`).

```powershell
.\.venv\Scripts\python.exe -X utf8 -m pytest tests/integration/test_assistant_storage.py tests/unit/test_domain.py -q --junitxml=.local/chat-storage-20261017/storage-final.xml
```

7. Isolated `python -I` imported `cn_contract.assistant.service` and asserted no module beginning `cn_contract.web` was loaded: exit 0. No Web/intake service imports were introduced.
8. `git diff --check` on owned changes: exit 0.

Final source hashes: service `9612e314cf0cf0d03b12f4a85b2b21bf7dafd481a0e297b4b40859062f48e524`; domain `ba50ccd5db50a2b2cbcab59e81aec6e5592f9da0030723ffc22fc44352c0d26c`; assistant test `7bfa0e9f257a49b203122acc88d3319281fcecdf831e1b7b6b234b85ea0fe3a1`.

## Remaining / limits

Root and migration agent own bootstrap, upgrade, restore compatibility and overall integration. No HTTP routes, homepage, streaming, model executor, attachment reader, automatic profile writer or cloud service is implemented here. Reads currently return this conversation's complete history; paginated UI transport is a later consumer concern. Future CH-04 commits must recheck then-current intake version/conversion state and extend its input snapshot explicitly; the current seven-field snapshot does not claim to freeze the intake record. No full suite, packaged build or independent review was run by this subagent.
