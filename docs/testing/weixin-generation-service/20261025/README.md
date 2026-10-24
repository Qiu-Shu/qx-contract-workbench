# D2g1 显式代际追加与查询实测

基线37654fa，按[实施合同](../../../plans/2026-10-25-weixin-generation-service-d2g1.md)完成后端服务。只追加domain输入DTO和新generations.py；schema17、原历史和账号暂停guard不改，无HTTP、页面或实际收件切换入口。

## 源码已实现

八字段冻结 `WeixinPeerGenerationInput` 绑定request、严格整数generation/checkpoint、前代/前scope摘要、target binding、完整scope和理由；零代际前摘要必须为空，拒绝额外权限字段并重新校验model_copy。

`append_synthetic_generation` 在BEGIN IMMEDIATE中重建实际principal/fence及schema17后读取root，不让旧库缺表SQL先于明确409。账号active=False仅绕过代际暂停，仍拒绝account/root撤权；root、当前最新目标及请求固定目标/新目标均核当前owner/workspace、对象ACL、案件/转案状态和会话未归档。exact scope、代际/两个摘要/checkpoint CAS、跨原mapping和所有generation的binding占用及CID重复检查后，按真实目标来源和账号因果时间只INSERT一条，完整pre/post历史验证成功才commit。全部可能写拒绝审计的权限检查在INSERT前结束，post只做纯历史校验。零代际也明确检查旧inbox/dispatch/grant，不依赖空表validator早返。

同request先用已存目标核当前权限和snapshot，再还原原八字段核对，完全相同返原记录；后续代际不使旧request误报latest CAS，自身binding不误判占用。不同输入409；不重写记录或推进旧游标。未知结果用 `find_peer_generation` 只查固定metadata；恢复副本、逻辑撤权、会话归档或scope增长后仍须root和命中目标当前对象权限，历史不授予当前访问。成功find无业务/审计写入，ACL拒绝可沿既有机制独立记审计，不声明拒绝绝对零写入。

追加代际之后整个账号的微信收件仍暂停，旧payload不重新解释，普通TaskDraft可人工继续。find成功或记录已保存均不代表实际微信已连接、目标运行切换或法律意见批准。

## 本轮实际验证

本机原始证据位于 `.local/weixin-generation-service-20261025/`；verification-summary.json绑定2份改变产品源码及20份运行相关源码、最终JUnit/Node/四门回执和原AGENTS用户改动。独立16另绑定3个测试/辅助文件，23份SHA运行前后相同。

| 实际命令范围 | 最终证据 | 结果 |
| --- | --- | --- |
| Input/service/atomic/backup四新模块 | root-new.xml/json/log | `.venv/Scripts/python.exe -B -X utf8 -m pytest ... -q --tb=short --junitxml=...`，显式独立D盘basetemp；exit0，100 passed，95.85s |
| 旧generation DTO/history/guards/backup及View/UTC/refresh DTO/HTTP八模块 | root-legacy.xml/json/log | 同命令前缀及独立D盘basetemp；exit0，210 passed，114.26s |
| 作者最终Input20+service64 | backend-final.xml及backend-summary.json | exit0，84 passed，53.45s；不再加进根100 |
| 独立事务12+恢复4，最终schema修补后重绑 | independent-final.xml/json | exit0，16 passed，19.13s；不再加进根100 |
| 14个scripts/test_assistant*.mjs | node-all.tap/json | 现有bundled Node v24.22.1，--test --test-reporter=tap；exit0，192 passed，0 fail/cancelled/skipped/todo，0.25s |

两份根JUnit按classname/name为**12模块310个不同Python用例**，无重复、失败、错误或跳过。各轮历史925/255/814与本轮310的模块选择不同，不能相加或称全仓总数。实际完整argv、时间、退出码和摘要见相应JSON。

