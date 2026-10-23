# Chat-first execution ledger and first delivery slice

- 2026-10-23 CH-07C2b1：自动建档的存储前置切片完成。新命名schema及固定保存回执保留旧11版44摘要，三迁移通道与五族旧完整性校验接续；新格式/新回执仍fail-closed，未启用自动归档。20文件初轮630/632通过，2项旧测试预期修正后两个文件54通过；四开发门通过，542份输入稳定、产品源码未变，Spec6/Standards30独立通过。修复新摘要CHECK的NUL尾缀漏洞。安装版0.4.1和WIN-PATH-02开放项不变；未碰真实资料/模型/云。 [Evidence](../testing/profile-model-schema/20261023/README.md)。

- 2026-10-23 CH-07C2a: offline send basis binds exact C1 wire/config/template and separate local profile/intake save plan. Actual saved run/message views bridge request identity and scope/composer revisions. 380 related tests (54 new), four gates, 538 stable inputs; independent Spec12/Standards9 pass. No new runtime authorization, schema, ledger, archive hook or UI. C2b must close these together before activation; WIN-PATH-02 remains open. [Evidence](../testing/profile-basis/20261023/README.md).

- 2026-10-23 CH-07C1: explicit current-text answer/profile proposal codec and lazy provider entry completed; 577 related tests, four development gates, 535 stable inputs. Independent Spec13 / Standards8+4 passed after fixing numeric-date coercion and money wire types. Old wire behavior preserved. No registry, purpose grant, save hook, GUI or automatic archive activation; C2/C3 remain. [Evidence](../testing/profile-output/20261023/README.md).
- 2026-10-23 CH-07B: implemented atomic profile/intake/receipt persistence, historical reads, response-only consultation provenance and additive schema/recovery. Focused and independent reviews passed. Full Python run: 3816 passed / 3 failed, 532 stable inputs; all four development gates passed. Two stale fixtures corrected (9/36 focused tests pass); long-path restore publication WinError5 remains unresolved, so overall acceptance stays open. No speculative permission/retry changes. CH-07C model hook and archive panel remain next. [Evidence and limitations](../testing/profile-persistence/20261023/README.md).

- 2026-10-23 CH-07B1: server-owned source reconstruction completed on baseline 0eb341a; bounded referenced user messages and selected parse versions, original integrity outside DB transactions, fresh authorization/scope/restore checks before returning. 186 related tests (40 new), four development gates, 524 stable inputs; independent Spec7/Standards8 passed. Duplicate selected IDs now fail closed after a reproduced review finding. Success has no business writes; existing denial audits remain. This is a persistence prerequisite, not automatic archiving. CH-07B still requires atomic profile/intake/receipt/event writes plus migration/recovery together. [Evidence](../testing/profile-sources/20261023/README.md).

- 2026-10-23 CH-07A: pure profile merge/provenance/manual protection and IntakeDraft projection completed. 400 focused/related tests (45 new), four development gates, stable 522 inputs; independent Spec 6 / Standards 9 passed after four findings fixed. Exact source matching is not authorization or factual verification. Model contact values rejected; trusted manual input only in this slice. No new tables, model calls, HTTP/UI, installer or resource claims. Next CH-07B closes profile/intake/receipt/event atomic persistence with migration and recovery; then CH-07C structured model output. [Evidence](../testing/profile-merge/20261023/README.md).

User authority: on 2026-10-16 the user explicitly resumed unattended work, after confirming both code decoupling and installer/startup footprint are priorities. Enter sends; Shift+Enter adds a newline, with Chinese IME protection. The existing `codex/contract-review-v2` branch remains the integration branch. Do not resume real-material cloud transmission or treat this as deployment approval.

Specification: [chat-first-architecture-v2.1.md](chat-first-architecture-v2.1.md). Original design supplied by the user is preserved on their Desktop. The revised specification is a design baseline; execution evidence belongs here and in `docs/testing/chat-first/`.

