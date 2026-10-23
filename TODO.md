# TODO — 群兴法律工作台协作清单

2026-10-23 CH-07C2b2a已完成可信数据库装配：读取实际消息、原请求摘要及档案/接待基线，拒绝跨会话、旧绑定和版本变化，同时隔离发送后新草稿；共用附件选择校验拒绝损坏快照。单次13文件源码回归393项通过（可信装配49项、附件解码22项已包含），四开发门通过、545份输入稳定，独立复核见证据。发送、费用与原子保存仍由C2b2b闭合，自动归档入口继续关闭；安装版0.4.1及WIN-PATH-02状态未变。 [实测](docs/testing/profile-trusted-preparation/20261023/README.md)。GitHub同步以随后回执为准。

CH-07C2b1源码与合成证据 `35fc88a` 已同步，远端SHA及4,438文件树一致；[同步回执](docs/testing/GITHUB-PROFILE-MODEL-SCHEMA-20261023.md)。

2026-10-23 CH-07C2b1：自动建档的存储前置切片完成。新命名schema及固定保存回执保留旧11版44摘要，三迁移通道与五族旧完整性校验接续；新格式/新回执仍fail-closed，未启用自动归档。20文件初轮630/632通过，2项旧测试预期修正后两个文件54通过；四开发门通过，542份输入稳定、产品源码未变，Spec6/Standards30独立通过。修复新摘要CHECK的NUL尾缀漏洞。安装版0.4.1和WIN-PATH-02开放项不变；未碰真实资料/模型/云。[证据](docs/testing/profile-model-schema/20261023/README.md)。

最新接续（2026-10-23，CH-07C2a）：离线发送内容/保存计划绑定完成；380关联、四开发门、Spec12/Standards9通过。C2b仍须闭合原生用途许可、版本化账本、固定原子钩子及迁移恢复，自动保存尚未启用；以[本片证据](docs/testing/profile-basis/20261023/README.md)为准。`a84a156`已正常同步，远端SHA及4,370文件树一致；[回执](docs/testing/GITHUB-PROFILE-BASIS-20261023.md)。

最新接续（2026-10-23，CH-07C1）：协议切片及577项关联验证完成，自动保存仍待C2/C3；以[本片证据](docs/testing/profile-output/20261023/README.md)为准。后续同步结果见下方回执。
已同步：CH-07C1协议源码与证据 `bcc5013`，远端SHA及4,331文件树一致；自动建档接线和Windows恢复开放项继续推进。[同步回执](docs/testing/GITHUB-PROFILE-OUTPUT-20261023.md)。

最新接续（2026-10-23）：CH-07B本地档案/接待原子保存、历史接口、迁移恢复已实现并独立复核。完整回归3816通过/3失败，两个旧测试夹具已修正、定向9/36通过；最终目录rename WinError5仍待定位，保留开放验收项，不称全套全绿。自动钩子与档案侧栏尚未接通；先核对本片诊断证据，再推进CH-07C。WorkBuddy本轮无活动端点未派发，安装版0.4.1不变。[本片证据](docs/testing/profile-persistence/20261023/README.md)。同步状态以独立回执为准。

更新：2026-10-22。对话页模型 UX 小片从 `8c609ac` 完成（所有者直接指令）：排查并修复"API 已配置但发送按钮灰色"（模型启用是进程内存态，重启即失效；capability 需已保存草稿触发）——①持久化所选模型并在后端就绪时自动用本机已存密钥恢复配置（取消每次手动"配置本次运行"，显式停用才清除，换密钥不清除，恢复副本永不自动配置，Jev 不参与）；②对话页「保存草稿」左侧新增「切换模型」按钮（Flash↔Pro 互切、仅对话页主 frame 可调的新 IPC 桥、切换后自动重算 capability）；③窗口焦点回来时自动重拉生成条件。每次发送的原生确认窗逐次核对不变。此前记录已核对模型名、参数与价格文档；这不构成真实供应商连通或端到端验收，CH-04真实冒烟仍待。安装版仍为0.4.1。此表用于协作排期；完成事实以 [TASK_STATUS](docs/TASK_STATUS.md) 与对应证据为准，完整验收条件以 [v2.1](docs/plans/chat-first-architecture-v2.1.md) 为准。

