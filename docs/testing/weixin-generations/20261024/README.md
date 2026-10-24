# D2f 跨对话收件代际底座实测（2026-10-24 UTC）

从 `01d5a1a` 按[设计与实施合同](../../../plans/2026-10-24-weixin-generations-d2f.md)完成存储、升级、历史校验与明确阻断。本片没有正式的对话转案或 peer 切换服务；独立 SQL 合成记录不代表实际微信绑定。

## 源码已实现

schema17 `weixin-generations-v1` 仅追加 `weixin_peer_generations`，14字段、3个FK、root/generation与root/request和目标binding唯一，整行不可改/删。集中冻结 DTO `WeixinPeerGeneration` 绑定规范scope及完整摘要，严格整数、UTC、有界理由，首代前摘要为空、后代必须连接前代。旧mapping、grant、poll、descriptor、dispatch的结构和历史不改，D2d同目标规则不放宽。

`generation_integrity.py` 核对同owner/workspace、新CID/精确synthetic binding、跨原mapping及全部代际的binding占用、原/前代CID禁复用、连续代际、首代D2d有效scope摘要、后代scope及完整generation摘要链。checkpoint与账号poll、dispatch、grant的UTC上界吻合，代际不得在账号/root撤权后产生；首次代际后全账号不得再有上述微信活动。新目标的消息source_revision和材料snapshot须真实存在且不晚于代际，revision0可保留之后新发生的普通活动。历史核验不冒充过去成员授权事实；运行切换仍需后续当前身份与权限核验。

schema catalog/bootstrap、数据库/原生升级/恢复链、六个旧assistant/task来源gate及三个旧微信gate接续新版本，ops完整性hook和两种恢复fence增加 `weixin_generation_enabled=false`。32个前驱native/non-native的原始及规范摘要不变；根代理另外用上轮Git提交中的catalog实现独立比对相同32组值，审阅者也核过原始DDL与旧30值前缀。

当前运行层不解释新代际：非空代际账号的poll、dispatch、scope refresh暂停，包括同账号其他peer；旧payload相关find也可拒绝。旧CID授权投影为target_changed，恢复/归档/撤权状态优先；永久撤权仍可用，时间回拨也晚于代际。零代际保持原行为，另一账号和普通TaskDraft人工读取/更新保持可用。这是暂时的账号级微信入口限制，不会取消已有普通业务任务。产品无自动生成或公开追加代际入口。

## 本轮实际验证

原始命令、JSON、JUnit、SHA和日志保存在本机 `.local/weixin-generation-20261024/`。`verification-summary.json`绑定19份产品源码、7份选定通过JUnit、Node与失败浏览器报告；逐份核验独立运行前后SHA及原AGENTS用户改动保持。

以下命令均使用 `.venv/Scripts/python.exe -B -X utf8 -m pytest <文件> -q --tb=short --junitxml=<回执>`。完整参数另存同名JSON；前三类名称均为真实模块范围，不代表全仓回归。

| 实际范围 | 最终回执 | 结果 |
| --- | --- | --- |
| 新generation DTO/schema/history/guards/backup，5模块 | `root-generations.xml` | exit0，230 passed，198.78s |
| 旧授权View/因果时间/refresh DTO/HTTP routes，4模块 | `root-desktop.xml` | exit0，88 passed，49.00s |
| 旧账号/完整收件/原子收件，3模块 | `root-runtime.xml` | exit0，81 passed，81.50s；1条既有故意伪造输入序列化warning |
| 旧分发/原子分发/重新授权/原子重新授权，4模块 | `root-dispatch.xml` | exit0，67 passed，74.67s |
| 旧inbox/dispatch/grant三历史完整性模块 | `root-history.xml` | exit0，216 passed，117.35s |
| schema版本/原生workspace升级，2模块 | `root-workspace-final.xml` | exit0，68 passed，156.47s；显式D盘独立basetemp |
| 旧三schema已改动的后继兼容节点，具体-k见storage-notes | `storage-legacy-green.xml` | exit0，64 passed，26.27s；未称三模块全部用例 |

七份选定JUnit按 `(classname,name)` 核对为**24模块814个不同Python用例**，无重复身份、失败、错误或跳过。新增五模块根整组230已经包含作者最终97及独立25，不再累加；早期storage106/5与所有重复或中间组也不另加。独立25在最终19份产品源码和3份测试/辅助文件SHA前后相同条件下通过（34.27s），覆盖guard19及真实备份6；作者DTO20+history77另有冻结97回执。