## Global constraints

- Reuse existing authentication, immutable originals, versioning, parser checks and independent Chiheng environment. Business DTOs remain in `src/cn_contract/domain.py`.
- Development and ordinary CI use independent synthetic documents only. Do not touch the running installed application, real workspace, library import processes or existing MCP processes.
- Respect the user's explicit existing-branch preference. No extra checkout/environment or dependency installation is needed for this slice. Baseline HEAD: `c0f9ae466344e5d585c04d6a9e3ff959a2b7b798`.
- Code responsibilities, installation bytes, process import time, and real desktop startup are different measurements. No unmeasured performance claims.
- The app goal card was observed as paused; the current tool cannot resume that status. The user's new instruction authorizes work, and the existing hourly heartbeat has successfully been set ACTIVE with the new task order. Do not claim the goal card itself changed.

## Pre-flight interface checks

| Producer / consumer | Ruling |
|---|---|
| Ingest / PDF adapter | Keep the existing parse_pdf call signature and importable package; move import to the PDF branches, not a dynamic plugin loader. PyInstaller must still collect it. |
| Electron builder / packaged app | Use installed builder's supported electronLanguages configuration; keep Chinese simplified/traditional and en-US fallback. Keep licenses and all supported business capabilities. |
| Specification / existing repo rules | domain.py owns business DTOs; app.py only wires new modules. Existing feature branch takes precedence over generic worktree recommendations. |
| Benchmark / product claim | Import subprocess measurements do not represent full Electron startup. A locale-only package comparison must use identical backend inputs. |

### Task 1: Freeze the revised specification and baseline

Files: this plan, architecture specification, boundary map, sanitized baseline evidence.

Expected: original Desktop v2.0 unchanged; v2.1 has both independent review corrections; current Q/C revisions and active-process categories recorded without command-line secrets.

### Task 2: Defer PDF dependency loading

Files: `src/cn_contract/documents/ingest.py`, a focused isolated-process test file, synthetic local evidence.

Expected RED: importing core web/ingest or using DOCX prematurely loads PDF dependencies. Expected GREEN: DOCX works without loading them; first real synthetic PDF use still validates and parses through the existing adapter. Run affected parser/security regressions. Benchmark five fresh subprocess imports before/after; retain exact samples.

### Task 3: Reduce unused Electron language resources

Files: `desktop/package.json`, desktop documentation and comparison evidence.

Expected: the fixed builder accepts the declared language list, packaged output retains zh-CN, zh-TW and en-US, required licenses and all backend bytes. Build in a new ignored output directory, without replacing the active installation. Check actual packaged Chinese UI and a synthetic DOCX workflow; compare byte inventory with the baseline and distinguish installed from compressed sizes.

### Task 4: Review, regress, and record the slice

Run existing Node suite and applicable Python regressions, plus the full Python suite once after final code. Preserve actual failures and skips. Independent source review checks deferred-import semantics, freezing, language fallback, fixture-only scope and immutable-data rules. Commit only verified source/docs/tests; no generated package, private data or credentials.

## Plan-wide status

- CH-00: research baseline and v2.1 review complete; execution evidence being recorded.
- CH-00A: shared storage bootstrap and HTTP request guards extracted and verified in 00c12b7; broader business separation remains. Do not call all decoupling complete.
- CH-00B: first resource/loading slice verified; broader capability packaging and full-process measurements remain.
- CH-01: first four-table storage/service slice, fixed schema versions, native upgrade and legacy backup compatibility verified on 2026-10-17. HTTP/list/cancel/event reads now passed targeted/frozen checks and the final full suite: 2,042 distinct tests, no failures/errors/skips. Worker/model execution and frontend consumers remain. See the current execution entry below.
- CH-02: local-draft homepage implemented, independently reviewed and verified by the final 2,094-test full regression. Generation, attachments and profile panels remain later integration work.
- CH-03A: conversation-owned DOCX intake, immutable source/parse/snapshot records, source panel and native qxbak recovery verified. Final single full regression: 2,171 passed, no failures/errors/skips, exit0, 1,814.65s; 426 input files unchanged and collection/JUnit identities match. Browser11, final frozen EXE7, development Electron9 and four gates passed. Remaining CH-03 and CH-04 through CH-11 stay pending. Do not redo old T00-T13 work or library imports.