`[x]` 只表示写明范围的工程切片完成，不表示整个 CH 阶段、真实法律效果或生产完成。`[ ]` 表示仍有工作。未认领不代表可跳过依赖；协作者在自己的 PR 中写明任务 ID、改动范围和依赖，再更新本表的负责人/状态，避免重复实施。当前未指定具体协作者姓名。

## 当前及下一步

| 任务 ID | 优先级 / 状态 | 负责人 | 交付与验收边界 | 依赖 |
| --- | --- | --- | --- | --- |
| CH-05C | 已完成本机配置切片 | Codex | 独立凭据、日常配置/停用、能力声明和关闭双清理；190桌面/119关联Python通过，源码/冻结Windows各9组；未接发送许可 | [本片证据](docs/testing/jev-native/20261020/README.md) |
| CH-05D1 | 已完成后端接线切片 | Codex | 独立逐请求许可、单槽保护和同主任务可选辅助；201桌面与157/83/32分组后端检查、源码10组/冻结控制7组通过；未接日常发送确认UI | [本片证据](docs/testing/jev-request/20261020/README.md) |
| CH-05D2 | 已完成同窗独立确认切片 | Codex | 240桌面、4开发检查、源码默认关闭6组/双选8组/冻结授权停用5组；辅助不选仍继续主流程，末检查失败清理闭合许可；真实预算未配仍关闭 | [本片证据](docs/testing/jev-confirmation/20261020/README.md) |
| CH-00A-续 | P0 · 持续推进 | 待认领 | 结合下一功能继续收窄入口职责及既有接待依赖；保持旧路由/DTO/权限兼容，不为拆文件增加空壳 | 先确定模块和关联测试 |
| CH-00A3 | 已完成接待依赖切片 | Codex | 建案/记录编码下移应用层、旧Web别名兼容、接待Word按需导入；147关联、4开发门、双轴各4探针通过；模块与跟踪分配实测不等于整机/安装包收益 | [实测](docs/testing/intake-decoupling/20261023/README.md) |
| CH-00B-续 | P0 · 可并行测量 | 待认领 | 复用既有基线，报告同能力包体、可输入时间、空闲/峰值占用和退出清理；区分安装器/未压缩目录/进程数据，不反复重建不变产物 | [首片测量](docs/testing/chat-first/20261016/README.md) |
| CH-00B2 | 已完成检索内存切片 | Codex | 长文原文定位去掉整篇映射；同合成样本Python峰值约-87.7%、耗时中位数约+6–8%；183通过加2项DuckDB补验通过，同代码分两批覆盖185项，不是整机资源验收 | [本片实测](docs/testing/library-memory/20261020/README.md) |
| CH-03-续 | P1 · 部分完成 | 待认领 | 补齐当前 DOCX 之外经批准的附件范围、衍生脱敏版本和跨模块映射；无可靠映射不外发 | 现有建案前附件/来源接口 |
| CH-04-续 | P1 · 部分完成 | 待认领 | 补第二主供应商及更广材料范围；真实合成联网验证需实际账号、数据许可及费用条件，缺条件如实记录 | 现有普通文字链；官方协议重新核对 |
| CH-06A | 已完成内部法库底座 | Codex | 最多8条/1200字符精确引用及当前权限重核；341关联通过、2旧DuckDB跳过；没有HTTP/UI/模型入口 | [本片证据](docs/testing/library-adapter/20261020/README.md) |
| CH-06B1 | 已完成内部持久化切片 | Codex | 持久引用、固定回执、8次工具额度、当前授权及schema/升级/恢复同片；完整回归3222通过，0跳过；未接UI/多轮模型 | [本片证据](docs/testing/library-ledger/20261020/README.md) |
| CH-06B2a | 已完成本机检索与引用面板 | Codex | 一次关键词查询与历史原文片段；Python同输入分两批覆盖3271通过（首轮3233+原38项换盘补验），55顶层Node/8组源码浏览器通过；归档与旧记录误判已修，无真实模型/安装器验收 | [本片证据](docs/testing/library-chat/20261020/README.md) |
| CH-06B2b1 | 已完成本机预览接口 | Codex | 服务器重建选定历史片段和问题，完整JSON/UTF-8预算，超限保留；无新许可/账本/模型调用/选片UI；644关联Python、4开发门、Windows HTTP9组通过 | [本片证据](docs/testing/context-preview/20261020/README.md) |
| CH-06B2b2a | 已完成适配基础切片 | Codex | 独立上下文DTO/codec与共享传输；542关联、4开发门、双轴各6项通过；应用资料发送仍关闭，无新schema/账本 | [本片证据](docs/testing/context-provider/20261021/README.md) |
| CH-06B2b2 | 已完成资料发送闭合切片 | WorkBuddy | 新输入格式列、有序来源关联、原生一次许可（服务端重建核对、max_calls=1）、同 attempt 执行/撤销/费用、升级与备份恢复同片闭合；一次资料辅助回答经回环 HTTP 字节核验；旧V1字节和权限保持；选片GUI与真实供应商不在本片 | [本片证据](docs/testing/context-send/20261021/README.md) |
| CH-06B2c1 | 已完成轮次账本底座切片 | WorkBuddy | attempts 重建支持 round_no（1–4、UNIQUE(run_id,round_no)、不可变触发器纳入新列）；FK OFF 重建窗口在三条迁移通道同序语句保证字节一致；完整性 fail-closed 拒绝多轮归档；行为不变恒 round 1；无 runner 循环/协议/授权变更 | [本片证据](docs/testing/bounded-rounds/20261021/README.md)；[执行合同](docs/plans/2026-10-21-bounded-rounds.md) |
| CH-06B2c2 | 已完成受限串行循环切片 | WorkBuddy | `library-context-v2` 工具计划协议（≤4轮/≤8工具、DTO 层拒陌生 tool）；max_rounds 显式授权形状与 registry lease generate_rounds 分支；`assistant-rounds-v2` CHECK 加宽（12 步重建、v1 冻结摘要固化）；runner 主循环与 rounds_exhausted/budget_exhausted/tool_limit/tool_rejected 四停止；撤权走 claim-abandon 闭合、恢复封存 interrupted 不重发；完整性开放 v2 多轮全绑定；v1 字节与行为不变；真实供应商不在本片 | [本片证据](docs/testing/bounded-rounds/20261021/README.md)；[执行合同](docs/plans/2026-10-21-bounded-rounds.md) |
| CH-06B3 | 已完成律师选片 GUI 切片 | WorkBuddy | 选片面板（本会话已保存引用 1–8 条保序勾选、编辑/换对话/撤选即失效）；预览扩展 send_basis（request_id 惰性铸造、DTO 逐字段一致性校验）；桌面 `authorize_context` 新通道（桌面自行 CSRF POST 预览重建 basis、六键确认窗片段清单、单次 lease）；前端三向互斥与发送分派、NETWORK_UNKNOWN 只找回不重发；无 schema/依赖变更，v1 单轮锁定，真实供应商不在本片 | [本片证据](docs/testing/selection-gui/20261021/README.md)；[执行合同](docs/plans/2026-10-21-selection-gui.md) |
| UX-01 | 已完成对话页模型 UX 小片 | WorkBuddy | 排查修复"已配置但发送按钮灰色"（启用为进程内存态+capability 需已保存草稿）；所有者指令取消每次手动配置——所选模型持久化、后端就绪自动用已存密钥恢复（停用才清除、换密钥不清除、恢复副本不自动配、Jev 不参与）；对话页「保存草稿」左侧新增「切换模型」按钮（新 IPC 桥仅对话页主 frame 可调）；焦点回来自动重拉 capability；每次发送原生确认窗不变；桌面 270/270、前端 68/68、四开发门 exit 0 | [本片证据](docs/testing/model-ux/20261022/README.md)；[执行合同](docs/plans/2026-10-22-model-ux.md) |
| WIN-PATH-01 | 已完成原件/qxbak源码切片 | Codex | 创建/读取/回滚统一I/O路径，逻辑引用不变；424关联、4开发门、16真实HTTP请求及双轴复核通过；原件父目录279→282字符。UNC/超长SQLite/任意长cnbak目标及新安装包未验 | [本片证据](docs/testing/contract-long-path/20261020/README.md)；CH-10仍需安装验收 |
| WIN-PATH-02 | P2 · 开放，发布阶段新现场 | Codex | 本轮全套首次长路径restore在最终目录rename报WinError5；孤立复跑通过，根因未定。与旧nlink/回收站shim错误不能混同，不猜测加重试或放宽守卫；保留前序复验及新顺序/句柄探针 | [本轮证据](docs/testing/profile-persistence/20261023/README.md) · [旧复验](docs/testing/intake-decoupling/20261023/README.md) |
| CH-07A | 已完成纯内核切片 | Codex | 来源/合并/人工保护/合法投影；400关联、4开发门、双轴6/9探针；无持久化或模型接线 | [本片证据](docs/testing/profile-merge/20261023/README.md) |
| CH-07B1 | 已完成来源前置切片 | Codex | 当前授权下有界重建真实存储来源；事务外核对原件后再次检查，存量损坏拒绝；186关联、4开发门、双轴7/8探针，无业务写入/模型接线 | [本片证据](docs/testing/profile-sources/20261023/README.md) |
| CH-07B | P1 · 后端已实现，整体验收未关闭 | Codex接续 | 原子档案/接待/回执、历史与人工接口、迁移恢复完成代码和定向验证；全套3816/3819，两个旧夹具修正后9/36通过，长路径发布WinError5根因未定。保留原失败，勿将补验算成一次全绿 | [执行合同](docs/plans/2026-10-23-profile-persistence.md) · [证据](docs/testing/profile-persistence/20261023/README.md) |
| CH-07C1 | 已完成协议切片 | Codex | 当前文字同次回答/提案、出处由服务器填充、撤权保留用量；577关联、4门、Spec13/Standards8+4通过；未启用应用自动建档 | [实测](docs/testing/profile-output/20261023/README.md) |
| CH-07C2a | 已完成离线准备切片 | Codex | 同wire不同保存计划使用不同basis摘要；实际saved views身份/版本桥接；380关联、4门、Spec12/Standards9；无运行许可或自动存档 | [合同](docs/plans/2026-10-23-profile-send-basis.md) · [证据](docs/testing/profile-basis/20261023/README.md) |
| CH-07C2b1 | 已完成存储前置切片 | Codex | 630/632初轮、旧断言修正后54补验/4门/Spec6/Standards30；旧签名与旧校验保留，新格式和handler记录仍禁止验收，自动归档未启用 | [合同](docs/plans/2026-10-23-profile-model-schema.md) · [证据](docs/testing/profile-model-schema/20261023/README.md) |
| CH-07C2b2a | 已完成内部核验 | Codex | 393关联/四门通过；实际消息与原请求摘要绑定，当前版本重建；发送和自动保存仍封闭 | [合同](docs/plans/2026-10-23-profile-trusted-preparation.md) · [证据](docs/testing/profile-trusted-preparation/20261023/README.md) |
| CH-07C2b2b/C3 | P1 · 待接线 | Codex接续 | C2b同时闭合用途授权/完整basis绑定/账本/固定原子保存钩子/迁移恢复；新schema已准备；还须实现同一次执行语义重放，移除封闭guard须与完整链路同片验收。C3接面板和本地联系方式。不得暗增第二付费提炼或默认创建空接待 | CH-07B、CH-07C1、CH-07C2a、CH-07C2b2a |
| CH-08 | P1 · 待贯通 | 待认领 | 对话产物的客户/内部范围、复制和 Word 导出；复用既有导出，不从整页 DOM 复制内部信息 | CH-07 及原文引用 |
| CH-09-续 | P1 · 随新增表同步 | 对应模块作者 | 现有对话/附件/调用账本恢复已覆盖；新增档案/成果仍需完整备份、旧版本兼容、只读拒写和不重发 | 与 CH-07/08 同片实施 |
| CH-10 | P1 · 待整体验收 | 待认领 | 新安装候选贯通聊天→收件→生成→档案→引用→导出；断网/Jev缺席、中文路径/输入/缩放、升级与资源实测；不覆盖本机真实资料 | 核心链具备可测范围 |
| CH-11 | P1 · 待统一接入 | 待认领 | 持衡固定四动作、材料映射、角色/阶段隔离和同请求幂等；两仓独立环境、失败可恢复 | 公共材料与权限接口 |

