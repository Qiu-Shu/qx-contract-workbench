# CH-04B：受控生成 HTTP 与任务生命周期实测

2026-10-19，基线 `ffe1897`，沿既有 `codex/contract-review-v2` 分支完成。本片只有后端 HTTP 和生命周期；首页发送、真实模型设置、Jev、自动档案及新安装器仍未交付。独立虚构输入和回环服务是本轮唯一模型测试材料，真实模型调用为 0，安装版 0.4.1、真实工作区及法库未改。

## 实际改动

- 新 `assistant/task_manager.py` 管理本应用新登记的任务，固定最多 4 个并行任务。复用原授权、预算、幂等、claim、runner 和费用回执；事务提交后才调度，模型等待不占事务。历史记录、重放和读取不触发补发。
- 新 `web/assistant_generation.py` 提供能力状态、快速登记、当前权限下读取成果及按请求 ID 找回。`app.py` 仅增加装配。DTO 仍只定义在 `domain.py`；没有新增依赖、数据表或后台进程。
- 本机生命周期组合原工作器与生成任务，关停先停止准入并等待生成收尾，之后释放数据库与目录锁。恢复副本保持只读；新的三种读取路径采用精确白名单。
- 默认可信运行时为 `None`。能力查询仅依据已保存草稿，不读取凭据、不调用供应商。附件和未接通技能不能取得普通生成权限。旧 `/messages` 仍仅登记。
- 独立复核发现：合法 20,000 个非 BMP 字符超过模型 UTF-8 字节上限时曾返回原始 500。已在 HTTP 登记边界窄转换为固定 422；草稿保留，消息、attempt 和供应商调用均为 0。原反例不改断言，修后通过。

## 最终验证

|项目|本轮实际结果|
|---|---|
|受影响回归|145 个不同用例通过，0 失败/错误/跳过，exit 0，JUnit 86.360 秒；新增 53 项包含其中，不重复相加。|
|源码一致性|回归前后 351 份明确选择的源码、测试和配置摘要一致；最终检查仍一致。|
|独立 Spec|初始 7 项通过，字节边界反例 1 项有效失败后原断言修后通过；不是修后重跑全部 8 项。|
|独立 Standards|6 项通过，exit 0，0 未关闭问题。初次 harness 2 失败/4 通过因遗漏初始化，仅修正 harness，不计为产品缺陷。|
|开发门|默认安全配置、来源、依赖、schema 四项 exit 0；13 来源保留 13 条未生产批准提示，55 运行依赖及 1 构建依赖已核对。|
|最终 Windows 冻结后端|实际新 EXE 启动/登录/首页读取/未配置生成拒绝、管道关闭退出与端口释放、schema/标记/SQLite 完整性共 3 组通过；模型记录全为 0。|
|独立冻结合成链|真实本机 HTTP → 真实适配器 → 回环假供应商，共 5 组通过；正常、取消、关停未知共 3 次上游 POST，3 attempts/3 receipts/1 内部待核候选，重放及重启不新增 POST。|
|构建输入|203 份输入构建前后及最终核验一致；聚合 SHA-256 `2c41065f3601970d95ee9983a4f83255fc829a0dadc6a759cdd909a05ca94ae5`。|

回归实际命令及逐项身份见 [command](final-regression-command.json) 与 [JUnit](final-regression.xml)。这是针对受影响功能的回归，本轮未重跑完整测试套件；2026-10-17 的全套 2,350 项覆盖属于上轮证据。最终 session 29924 已结束，不要等待或重复启动。

后端冻结目录 546 文件、96,165,036 字节；独立测试帮助程序 546 文件、96,153,268 字节。两者是分别构建的目录包，不合并计入应用大小，也不是安装器大小。实际后端 EXE SHA-256 为 `0c6bb42804e1bc60d54bf3e78a9a8fcb36b29a2e6ddb03db475b1f43895b54b1`。单次 ready 1.362 秒、单次登记约 0.047 秒只是观测，不是冷启动、内存或性能验收。本片不宣称包体继续减小；核心未增加运行依赖，原按需加载和 Electron 语言资源策略保持。

## 可核对证据

- [数值汇总](summary.json)、回归 [前摘要](final-regression-source-before.json)/[后摘要](final-regression-source-after.json)、构建 [前摘要](frozen-final-source-before.json)/[后摘要](frozen-final-source-after.json)。
- [独立规范复核](independent-spec-review.md)、[独立标准复核](independent-standards-review.md)、[标准复核源码摘要](standards-reviewed-files.json)。独立探针与各自原始 JUnit 同目录保存，不计入正式 145 项。
- [冻结后端回执](frozen-final-backend-smoke.json)、[冻结合成链回执](frozen-native-http-run/report.json)。构建日志原样保留，允许的可选导入警告不被改写成零警告；真正冻结执行与开发依赖检查分别记录。
- 初始契约失败、生命周期失败、事件循环容量失败及 Unicode 边界失败保留对应 `*-red.xml`。旧的重叠 GREEN、不完整的合成响应、检查脚本变量冲突及修复前构建均只作历史，不计入最终通过。

原始执行位置是 `.local/chat-generation-http-20261019/`；归档脚本保存原路径语义，不能在本证据目录直接运行并期待构建产物存在。实际命令顺序为：目标 pytest（见 command JSON）、四开发检查、`frozen_build_final.ps1`、`.venv/Scripts/python.exe -X utf8 .local/chat-generation-http-20261019/frozen_backend_smoke_final.py`、独立冻结 `qx-http-probe.exe` 接收独立合成输出目录。最后一条使用真实冻结程序，未通过 pytest 或原生 Python 伪装。原始数据库、测试工作区、安装包和完整程序产物均不入 Git。

`manifest.json` 仅列本目录证据文件的准确字节摘要（不包含 manifest 自身），由 Git `-text` 保留；源码摘要另有范围，不能将“证据文件一致”当作产品正确性证明。

提交核对另发现既有换行差别：回归输入中 12 份、构建输入中 1 份（包含在前述 12 份内）在工作树为 CRLF，基线 Git blob 为 LF；逐字节验证除换行外完全一致，且基线 blob 未变。详见 [回归差别](final-regression-git-byte-differences.json) 与 [构建差别](frozen-final-git-byte-differences.json)。本轮实际执行/构建摘要描述工作树原始字节，不能称这些旧文件与 Git blob 原始字节一致。没有为消除差别重写旧文件；本轮改动的产品和正式测试文件均与暂存 blob 字节一致。

## WorkBuddy 与下一步

用户重新打开专用会话后，前段两次仍busy，旧任务wait返回unknown；只读核对所见旧记录/活动JSON问题保留历史，未清状态或重试。产品提交eccea9a后，新的实时状态已connected；新任务wb-151ff422094a完成限定3文件只读复核，3次Read回执、end_turn、无错误/发现。主代理独立核对其题设外前提并收窄措辞，见[本轮协作核对](workbuddy-root-check.md)及[脱敏回执](workbuddy-review.json)。这证明本轮完成一次协作，不代表以后持续在线，也不替代运行验证。

下一步按 [HTTP/首页准备](../../../plans/2026-10-17-main-model-http-readiness.md) 接页面：发送与草稿状态分离、使用原请求 ID 找回不确定结果、当前权限读取内部待核候选、来源回原消息，保持中文输入、迟到结果隔离、附件与技能限制。以同一条合成链验证浏览器与开发 Electron。可信设置及日常授权解析器随后接通，不能把固定测试摘要清单作为律师操作方式。Jev、自动档案和后续 CH 任务独立推进。