- CH-04A: controlled provider/attempt/receipt services and native recovery verified; HTTP task management, settings and homepage consumption remain next. No real external processing is enabled.
- CH-04B: HTTP generation and application-owned task lifecycle verified on 2026-10-19. Final targeted 145 passed, 351 stable inputs; four gates, independent review and rebuilt frozen backend/helper passed. Homepage consumption, protected settings/Jev and profiles remain. No real external processing or installer replacement.

## Review focus

No new model permission, no parser checks removed, no dependence on preloaded test modules, no optional dependency accidentally omitted by PyInstaller, no resources removed outside the supported build process, no performance numbers extrapolated to unseen hardware. The original desktop/backup/library paths must remain usable.

## Execution log

- 2026-10-19 follow-up after local product commit eccea9a: WorkBuddy connection recovered on a fresh status check. New three-file read-only task wb-151ff422094a completed with end_turn and three Read receipts, no findings. Root independently verified recovery wiring, BEGIN IMMEDIATE and unique run_id constraints; no product changes or repeated tests. Earlier busy/unknown observations below remain historical; the old task was not retried. See the phase evidence workbuddy-root-check.md.

- 2026-10-19 CH-04B afterffe1897 verified: four generation routes plus a bounded application task owner, with original worker lifespan composition. New work dispatches only after durable commit; history/replay/restart never send. Final session29924 ended exit0:145 distinct affected tests passed, no failures/errors/skips, JUnit86.360s;53 new tests included,351 stable inputs. This was not a full-suite rerun. Independent Spec7 plus1 unchanged post-fix probe and Standards6 passed; Unicode wire-cap P2 closed. Four gates and actual final frozen backend3/helper5 groups passed,203 stable build inputs;3 loopback POSTs,3 attempts/receipts,1 internal candidate. User reopened WorkBuddy chat but bridge stillbusy; old task lacks terminal record and active-state JSON damaged, previous wait unknown. No dispatch, no bridge mutation. No real model, installed app replacement or private data handling. [Evidence](../testing/chat-generation-http/20261019/README.md). Next homepage consumer, preserving fixed default-off and existing approved scope.

- 2026-10-17 CH-04A after114a1ab verified: explicit single-message DeepSeek transport, immutable wire/config/policy ledger, no-retry runner, body-free usage receipt and internal unverified output implemented as separate modules. Final full session3206 ended exit0 with2,348 passed/2 isolated-runtime skips (JUnit1,924.975s); the exact2 DuckDB cases then passed in the existing isolated runtime. All2,350 distinct collected cases covered, no unresolved failures/skips,451 stable input hashes;388 targeted cases are included, not added. Four development gates, final frozen backend and separate synthetic HTTP helper passed;201 stable build inputs, exactly1 loopback POST. Four independently reproduced defects closed. Earlier6904 and pre-event-fix builds are preserved historical evidence, never counted as final pass. No installed replacement, real credential/model, UI send, Jev or automatic profile. [Evidence](../testing/chat-model/20261017/README.md), [next HTTP/UI readiness](2026-10-17-main-model-http-readiness.md).

- 2026-10-17 CH-04 preparation during frozen regression: [source-based connection map](2026-10-17-main-model-readiness.md) records reusable authorization/ledger algorithms and the next bounded provider/attempt/runner seam. Historical queued tasks do not grant external processing; local attachment policy stays external=false, unknown billing needs its own DTO, and existing egress is synthetic-loopback only. This is implementation preparation, not a new user design interview or working main-model/Jev connection. No keys read, network model calls or frozen source changes.

