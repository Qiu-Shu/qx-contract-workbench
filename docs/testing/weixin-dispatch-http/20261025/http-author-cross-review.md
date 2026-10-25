# HTTP author cross-review of root service and DTO

Reviewer: `/root/dispatch_http`, 2026-10-25. This is a cross-author static review of root-owned service/DTO changes.

## Scope and exclusions

Reviewed `src/cn_contract/domain.py` (only the two new dispatch models), `src/cn_contract/weixin_inbox/conversation.py` (new fixed receipt and CID services), and `src/cn_contract/weixin_inbox/generation_dispatch.py` (private transaction helpers and preserved public wrappers). Existing transaction, current authority and receive helpers were read as dependencies.

I authored `src/cn_contract/web/weixin_authorization.py` and `tests/integration/test_weixin_generation_dispatch_routes.py`; those are explicitly excluded from independent approval. Root-owned `test_weixin_generation_dispatch_conversation.py` was read for test intent, but no additional tests were executed for this review. The root runner owns the final combined test result and SHA stability check; no cached results are called fresh validation.

## Findings

**0 actionable findings, 0 unresolved findings.**

### Final transaction binds CID to exact descriptor root

The CID current principal, owner, workspace, scope/ACL, and write revocation/fence are resolved within accounts._transaction. Private _dispatch/_find compare descriptor mapping.id to that resolved mapping.id before receipt publication. The transaction already holds BEGIN IMMEDIATE; no second public service transaction or cross-target reverse resolution is introduced.

Locations: `conversation.py:158-166`, `conversation.py:169-178`, `generation_dispatch.py:81-86`, `generation_dispatch.py:102-105`, `accounts.py:19-24`, `persistence.py:183-184`.

### Projection stays within rollback boundary

The exact fixed binding resolves conversation_id and validates the nine-field frozen view before leaving accounts._transaction. Any SELECT/model construction failure rolls back task event, cursor and receipt; commit occurs only after projection succeeds.

Locations: `conversation.py:148-166`, `conversation.py:176-178`, `persistence.py:199-207`.

### Read historical target under current ACL, never latest

_source active=False preserves actual principal/owner/workspace and root/fixed target current ACL using the immutable descriptor sidecar; it does not call latest/head resolution. Root unbound returns null. Unknown descriptor or foreign mapping is denied. Revocation/fence/archive block writes but need not erase readable existing acknowledgements.

Locations: `generation_dispatch.py:31-66`, `generation_dispatch.py:102-111`, `accounts.py:82-124`, `conversation.py:169-178`.

### Public Python API compatibility and original authority checks

Existing public signatures stay unchanged and retain one accounts._transaction. The extracted body retains _source, saved-receipt verification, exact saved target scope for new writes, per-(mapping,binding) earliest prefix, shared delivery, and post-write complete validation. The extra root_mapping_id argument is private, optional and only supplied by CID services; omitted public calls retain prior semantics.

Locations: `generation_dispatch.py:81-125`.

### DTO authority and privacy boundary

The input has only descriptor_id; inherited extra=forbid/frozen disallows caller authority fields. The output contains only mode/state/descriptor_id/conversation_id/task_event_id/cursors/UTC time/opaque full receipt digest. Unit cursor progression is validated. No account/bot/peer/session/source_event/payload/reason is projected.

Locations: `domain.py:77-78`, `domain.py:4869-4890`, `conversation.py:148-155`.

### No new execution or transport capability

The change still invokes TaskInbox receive_batch and the existing durable receipt. It does not freeze a draft, create an execution/model attempt, download/decrypt media, contact WeChat, or send a message. No DDL/migration change is part of the three reviewed files.

Locations: `generation_dispatch.py:81-99`, `dispatch.py:80-104`.

## Reviewed hashes

- `src/cn_contract/domain.py`: `f8f64176edbc9866887ade894680492769ae46b8ddd4bc3c6bc107632b89fe2e`
- `src/cn_contract/weixin_inbox/conversation.py`: `025fe5960dcfb967fdcf871d3589f068e10094717b6ac54ea09a11f538ca1c14`
- `src/cn_contract/weixin_inbox/generation_dispatch.py`: `a1f22dc3c7813f9a28a050acb46f3880ad9316ad3b98e83bb260e04a8f9df361`

## Limits

Static review does not establish a running real WeChat channel, real model or installed-build success. HTTP implementation and tests require another author's review. Long-process native crash and WIN-PATH-02 remain OPEN; product external capabilities remain closed.
