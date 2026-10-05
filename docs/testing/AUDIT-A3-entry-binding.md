# A3：源包启动绑定守卫

日期：2026-10-05。范围：当前 Codex 本机适配源包与既有两个离线工具；不是宿主加载、ChatGPT 连接或法律能力验收。

## 本切片结果

已添加 `src/cn_contract/mcp/bound_entry.py`，仅使用标准库先检查绑定，再延迟导入既有 `offline_server.main`。现有离线服务、业务 DTO、案件或候选接口没有在本切片改写。源配置版本由 0.1.2 改为 0.1.3；项目 Python command/cwd 不变，args 改为 `-I -X utf8` 和守卫文件的固定绝对路径。

使用直接脚本入口，是因为 `-m cn_contract.mcp.bound_entry` 会先运行已有 `cn_contract.__init__` 并导入领域代码，不能满足失败启动前不导入业务的要求。`-I` 是解释器路径隔离选项，不是 OS 沙箱。

**本切片尚未冻结运行绑定。** 旧 `plugins/qx-contract-offline-codex/runtime-binding.json` 未改，实际 SHA256 保持 `23a06b68547afd25db8e1596fa7f06138b8c411c5edfa59a00673fce4f45587b`。其 v1/0.1.2 快照已经过时，新守卫拒绝是预期行为。源码完成后由父任务统一生成 v2 绑定并执行成功入口检查；本切片不能称当前源包已经可启动。

## 实际检查边界

固定读取当前项目源包的绑定路径，不提供 MCP 参数、任意绑定路径或环境覆盖。v2 要求完整且精确字段集合、项目根、守卫/离线模块路径、0.1.3 源配置、预期两工具和关闭状态。

文件集合独立枚举当前 `src` 中全部 `.py/.js/.css/.html`，包括未跟踪、隐藏、嵌套及大写扩展名文件。另覆盖原五项配置/锁元数据、原四份固定虚构 DOCX 及 provenance、两个当前源 manifest。字节 hash 与集合均一致才通过；仅逐个校验旧清单不能放过新源文件。一般文档、其他扩展名、缓存 `.pyc` 及已安装 wheel 字节不在此 hash 范围内。

锁内运行依赖、build 依赖及当前项目 distribution 的版本须与已安装元数据一致。当前真实锁是 55 运行包、1 build 和项目自身，共 57 个版本；纯单元测试使用独立虚构的小锁。Python 完整版本也同时核对锁、绑定和解释器。

默认配置须保持 provider mock 与 QCC 严格 false，即使有人重新计算绑定也不能仅凭改变默认值开启真实调用。入口不启动新协议、不读案件或凭证，仍调用原两个受限离线工具。

拒绝重复 JSON 键、非 UTF-8、JSON 特殊浮点常量、过大绑定或受控文件、坏 hash、额外/遗漏映射、相对或越界路径、已知 symlink/reparse 和受控文件 hardlink。名义祖先先检查再 resolve，避免 resolve 隐去链接。入口只显示固定 `BOUND_ENTRY_REJECTED`，不输出输入内容、异常详情或私人路径。

构建编号是除 `build_id` 外的完整绑定规范 UTF-8 JSON 的 SHA256 前 32 位，前缀 `qx-offline-source-0.1.3-`；校验时重算。它是绑定内容指纹，不是数字签名或第三方批准。

## 真实测试与证据

命令使用本项目 `.venv/Scripts/python.exe`；原始日志与 JUnit 保存于 `.audit-local/audit-a3-bound-entry-20261005/`，被 Git 忽略。以下是本切片实际结果，不是计划数量。

|步骤|命令范围|退出码|实际数量/结果|
|---|---|---:|---|
|首次 RED|`-m pytest tests/unit/test_mcp_bound_entry.py -q --tb=short`|1|56 failed，0 errors；守卫文件缺失断言|
|初版 GREEN|同目标|0|56 passed，0 errors/skips/warnings|
|构建编号 RED|同目标，加入合法任意 label 反例|1|1 failed / 56 passed，0 errors|
|构建编号 GREEN|同目标|0|57 passed，0 errors/skips/warnings|
|最终目标/相关回归|守卫、offline/progress 单元；offline STDIO、host metadata、progress wire 集成|0|179 passed，0 errors/skips/warnings；守卫目标 62 项|
|当前源入口检查|`-I -X utf8 src/cn_contract/mcp/bound_entry.py --check`|78|v1 旧绑定被拒；固定错误码，无工具启动|
|只读 capture helper|直接脚本命名空间调用 `build_binding_snapshot(root)`，未写绑定|0|当时 97 源/选定文件、57 依赖版本；`binding_written=false`；并行源码未冻结，数量不是最终源包声明|