14个 `scripts/test_assistant*.mjs` 使用现有bundled Node v24.22.1 `--test --test-reporter=tap`，exit0：**192 passed**，0 fail/cancelled/skipped/todo，0.25s。四开发检查最终源码上exit0：`-m cn_contract.cli schema --check`、`scripts/verify_defaults.py`、`scripts/verify_sources.py --mode development`、`scripts/verify_runtime_dependencies.py --mode development`，前缀同上。13来源仍NOT_PRODUCTION_APPROVED，55 runtime+1 build，native_build_verified=false，network_calls=0。

## 端到端边界与验收矩阵

| 合成场景 | 本轮实际结果 |
| --- | --- |
| 两代记录与D2d前置grant、旧accepted/blocked/已分发来源 | 校验通过，原payload/摘要不迁移、不改写；没有运行时切换服务 |
| 跨owner/workspace、复用原/其他代binding、回原/前代CID、编号/hash/checkpoint/撤权/UTC破坏 | 完整重算新摘要仍拒绝，历史不靠hash格式判真 |
| 缺失/未来input或material版本；此前/同刻/0版本后续活动 | RED→GREEN；独审另用完整schema17内存库调用真实公开validator独立复验10边界，符合预期 |
| 账号暂停及隔离 | poll/dispatch/refresh和旧find拒绝；同账号其他peer暂停；另一账号正常；恢复/归档/撤权投影优先；时钟回拨仍能永久撤权 |
| 普通TaskDraft继续人工处理 | 实际read_draft→update_draft→read成功，旧微信payload/grant/generation不改 |
| 完整native qxbak两代往返 | 保留两代记录、原grant/poll/descriptor/dispatch及任务历史；恢复poll/dispatch/refresh保持BLOCKED_LIVE；普通非native归档拒绝非空代际 |
| 篡改归档并重算摘要 | previous_scope/checkpoint/root目标破坏均在创建及真实认证restore阶段拒绝，不发布目标目录 |
| 独立guard/backup样本执行 | assistant/model/review/task execution等run为0，无真实模型/微信 |
| 额外继承对话授权浏览器回归 | **FAIL**：前段真实合成上传、两次授权和丢ACK找回完成（grant2/POST2）；qxbak恢复在 `workspace_backup.py:376` 发布目录rename遇 **WinError 5**，后续恢复页面及撤权验收未完成 |

来源时间10例通过public save_message/select_materials创建真实来源，其中消息操作会产生queued assistant_run，未启动worker/provider；不能把全部Python场景概括为零run。独立guard/backup25的零run断言只覆盖相应样本。

浏览器命令 `.venv/Scripts/python.exe -B -X utf8 scripts/validate_weixin_authorization_browser.py --output .local/weixin-generation-20261024/browser-regression` 实际exit1；失败JSON及qxbak保留。本轮未重试漂绿、未修改该路径实现，**WIN-PATH-02继续开放**；独立6项备份通过不能替代这组浏览器恢复失败。截图未做新的视觉评审，不称浏览器全流程通过。

## 失败、修复与独立复核

有效先行RED包括缺DTO20、缺schema17的33、完整历史规则32 failed/35 passed，以及独立运行守卫和篡改备份13例。独审实际构造“generation 03Z、目标revision1消息04Z”证明未来版本被接受；新增时间规则定向RED为4 failed/6 passed，修为generation专属 `_scope_sources` 后10通过，并执行完整97及根230。旧 `_scope` 与原微信历史语义未更改。

原生workspace回归首次 `root-workspace.xml` 为10 passed/58 setup errors，原因是旧pre-intake夹具删除扩展表时遗漏新generation表，不能算产品行为RED；只在原DROP清单加该表，保持精确旧schema断言，最终两模块68全部通过。不是资源guard失败，没有改资源保护。

独立审阅核过计划取舍、32指纹/DDL、三个旧微信gate、来源时间真实public validator探针、19源码冻结SHA和回执，最终无剩余确认源码缺陷。具体本机 `review-notes.md`；本轮未启WorkBuddy新任务。浏览器WinError5仍是未解决的实际失败，不以源码审阅通过覆盖。

## 尚未实现与NOT_RUN

显式代际追加/切换服务、当前桌面权限/CAS/未知结果查询、桌面切换入口及按代际恢复收件尚未实现；真实微信资格/可信身份/transport、登录/轮询/下载解密/发送Outbox、E有限期模型授权仍待。全仓回归、真实账号/模型/合同外发、付费、意见签发、新安装包和安装版Electron均NOT_RUN。安装版0.4.1及原生长进程崩溃未验证修复；WIN-PATH-02本轮复现仍开放。运行SQLite未加密，完整备份加密不代表运行库加密。

产品 `6e36cb5` 已正常推送并核远端SHA/tree/5,073条目一致；[独立同步回执](github-sync.md)。未把计划或候选称生产完成。