最终源码四开发检查均exit0，前缀 `.venv/Scripts/python.exe -B -X utf8`：`-m cn_contract.cli schema --check`、`scripts/verify_defaults.py`、`scripts/verify_sources.py --mode development`、`scripts/verify_runtime_dependencies.py --mode development`。13来源仍NOT_PRODUCTION_APPROVED、55runtime+1build、native_build_verified=false、network_calls=0，不是发布或生产通过。

## 验收矩阵

| 场景 | 实际结果 |
| --- | --- |
| 实际公开服务生成两代、重放第一代、未知查询 | 完整链和固定结果准确，全部旧payload/grant/poll/dispatch/游标/任务表保持原值 |
| 当前权限与输入冲突 | root/最新/新目标的成员/归档/接待归属、owner/workspace、真实session和复制模型均核验；旧request输入冲突409 |
| 真实目标来源与回拨时钟 | 绑定当前完整scope；真实消息/材料snapshot入因果floor，缺来源拒绝，不将不同CID版本计数比较大小 |
| 旧/未知schema及坏历史 | 身份/fence后精确schema17门，旧pre-inbox/前16版和未知结构均409且不修复；旧inbox/dispatch/grant及generation损坏拒绝 |
| SQL/commit故障 | INSERT前、实际INSERT后及commit前故障均回滚；真实commit后丢ACK保留唯一记录，仅find找回 |
| 并发与poll竞争 | 两实际Session/SQLite写锁竞争；异request同CAS恰一胜，同request返同记录；poll先胜令旧append CAS409，append先胜令poll STATE_CONFLICT，游标只因合法poll推进 |
| 新Database/新Python进程 | 不初始化schema、不启动worker，固定记录可查且不重发 |
| 服务生成两代后两次真实qxbak往返 | 记录和旧历史精确保留；恢复find可查，追加BLOCKED_LIVE，generation fence仍false |
| scope增长/会话归档/逻辑撤权后查询 | 成功find固定metadata只读；当前ACL仍须成立，不解除暂停或重新授权 |

普通正例和多数组合样本assistant_runs0；特定实际来源示例经public save_message产生恰1个queued run，未启动worker/provider，model attempts/review/task execution为0。不能将全部310项概括为零run。独立测试使用真实服务生成generation，故障SQL样本仅用于破坏/回滚验收，不冒充运行切换。

## 失败分类与独立复核

DTO缺失20个断言RED；首服务模块缺失1断言RED，属于接口缺失，不当成业务逻辑全覆盖。已有request改binding的有效RED为1 failed/6 passed：原先先读请求binding返回403，修为核已存目标后比完整input返回409；不是权限绕过。先行7 failed中6项为测试helper误用ServiceError.status，已纠正，不当成产品缺陷。

旧pre-inbox schema实际识别后两入口仍先查缺表抛OperationalError，有2个有效RED；把纯schema门移至身份/fence后、root SQL前，6个旧/未知schema节点GREEN，再跑完整84和根100。另两个损坏inbox样本先被不可变trigger拦截属故障夹具问题，改用既有corrupt helper，不作产品修复或有效RED。

独立事务/备份首轮在模块已实现后写完便通过，未声称有RED；旧schema修补前16只是中间证据，最终16绑定新SHA重新通过。独立review核事务/ACL顺序、旧request、纯post验证、schema修补、20源码/23执行文件摘要及计数，最终无剩余确认缺陷；本机review-notes保留。未启动WorkBuddy新任务。

## 未实施及NOT_RUN

按代际恢复接收/分发、HTTP/桌面明确操作、可信微信身份及transport、E有限期模型许可仍待；没有运行时切换或真实微信使用验收。本片浏览器、全仓回归、安装版Electron、真实账号/模型/合同、付费、签发/外发、新安装包均NOT_RUN。上轮[浏览器恢复WinError5失败](../../weixin-generations/20261024/README.md)未重试、未修复，WIN-PATH-02和原生长进程崩溃继续开放；安装版0.4.1不变。qxbak通过不代替运行库加密或安装版验收。

GitHub同步以本轮独立回执为准。