CH-05C/D1/D2 是协作细分标识，不替换 v2.1 中 CH-05 的总体验收；[架构交接](docs/plans/2026-10-20-jev-native-handoff.md)第一片已由CH-05C实现，第二片后端由[CH-05D1](docs/plans/2026-10-20-jev-request-backend.md)落实，同窗确认由[CH-05D2](docs/plans/2026-10-20-jev-confirmation.md)完成。Jev当前账本只接受完整普通文字意图判断；材料分类、运营风险须另建来源映射。预算预留不等于供应商收费上限或已付费用。

## 已完成的可复用切片

- [x] CH-00A 首片：公共存储初始化、HTTP 请求上下文及对话服务解耦；更广拆分仍在上表。
- [x] CH-00B 首片：PDF 延迟加载和 Electron 语言资源筛选；[同后端构建减少 46.62 MiB](docs/testing/chat-first/20261016/README.md)，不代表整体资源目标完成。
- [x] CH-01：对话存储、作用域、幂等、草稿、事件、迁移及受控恢复基础。
- [x] CH-02 首页切片：草稿、技能卡选择、历史、中文输入保护、取消/续读和生成历史呈现；技能卡不等于业务执行已经全接通。
- [x] CH-03A：建案前 DOCX 收件、原文版本、权限与恢复；未声称所有格式可读。
- [x] CH-04A—I：普通文字主生成、账本、会话授权、系统保护凭据、原生设置/具体发送确认及旧 provider 引用释放；真实调用保持未验，详见 [接线记录](docs/plans/2026-10-19-post-home-readiness.md)。
- [x] CH-05A：Jev 薄提供器/严格响应解析/纯路由，367 个关联用例；[证据](docs/testing/jev-adapter/20261020/README.md)。
- [x] CH-05B：独立辅助账本、升级与恢复，703 个关联用例；[证据](docs/testing/jev-ledger/20261020/README.md)。这些与前项为各阶段回归，不累加为总测试数。

