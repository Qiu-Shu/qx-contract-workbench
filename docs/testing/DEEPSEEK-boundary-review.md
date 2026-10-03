# DeepSeek 离线适配边界独立审阅

2026-10-03 UTC。范围：首批纯离线 codec 与现后端安全边界；当前 **ENGINEERING_PASS（本独审25项）/ REAL_CALLS_DISABLED**。本文不记录协议审阅代理或根回归为自己的测试，也不以源码扫描代替运行。

## 原始边界与只读核验

独立基线覆盖 450 个公开项目文件：全部现 src/tests/sources/schemas/config/scripts，加 pyproject、无密钥的 .env.example 与 ChatGPT 目标方案。原 domain 完整正文 46,979 bytes 和 ReviewRun 导出 schema 另留只读副本，实际确认原 schema 与唯一领域模型一致，包含 13 个 $defs。

基线 `.audit-local/deepseek-boundary-review/baseline.json` SHA-256 `db59ffcf3f5ba770c7846ed033a7354af1c378b6243a387e9b14fb55e14364b2`。后续 api-seen 快照是实施中观察；作者冻结后 final 快照实际为 452 个文件，变化只有 domain.py、新 deepseek_codec.py、新 test_deepseek_codec.py；其他 449 个原文件 hash 不变，包括原84定义和虚构材料、来源/运行依赖锁、默认配置、CLI/web/模型注册/出站/签发代码与插件目标方案。

本审阅捕获和读取全部是公开工程代码、独立虚构测试材料及既有脱敏配置，未搜索或读取真实 key、环境凭据或私人合同。最初读取时曾使用不存在的 ReviewRun.schema.json/export_schema.py 等猜测路径；它们是辅助定位错误，不是业务功能 RED。之后实际定位唯一 schema 为 schemas/review-report.v2.schema.json，CLI 的 schema --check 为只读比较。

## 当前候选代码与守卫核验范围

新增三 DTO 仅在 domain.py，codec 返回 DeepSeekOfflineReply，状态 OFFLINE_ONLY / protocol_only，unknown cost 为 None/USD；显式离线发明价格标记 synthetic/estimated_synthetic。它们不是 ModelResponse 或合法扣费收据。

代码读取已确认旧 require_provider 只接受服务端注册 exact MockProvider，默认 mock、QCC off、web services 仍构造 mock。已有 CLI、web Cookie/CSRF/案件 authorize、预算 gateway、egress、正式签发与 T13 当前守卫不属于 writer 修改范围；最终保留证据需实际 hash 和运行探针。

自己的目标探针覆盖：原 450 文件边界/旧 domain 定义与常量 AST、ReviewRun schema 不扩展；默认和 CLI 真实 provider 标签先拒；DeepSeek/未注册 loopback 目的地的 egress 拒绝；codec/domain 不新增 I/O import 或动态执行；codec 导入和三函数运行时禁止 env/socket/执行能力；有限 anchor 投影；离线 DTO 与 synthetic 成本不授 provider 权限；旧 workflow 拒绝离线 reply 且审查记录不增加；unknown cost、OFFLINE 状态与 payload 字符串保持数据。

一个独立虚构上下文由既有 prepare helper 创建，复用模块级实例，不把多次造 DB 当审查样本数量。所有新探针、native collection、JUnit、命令和时间放在自己 `.audit-local/deepseek-boundary-review`；实际数量以运行结果为准。

## 实际测试结果

作者明确冻结后实际运行自己的探针：**25 passed，0 failed/errors/skipped/warnings，退出码0**。预先 native collection 与实际 JUnit 25 参数名称一一相等；15 个当前关键执行输入前后 hash 完全一致。pytest 显示 1.10秒，独审包装耗时 1.584004秒，UTC `11:00:44.748659–11:00:46.332663`。原始结果保存于 `.audit-local/deepseek-boundary-review/final-01/`。

|实际命令（均本项目.venv Python）|退出码|实际结果|
|---|---|---|
|`python -X utf8 .audit-local/deepseek-boundary-review/capture-body.py`|0|原domain bytes/hash与450基线相等；原ReviewRun导出schema与保存文件相等、13个$defs；不是功能测试|
|`python -X utf8 -m pytest .audit-local/deepseek-boundary-review/test_boundary.py --collect-only -q`|0|25个native参数；UTC11:00:44.267283–44.747658|
|`python -X utf8 -m pytest .audit-local/deepseek-boundary-review/test_boundary.py -q --tb=short --basetemp=.audit-local/deepseek-boundary-review/final-01/temp --junitxml=.audit-local/deepseek-boundary-review/final-01/results.xml`|0|25PASS/0警告；与collection相等；执行前后15关键输入稳定|
|`python -X utf8 .audit-local/deepseek-boundary-review/snapshot.py final`|0|452当前文件；原449保持，只有domain修改及codec/正式test新增|

当前源hash：domain `c118ff19479fa4cc56aa393740234fd8f78df4a81815a8fde2048dbf535609fc`；codec `1691a927aac4c4b0676536f19e2887538278a4d9a32e29d27e823084438ef362`；正式测试 `406b7eb3d3c4017788d021dd74796245fd58723ea426b78e5564b1c9df512f55`。自己的JUnit SHA-256 `73036d9469c6c94cb260e661a2f02459cfa5df63cecdb91271a979e34201bad3`。

实际正例执行了请求投影、响应解析和显式发明USD算术；费用未知时仍为None，合成估价例为USD `0.0000027`，未当成真实扣费。wire/reply/usage/合成估价对象均经旧require_provider实际拒绝；旧run_review实际拒reply且ReviewRunRow数量不增加。CLI的deepseek标签在读fixture和创建输出前实际阻断；三个未登记目的地实际BLOCKED_LIVE。恶意Python形状字符串仅保留在payload，导入与函数运行的env/socket/执行相关插桩未触发。真实供应商请求0。

本独审没有发现新业务缺陷；不存在独审功能RED，不冒认作者的有效RED是自己的发现。当前签发/HTTP/完整mock旅程主要由原代码hash保护，本独审没有实际生成并尝试签发新导出包、没有新浏览器或Word检查。历史815/84、作者121/308、协议代理结果和根新回归分别记录，不并入这25项。

## 未解除范围

此阶段不接入真实 transport、不读取密钥、不付费、不安装 ChatGPT/Codex 插件、不创建 OAuth/隧道/托管项目，不处理真实材料。源码和局部插桩不能代替 OS 全局出站/秘密访问保证。真实模型/数据政策/价格账本/批准信任根、法律规则与双律师 gold、正式签发与生产仍独立阻断；ChatGPT 目标方案保持 PLANNING_ONLY。
