SPEC verdict: ❌ Needs fixes — explicit readiness, clarification material continuity, crash recovery, and original-media completeness do not yet satisfy Task 2.

QUALITY verdict: ❌ Needs fixes — four confirmed important findings below. No critical finding; Task 3 frontend wiring is outside this review.

## Strengths

- The service connection and poll journal are additive in the existing database. Poll/cursor and source associations commit together, with stable duplicate identities and immutable media/poll/run records (`src/cn_contract/weixin_inbox/service_records.py:49`, `:102`; `service_schema.py:6`, `:50`). The implementation preserves the predecessor schema rather than broadening legacy fixed-chat records.
- Shared assistance actually invokes the configured Jev provider, separates the new four-question template from old hashes, and checks batch revision and authority before accepting late results (`src/cn_contract/assistant/shared_judge.py:48`, `:86`, `:95`; `providers/jev_codec.py:11`, `:78`). The authenticated desktop helper is present; native/frontend consumption is correctly deferred to Task 3.
- Original-source reply association and durable unknown claims are present (`src/cn_contract/weixin_inbox/service_runtime.py:188`; `service_records.py:113`). The inherited queued-worker authority fence remains in place (`personal_runtime.py:160`), and destination checks preserve an unsent composer (`service_runtime.py:305`, `:365`).
- The tests exercise actual attachment parsing, business records, model ledgers, predecessor-object preservation, and desktop archive restore. The >50 MiB database concern is addressed by the supported desktop archive path and is not a finding here (`tests/integration/test_weixin_service_runtime.py`, large-originals restore test).

## Important findings — must fix

### 1. [P1] Explicit readiness instructions are not authoritative

`src/cn_contract/weixin_inbox/service_routing.py:8` and `src/cn_contract/weixin_inbox/service_records.py:95` recognize only a narrow set of whole-message controls. A normal combined instruction such as **“新事项：请审查合同，先别开始、还没发完”**, followed by a file, is not held; it proceeds to Main. The synthetic probe completed a business/model run and recorded **one Main call** despite the explicit wait.

The reverse transition is also broken: `service_records.py:96` preserves `held` unless the legacy control returns `collecting`, while line 97 recognizes **“开始 / 开始处理 / 发送完毕 / 可以开始”** only for the deadline. Thus a held batch followed by “可以开始” remains `held` (probe: revision 5, zero Main calls). `service_runtime.py:274` similarly uses the legacy control to decide whether Jev may override explicit start.

Use one explicit-readiness interpretation for collection and judgment precedence. Clear negative/wait directives must prevent execution even inside a longer instruction and even if Jev suggests start; supported start/completion directives must release the hold and outrank auxiliary wait, while material-readiness checks remain enforced. Add focused cases for both directions.

### 2. [P2] Answering the offered “new matter” clarification strands the original batch

`src/cn_contract/weixin_inbox/service_routing.py:38` explicitly tells the user to answer “新事项” for new business. However, `src/cn_contract/weixin_inbox/service_records.py:76`–`:83` treats that answer as a new batch whenever the pending batch has text, including when it is awaiting clarification.

Synthetic sequence: complete two matters; submit “请审查这份合同” plus one file; receive ambiguity clarification; answer exactly “新事项”. The original two-event/file batch remains `clarify`, and the answer becomes a separate one-event `waiting` batch. No new review runs. The offered answer therefore cannot route the retained materials as promised.

Resolve a new-matter answer against the pending clarification before applying ordinary batch-splitting rules, preserving the original events/files and decision revision. Keep genuinely separate new-business messages distinct when they are not answers to a pending clarification.

### 3. [P2] A crash after material selection permanently blocks the batch

`src/cn_contract/weixin_inbox/service_runtime.py:424` commits `attachments.select_materials` before the business/link transaction at line 429. On retry it constructs the same `service-selection` request ID with the now-newer `expected_scope`. The unchanged selection implementation hashes the entire request and rejects that changed request under the previous ID (`src/cn_contract/assistant/attachments.py:312`–`:320`).

A focused fault injection called the real selection function, then raised immediately after its successful commit. Retrying normal `advance` left the batch `routed`, with **zero business links and zero Main calls**, and the version/authorization notice. The selection has already changed the scope, so subsequent attempts repeat the conflict; restart does not repair it.

Persist/reuse the accepted selection request or recover its existing receipt before resubmitting. Resume from the committed stage without repeating any unknown external operation. Add this exact commit-boundary recovery case.

### 4. [P2] Integrity validation accepts a missing persisted original

`src/cn_contract/weixin_inbox/service_records.py:154`–`:161` validates hashes of media rows that exist, but never checks that every media item declared by an immutable event has its required media row. An incomplete database can therefore retain a file-bearing event while losing its original bytes and still pass `validate_records`.

The synthetic probe ingested one file, temporarily removed the media-delete trigger in the isolated fixture, deleted the media row, recreated the exact original trigger SQL, and ran `validate_records`: it returned successfully with **media_count=0**. This models corrupted/restored contents with the expected schema, not an ordinary supported deletion path. Trigger presence alone does not validate historical content completeness.

Validate exact event/media coverage in addition to per-row hashes, and reject missing originals with the appropriate integrity error. The normal application-created archive test does not cover this corruption case.

## Focused checks and review boundaries

- Read the supplied full review package once in bounded chunks; one tool-output truncation was repaired by reading its missing middle span. No git commands, index/branch mutations, source edits, broad repository crawl, or suite reruns.
- Named cross-cutting checks: existing `_control` and draft inheritance for readiness/material continuity; existing `business.submit` for execution linkage; `attachments.select_materials` for selection retry semantics; inherited `_io` for queued authority checks. CodeGraph was used first. Its fixture lookup returned unrelated matches, so the specifically named synthetic fixture/setup helpers were read narrowly; `_io` was read narrowly because the graph excerpt cut it off mid-function.
- Two inline synthetic probe commands, both exit **0**, ran **five scenarios** using temporary independent workspaces and existing fake Main/MockTransport fixtures. Results: explicit start remains held; new-matter clarification splits/strands originals; missing media passes validation; committed selection fault cannot recover; explicit wait nevertheless executes once. No live network, real credentials, user profile, or real materials accessed. Temporary fixtures were removed; only this report is a retained output.
- Existing reported evidence remains separate: frozen targeted **110 passed**, backup/schema **3 passed**; prior **339 passed / 2 failed** is superseded only where recorded. Final broad regression was reported RUNNING at dispatch and is not claimed PASS by this review. Controller must obtain its final result after fixes.
- Suggested wider coverage only, not additional findings: completed-result restart with source-context redelivery, same-target composer edits at stage boundaries, and overlapping download/collector timing. These were not independently probed here.

## Assessment

Task quality: **Needs fixes**. The architecture and existing compatibility work are substantial, but explicit user controls, clarification continuity, and a durable commit-boundary recovery path currently fail concrete synthetic scenarios. The archive validator also needs to prove that declared originals actually remain present.