最终相关回归命令：

```text
.venv/Scripts/python.exe -m pytest tests/unit/test_mcp_bound_entry.py tests/unit/test_mcp_offline.py tests/unit/test_mcp_progress_unicode.py tests/integration/test_mcp_offline_stdio.py tests/integration/test_mcp_host_metadata.py tests/integration/test_mcp_progress_tokens.py -q --tb=short --junitxml=.audit-local/audit-a3-bound-entry-20261005/target-regression.xml
```

其中三个直接 CLI 负例（STDIO、check、未知参数）均实际退出 78、stdout 空、stderr 固定码；另外两个新子进程安装导入哨兵，拒绝时从未尝试导入 `cn_contract`/`mcp`/`mcp_types`。单元正例验证纯检查无业务或 SDK 新导入、check 输出范围、先验证后 import 的顺序与 STDIO 启动无额外 stdout。单元成功启动使用测试替身；当前真实源绑定尚未冻结，成功的真实守卫 STDIO **NOT_RUN**。相关旧 STDIO 回归通过不代替这一成功入口验收。

原始文件：`red.xml/red.txt`、`green-first.xml/green-first.txt`、`red-build-id.xml/red-build-id.txt`、`green-build-id.xml/green-build-id.txt`、`target-regression.xml/target-regression.txt`、`current-source-check.txt` 及 `execution-ledger.json`。首轮 RED 曾用读取日志的 shell 包装，其包装退出 0；在实现前已重新执行同目标并明确传播 pytest 退出码 1，记录采用后一次真实退出码，未把包装码误记为测试通过。

## 父任务冻结接口与剩余事项

`inventory_repository_files(root)` 是只读完整枚举/哈希接口；`build_binding_snapshot(root)` 是只读 v2 payload 生成接口，构建编号自动派生，不接受自报 label。为避免包级导入，可用标准库 `runpy.run_path` 在不等于 `__main__` 的命名空间读取守卫文件，再调用该函数。根目录须是绝对 `Path`，进程须为当前项目解释器。函数不会写绑定、安装或刷新宿主。

父任务应等所有源码稳定后，保存旧快照证据、生成并写固定源绑定，执行固定绝对脚本 `--check` 和真实 SDK STDIO 握手/两工具有限调用，再记录实际文件数、构建编号和 artifact hash。若再次改变被绑定源码，需重新冻结，不能继续沿用旧编号。

本检查对象是当前项目源包，活动缓存 manifest/实际 loaded root/宿主聊天调用没有被验证。没有全局 reload、缓存改写、宿主模型 turn、网络请求、依赖安装、账户/许可接受、付费、真实资料或发布。

执行中的 Python 和守卫本身仍是可信启动前提；本机有权同时改写守卫和绑定的主体不受其隔离。校验与后续导入之间仍有 TOCTOU，源码/依赖运行中变化也未防御。已安装版本不证明依赖字节或 `.pth`/OS 行为，known-link 拒绝不证明系统免疫。生产、正式签发、真实模型/QCC、法律 gold、宿主/ChatGPT 连接继续分别阻断或 NOT_RUN。

## 独立审阅 P2 修复：项目 distribution 自引用

独立审阅实际跑原 62 目标通过，但 23 个隔离探针中有 2 个错误接受，原始证据保留在 `.audit-local/audit-a3-entry-review-20261005/`。`_locked_versions` 汇总 runtime/build 后无条件加入项目自身版本，把锁内同名 `qx-contract-workbench==9.9.9` 覆盖为项目的 `0.1.0`；因此不能保证每个锁条目都接受已安装版本核验。这是结构校验缺口，未证明远程利用或本机权限突破。

最小修复：项目 distribution 只由 `pyproject.toml` 单独声明；若 runtime 或 build 汇总已含 `qx-contract-workbench`，直接拒绝，包括同版本重复条目。不修改真实锁，也不把其自引用当合法依赖。