- [x] CH-05C：Jev 原生独立配置生命周期；[190/119测试及Windows各9组实测](docs/testing/jev-native/20261020/README.md)，不代表辅助发送已经贯通。
- [x] CH-05D1：逐请求后端许可、固定私有协议和同任务可选辅助；[源码与冻结控制验证](docs/testing/jev-request/20261020/README.md)，不代表D2确认UI或真实调用已完成。

- [x] CH-05D2：同窗独立许可、可选辅助与失效清理；[Windows实测与独立复核](docs/testing/jev-confirmation/20261020/README.md)。真实辅助未启用。

- [x] CH-06A：独立法库引用及前后权限检查；[Windows合成库实测与独审](docs/testing/library-adapter/20261020/README.md)，内部接口不代表自动查库/法律判断已贯通。

- [x] CH-00B2：检索共用按区间定位；[同源前后内存/耗时、183项加2项补验通过及独审](docs/testing/library-memory/20261020/README.md)。未覆盖Electron/RSS/冷启动。

- [x] CH-06B1：固定调用事件、持久引用、不可变回执、历史授权与完整备份迁移；[全套及独立复核证据](docs/testing/library-ledger/20261020/README.md)。HTTP/UI、4轮模型和自动档案仍未完成。

- [x] CH-06B2a：本机检索、持久引用面板、未知请求找回、取消与只读恢复；[源码分批回归与浏览器证据](docs/testing/library-chat/20261020/README.md)。资料辅助生成与自动档案仍待。