- 2026-10-17 CH-03A after00b106c verified: 159 distinct targeted cases are included in the final 2,171-test full pass, not added; no failures/errors/skips, exit0, 1,814.65s, 426 stable source/test/config hashes and exact collection/JUnit match. Real browser11, final rebuilt frozen backend7, development Electron9 and four gates passed with synthetic materials. Independent review closed late-preview and destination-alias issues; valid alias RED1fail/1pass then42green. Original full94872 was deliberately stopped and preserved, never counted; final31938 ended and must not be rerun. DOCX long-path original creation/backup/restore/read/rebackup and read-only recovery verified. No model/Jev/send/auto-profile/installed update. WorkBuddy lost its task/endpoint; no review receipt. [Evidence](../testing/chat-attachments/20261017/README.md), [independent review](../testing/chat-attachments/20261017/review.md), [next preparation](2026-10-17-main-model-readiness.md).

- 2026-10-17 CH-02A after e46ce3c complete: five small ES modules and separate authenticated HTML routes; native login selects the local-draft homepage. Final single full suite 2,094 passed, zero failures/errors/skips, exit0, 1,743.82 seconds; collection and unique JUnit identities match. Page18/related40/frontend wrappers2 are included, not added; Node28+4 behavior groups ran through those wrappers. Real browser11, review-fix probes4, frozen EXE5 and actual Electron development home6/contract14/new intake10/backup10/restored draft1 passed. Four distinct code/visual findings closed; four development gates passed. Session84247 ended. Of397 initial hashes,393 unchanged; four standalone CJS callers changed and one new CJS added, separately verified; product/Python inputs unchanged. No installed app replacement, model/Jev or attachments. [Evidence](../testing/chat-home/20261017/README.md). [CH-03 readiness](2026-10-17-conversation-materials-readiness.md) independently reviewed: replay precedes new quota/version checks, and first native attachment recovery uses qxbak; cnbak identity/schema extension remains explicit future work. Planning is not attachment implementation.

- 2026-10-17 continuation after cfc3801: bounded message pages, latest-run summaries and lookup by the original request ID completed. HTTP create/draft responses also bounded, legacy service defaults preserved. 218 distinct focused/related tests passed (32 new included), zero failures/errors/skips; actual new frozen Windows EXE passed four groups including 51-message pagination, restart/idempotent replay, encrypted backup and quarantined recovery. Four development gates and independent Spec/Standards review passed. Current WorkBuddy three-file static review completed; future logical rebuild/cloud migration needs explicit order guarantees. No full-suite rerun, homepage/model/attachment integration or installer replacement. [Evidence](../testing/chat-history/20261017/README.md).

- 2026-10-17 completed continuation after e7618bb: assistant HTTP/list/cancel/SSE and exact recovery reads implemented; 97 service tests plus refined8 and final10 HTTP tests passed. Actual final frozen EXE6 groups passed. Standards polling-window P2 fixed and independently closed. Final full suite completed: 2,042 passed, no failures/errors/skips, exit0, 1,694.84 seconds; 387 source/test/config hashes unchanged and all JUnit identities unique. Evidence `.local/chat-api-20261017/full-final.log/.xml/.exit`, preserved summary [here](../testing/chat-api/20261017/regression-summary.json). Prior incomplete run deliberately interrupted and preserved, never counted as pass. Regression session19484 has ended; do not wait on it or repeat this run. Independent CH-02 experiments made no product/test changes.

- 2026-10-17 CH-02 preparation: Deep Chat's isolated default/adapted/native browser experiments completed with 26 observations and 12 outcome assertions, without product adoption. Keep the native input first release; actual CSP compatibility is not the reason to reject the component. Npm and design-source revisions differ and are recorded separately. [Evidence](../testing/chat-ui-compat/20261017/README.md). [Homepage readiness](2026-10-17-chat-home-readiness.md) confirms two prerequisites: bounded message history and server-side run discovery on reload. Independent read-only check found no necessary correction. No homepage/model/attachment completion is claimed.