新增两个正式测试分别针对 `packages` 与 `build_packages`，各覆盖 `9.9.9` 和同版本 `0.1.0`，完整重算实际文件 hash 与绑定构建编号，再核对 verification 和 snapshot helper 均拒绝。失败测试先于实现，原独立错误接受证据没有覆盖。

|步骤|实际结果|退出码|
|---|---|---:|
|新增目标 RED|2 failed / 62 passed；完整重绑后的自引用未被拒绝，0 errors|1|
|修复后目标与原相关回归|181 passed，0 errors/skips/warnings；守卫目标现在 64 项|0|

修复证据另存 `.audit-local/audit-a3-bound-entry-repair-20261005/`：`red.txt/red.xml`、`target-regression.txt/target-regression.xml` 和 `execution-ledger.json`。命令范围与前述最终目标/相关回归相同，JUnit 路径改为该新目录；未运行全套。真实依赖锁 SHA256 仍为 `32403ab026ebce63e3d6f336289b713a1aab2023ad5719a755b3f56da7fe6693`；旧绑定 SHA256 仍为 `23a06b68547afd25db8e1596fa7f06138b8c411c5edfa59a00673fce4f45587b`。当前真实锁没有同名项目自引用，原 57 个版本无需调整。

本次仅修复守卫、其测试并追加本记录。插件源配置、实际 runtime 锁、旧绑定、其他业务代码与宿主/缓存保持未修改。本作者回归不是原 23 探针的独立复验；修复后独立结论及最终真实入口冻结由父任务另记，成功 bound STDIO 仍 NOT_RUN。

## 最终父任务冻结与独立实际入口核验

2026-10-05 原独立23探针有限复验全部符合预期，64目标通过；原两个版本自引用错误接受反例已关闭，原反例记录保留。随后所有业务源码停止修改，父任务保留旧 v1 快照，08:17:43 UTC 实际写入源包 v2 绑定：100文件、57版本、构建编号 `qx-offline-source-0.1.3-bd6518818b05ba45094fe2e8f1040be9`，新绑定 SHA256 `f05533c8aa92c4339efaac38b9825c72b0f0042f54a09c5677040ccc72925606`。

提交前的只读 Git 过滤检查发现：101个绑定文件/新虚构清单对象中5个会被LF转换，导致已测字节与提交后的字节不同。父任务增加 `.gitattributes` 精确字节条款，保留已审源 bytes，未为迁就Git重写源码；修复后101/101一致。此项是实际发布字节检查，不计作5个业务缺陷或pytest用例。

|实际运行|退出码|结果|
|---|---:|---|
|固定绝对路径 `bound_entry.py --check`|0|BOUND_ENTRY_VERIFIED；当前派生构建编号相符|
|父任务通过实际SDK调用固定守卫|0|10有效工具调用，含4类型×2操作的8人工示例；2非法参数固定拒绝；拒绝后恢复，session正常结束，stderr空|
|独立 final source freeze 检查|0|独立枚举100/100hash、57/57版本、canonical build_id及101/101 Git过滤字节一致，3.82秒|
|独立固定配置原样启动原始STDIO|0|6响应+1通知；4工具调用包含2状态、1人工nda示例、1固定拒绝；恢复后stdin EOF自然child退出0，stderr空、stdout均JSONRPC|

父任务SDK初次核验使用了错误的 `InitializeResult.serverInfo` 属性，已安装SDK为 `server_info`，该辅助脚本失败退出1，不计产品RED；修正后上述真实入口调用通过。独立核验前后100库存和7个观察hash稳定。

父证据 `.audit-local/audit-parent-20261005/` 中保留历史绑定、最终绑定冻结、Git前后字节检查、check/SDK日志；独立最终报告 `.audit-local/audit-a3-entry-review-20261005/parent-freeze-recheck/REPORT.md`。本次没有改写全局配置、缓存、Marketplace安装记录或启动宿主模型turn，源验收不等于宿主刷新/聊天调用。当前聊天工具库存仍没有目标两工具；ChatGPT连接和案件/身份/文件桥仍NOT_RUN或未实现。依赖字节、许可批准、OS硬限、运行中变化防御和生产边界均未被这些数量证明。