- [x] CH-06B2b1：独立完整上下文预览接口、旧文字协议不变、无外发及恢复副本拒新预览；[关联回归和实际HTTP证据](docs/testing/context-preview/20261020/README.md)。未完成资料发送或新选片UI。

- [x] CH-06B2b2：`assistant-context-v1` 不可变输入格式、有序来源关联、原生一次许可与备份恢复同片闭合，一次资料辅助回答链路接通；[关联回归、原生回环字节与升级恢复证据](docs/testing/context-send/20261021/README.md)。律师选片GUI、真实供应商与有界多轮仍待。

- [x] CH-06B2c1：`assistant-rounds-v1` 重建 attempts 表支持有界轮次（round_no 1–4 不可变、UNIQUE(run_id,round_no)），三条迁移通道 FK OFF 窗口同序闭合、新建与升级字节一致、数据行保留；完整性校验对多轮归档 fail-closed；[结构/迁移/损坏矩阵与关联回归证据](docs/testing/bounded-rounds/20261021/README.md)。行为不变（恒 round 1），循环 runner、工具计划协议与轮间授权仍待 B2c2。

- [x] CH-06B2c2：`library-context-v2` 工具计划响应协议与同 run 受限串行循环 runner（model round→固定 library handler→下轮/final，≤4 轮模型/≤8 工具）；轮间授权显式形状 max_rounds；结构版本 `assistant-rounds-v2`（CHECK 加宽含 v2，复用 12 步重建、三条通道同片闭合）；四种有界停止原因与恢复封存不重发；完整性开放 v2 多轮语义（plan↔tool.before↔receipt↔下轮 exchanges 精确绑定，篡改矩阵全拒）；[runner/schema/授权/完整性矩阵与广域回归证据](docs/testing/bounded-rounds/20261021/README.md)。v1 字节与行为完全不变；真实供应商接入、律师选片 GUI 仍待排期。