- 2026-10-17 renderer preparation: fixed markdown-it 15.0.3 and DOMPurify 3.4.17 browser artifacts, registry integrity and seven license texts checked in an isolated directory; 13 synthetic browser checks passed, five localhost requests and no external attempts. Two scripts total 130,614 bytes, not an installer-size measurement. Root visually checked the long-URL table: no page overflow but first column too narrow, so product readability still needs CSS/viewport verification. No runtime adoption or desktop external-navigation change. [Evidence](../testing/chat-render-compat/20261017/README.md).

- 2026-10-16: resumed by explicit user message; hourly heartbeat update succeeded. Main branch and existing local environments reused. Two document reviewers identified five specification corrections, all incorporated before implementation. WorkBuddy status connected in this session; that status alone is not a completed review task.
- 2026-10-16: Tasks 2/3 implementation and targeted/frozen desktop checks obtained; exact results and full-suite process continuation are in [first-slice evidence](../testing/chat-first/20261016/README.md). Full regression pending, so Task 4 and local commit remain open. Current WorkBuddy scoped review completed; its hard-link unlink claim was rejected by independent review.
- 2026-10-17: Task 4 verification closed: full suite 1,903 passed / 2 isolated-runtime skips, then the exact 2 DuckDB cases passed in the existing runtime; 1,905 distinct cases covered. Schema/default/source/dependency development checks all exit 0. First-slice source has not changed since independent review and the completed full run; proceed with local commit and CH-01.
- 2026-10-17: 00c12b7 completed shared storage/request extraction, 167 distinct affected tests and 5 frozen checks. Current CH-01 storage slice then passed 293 targeted regressions and 8 actual frozen-backend checks, four development gates and independent Spec/Standards review. Four tables and five local services now preserve conversation input/scope/idempotency; queued runs do not execute. Known old archives validate before staging upgrades; restored runs are blocked. No new installer, homepage, model, attachments or real-data migration. Evidence: [CH-01 storage](../testing/chat-storage/20261017/README.md). Next: thin HTTP/runner boundaries, then homepage and pre-case attachments; do not treat the storage slice as complete CH-01 or product delivery.

- 2026-10-23 C2b2a: CH-07C2b2a已完成可信数据库装配：读取实际消息、原请求摘要及档案/接待基线，拒绝跨会话、旧绑定和版本变化，同时隔离发送后新草稿；共用附件选择校验拒绝损坏快照。单次13文件源码回归393项通过（可信装配49项、附件解码22项已包含），四开发门通过、545份输入稳定，独立复核见证据。发送、费用与原子保存仍由C2b2b闭合，自动归档入口继续关闭；安装版0.4.1及WIN-PATH-02状态未变。 [证据](../testing/profile-trusted-preparation/20261023/README.md)。

- 2026-10-23 C2b2b-A: CH-07C2b2b-A完成档案用途许可内核：完整保存计划绑定许可，普通聊天/资料回答/档案用途互相隔离，发送前后检查到期、撤权及配置变化，晚到候选丢弃而保留已收到用量。一次13文件379项关联通过（新增文件58项已包含），四开发门通过，546份工作区输入稳定。只修改现有registry，应用自动归档仍关闭；持久调用消费、费用和原子保存/历史恢复继续接线。 [证据](../testing/profile-authorization/20261023/README.md)。

- 2026-10-23 C2b2b-B: CH-07C2b2b-B完成内部档案执行与历史恢复闭合：复用单次调用账本和预算，同次回答、费用、待核档案/接待及固定保存回执原子提交；撤权弃候选保费用，恢复不重发。23文件首轮667/668通过，1项旧断言更正后原文件53项通过；产品源码未变，四开发门通过。原生许可窗口、HTTP/任务调度和档案面板仍待接入；安装版0.4.1及WIN-PATH-02开放状态不变。 [证据](../testing/profile-execution/20261023/README.md)。