- [x] CH-06B3：律师选片 GUI 三层落地——网页选片面板（`assistant-context.mjs` 控制器：savedCitations 汇集、保序≤8、request_id 惰性铸造、点选/编辑/换对话即失效、与 generation/research 三向互斥）；预览扩展（`MainContextSelection.request_id` + `MainContextPreview.send_basis`，ready 且给 request_id 时服务器组装 v1/v2 basis，DTO 校验逐字段一致且 source_bindings 与 manifest.sources 同序）；桌面授权链（preload `authorizeContext` → `desktop:approve-context` 处理器自行 GET 草稿/材料 + CSRF POST context-preview 全量比对 → 确认窗六键 library_context 变体渲染片段清单 → 单次 lease → Python `_OPERATIONS` 分发既有 `authorize_context`）；发送走 context-generations，NETWORK_UNKNOWN 只经 by-request 找回；[前端/桌面/Python 关联回归与端到端合成走通证据](docs/testing/selection-gui/20261021/README.md)。无 schema/依赖变更；v1 单轮锁定（max_rounds 锁 1），真实供应商接入与 v2 多轮界面仍待排期。

- [x] UX-01：对话页模型 UX 小片（所有者直接指令）——排查"API 已配置但发送按钮灰色"：模型启用为后端进程内存态（重启即失效）、capability 需已保存草稿触发，设置页「返回」整页重载本就缓解，本片补窗口焦点回来自动重拉 capability。取消每次手动「配置本次运行」（所有者明确指令的安全姿态变更）：所选模型持久化于 desktop-settings.json（严格校验），后端就绪自动用本机已存密钥恢复配置；显式停用才清除、换密钥不清除、恢复副本永不自动配置、Jev 不参与；每次发送的原生确认窗/单次 lease/会话绑定/120 秒有效期全部不变，密钥仍只在 OS 保护存储。对话页「保存草稿」左侧新增「切换模型」按钮：新 model-bridge.cjs 两 IPC（仅对话页主 frame、ready、非恢复副本），Flash↔Pro 互切并持久化，切换后自动重算 capability，无桥时按钮隐藏。桌面全套件 270/270（新 model-bridge 5 项、导航 2 项旧语义按新行为更新+2 项新增、桥键断言同步）、前端全套件 68/68（新增渲染 2 项）、四开发门 exit 0；Python 后端零改动。推送后真实启动回归（当日修复）：settings 的 model 键泄漏进 backend.start 参数触发 desktop_entry 白名单 BACKEND_REJECTED，已改为传参前剔除该桌面侧键并加防回归断言，复跑桌面 270/270、真实启动后端拉起验证通过。[证据](docs/testing/model-ux/20261022/README.md)、[执行合同](docs/plans/2026-10-22-model-ux.md)。

## 数据及交付前提

- [ ] 继续复用本地案例/法规索引成果；增量清洗、失败恢复和来源回查以既有导入记录为依据，禁止重复覆盖原件。
- [ ] 1985—2024 年数据目前在用户百度网盘、尚未下载；不能把年份范围当作本机入库数量。
- [ ] 阿里云在线资料库：服务器、访问权限、部署与迁移验收尚未完成；本机可查不代表多人在线可用。
- [ ] 受邀注册、验证码/密码登录、找回密码、设备会话与在线更新仍需独立交付，不由本机密码登录替代。
- [ ] 法律规则/材料使用许可、真实模型有限调用、律师质量验收及生产批准分别落实；不增加收费系统。

## 每次完成任务时

1. 更新本表的真实范围和剩余项，在 TASK_STATUS 添加结果、限制及证据链接；README 更新协作者需要知道的能力变化。
2. 记录实际目标检查与独立复核。没有运行的写未运行；相同输入和已完成验证不反复重跑。
3. 获取远端更新、检查协作者改动和待推送文件/历史。仅提交任务相关文件；真实材料、密钥、运行库及安装产物留本机。
4. 按 [协作约定](CONTRIBUTING.md) 正常推送到对应分支，再核对远端 SHA；遇到分叉先整合复核，不强制覆盖。同步失败保留本地提交，记录原因，不写已同步。
