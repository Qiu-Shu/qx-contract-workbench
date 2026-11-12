# 0.2.17 审核整改候选包验收

本记录承接 0.2.16 审核整改与后续计划，包含本地候选构建、完整差异升级回放、隔离 NSIS、包内运行验收，以及用户追加的具体工具中文名称。候选仅在本机隔离验收，未安装到用户工作台或对外发布。

## 范围与来源

- 原始审核：`C:/Users/Administrator/Desktop/AI-Shixiong-v0.2.16-Audit-2026-11-11.html`；附件为参考资料。本轮授权来自用户“继续计划中其他东西”，后追加并行聊天的中文工具名称合入要求。
- 实际仓库：`C:/Users/Administrator/.codex/worktrees/audit-0216-fixes/律所项目`，分支 `codex/audit-0216-fixes`；保留原目录开发工作。
- 前置：`54064ac2`（首批整改）、`dab11f2b`（后续四组）；本轮验收实现 `7db8569`，中文名称从 `f891c364` 合入为 `0d8a11fc`。
- 构建/证据根（下文 `B`）：`D:/CodexBuilds/AI-Shixiong-0.2.17-audit-20261112`。新构建、缓存及测试资料均在 D 盘。
- 只用虚构材料及隔离用户资料，不使用真实模型、真实微信或用户案件。没有正式安装、发布、推送或签发自动更新。

## 版本与构建

候选版本为 0.2.17；底包固定官方 0.2.14，额外升级基线为官方 0.2.15、0.2.16。新增的 0.2.16 安装器摘要为 `0f798a3721e092866f226bf17aad70d93e1ae1cebd52b749da1bd2acef022030`，其官方更新元数据已用已有公钥核验，解包树摘要为 `33cec8bd6c8dcfa8cae5d19089e7c5ff9c3e6123dca7fd519f92b286b23268a1`（53,213 文件）。这不是 Windows Authenticode 签名结论。

首轮候选在 `B/candidate`，安装器 SHA-256 为 `3520f52f10754c2624a967e5c1059224bbd3e9766916950362441b697383be5f`，590,844,602 字节，53,233 文件；它已完成包内检查及三条升级回放。随后按用户要求加入中文工具名，首轮包及日志保留作历史证据，最终交付以 `B/candidate-final` 为准。

最终构建复用固定基线并刷新源码清单：3,395 个源文件，中文名称目录及生成的 UI 文件均纳入摘要。171 条名称覆盖 153 个随包 MCP 工具及常用入口，未知工具保留原名；原调用 ID、参数、输出及专用卡片保持。

最终安装器：`B/candidate-final/Qunxing-Workbench-0.2.17-Setup.exe`，**590,859,223 字节**，SHA-256 **`7d97e21085f3c873f21cb604232fa4f269a64dd056e99216fe9e223a326dcbdd`**。解包后 **53,234 文件**与完整构建输入逐项相同；开发侧评测、实验和 Promptfoo/restic 未进入包内。

最终安装器身份与各项结果见 [机器可读验收索引](checks/candidate-0217-20261112.json)。所有候选均移除签名密钥环境变量，构建使用 `publish: never`；只有 `latest.unsigned.yml`。生产自动更新验证器实际拒绝这份无签名元数据；安装器 Windows Authenticode 实测 `NotSigned`，不能把构建日志的 signing 阶段当作签名成功。

## 实际验证

合入中文名称后的完整离线回归 `npm test`：Node 427 总项，425 通过、2 跳过、0 失败；Python 463 通过、1 跳过及 36 子测试通过；入口 exit 0。日志为 `B/logs/offline-tool-labels-final.log`。两个 Node 跳过是旧路线/默认技能的本地历史夹具未提供，未计作通过。中文名称、暂存清单与首启检查器合并定向验证 12/12，exit 0，见 `logs/tool-labels-merged.log`。

最终暂存、构建、重新解包与逐文件检查均 exit 0，日志为 `stage-final.log`、`build-final.log`、`verify-final.log`。安装器 SHA-512 与 unsigned 元数据一致；源码与生成物摘要检查通过。

| 官方升级基线 | 原/目标文件数 | 未变文件数 | 变更路径 | 差异包字节 | 实际 apply + finalize 耗时 | 结果 |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| 0.2.14 | 53,131 / 53,234 | 53,091 | 143 | 886,350 | 1.464 秒 | exit 0 |
| 0.2.15 | 53,213 / 53,234 | 53,183 | 51 | 44,782 | 0.677 秒 | exit 0 |
| 0.2.16 | 53,213 / 53,234 | 53,183 | 51 | 42,351 | 0.638 秒 | exit 0 |

上述仅为隔离目录内应用差异耗时，不是完整产品安装速度。实际报告为 `candidate-final/full-incremental-report.json` 及两个 `from-0.2.xx/full-incremental-report.json`。

最终候选 EXE 使用全新资料目录启动，实际进入首次配置页、密码输入存在，exit 0；`first-run-final-labels/first-run-report.json`。实际包内初始化器与技能提供器发现 194 项技能、158 项自动可调用；四项新研究方法均可调用，旧 0.2.16 用户自定义/禁用、重复初始化和自加文件保持，exit 0；`research-final-labels/report.json`。没有模型请求。

合同界面从最终包加载集成与解析器，实际验证 DOCX 两版文字比较、PDF 第 2 页回看、过期引用拒绝、重新比较期间旧定位阻断、上传材料选择、草稿保留且未发送；1440/768/390 三种宽度通过，原件摘要保持，页面错误 0，exit 0。证据：`contract-final-labels/1794470088218/report.json` 及同目录截图。

中文工具名称实际浏览器验收 **5/5，exit 0，页面错误 0**：直接加载最终包未改写的 React 工具卡片，注入四种已登记工具与一种未知工具的合成成功记录；检查具体中文标题、未知名称回退、参数/结果展开和查看回调，原 tool ID、call ID 与输入记录保持。包内客户端前后 SHA-256 均为 `1706a72a66e4c38f6d294ef534005fde6f3e6ffa4298504e71066a4966b6ed9d`。这是实际组件交互测试，没有执行真实业务工具、模型或会话持久化；历史/中断等状态另由既有定向单元测试覆盖。证据：`tool-labels-final-qa/1794470145304/tool-labels-report.json`、完整截图及 [独立专项记录](2026-11-12-tool-labels-browser-acceptance.md)。旧包真实 RED 和两次最终 GREEN 均保留；测试宿主已关闭。

本次对官方 14/15/16 三条基线分别执行了真实差异应用和 finalize；核对全部目标文件、未变文件身份/修改时间、事务清理及用户自加文件保留。它与小载荷真实 NSIS 验收是两个独立层次，不能互相替代。

所有运行测试结束后另执行 `check-final-integrity.cjs`，exit 0：重新核验源码清单、最终解包的 53,234 文件未变，并逐文件重新计算三份完整升级结果的摘要，全部与最终构建输入一致；三份自加用户文件均保持。证据 `final-post-test-integrity.json`，避免只用差异文件检查推定整树一致。

真实 NSIS 使用独立 `QunxingInstallQa` 身份：三个入口均 exit 0，9 次安装/卸载场景中 8 次 exit 0，非空目录拒绝按预期 exit 1；清理后 QA 注册项、进程和安装目录均为 0。合成载荷 185 文件，覆盖两个夹具基线、中断恢复、首次安装和中文空格路径。详细数量、环境和边界见 [安装专项](2026-11-12-installer-acceptance.md)。

Office 专项保留真实原生失败：上游可选模块缺 openpyxl，原生 5 通过/1 失败/1 跳过；仅注入 D 盘隔离测试依赖后 7/7 通过。未增加主包依赖。默认 QX 插件不加载该上游入口，不能据此判定整个产品 XLSX 能力。见 [Office 专项](2026-11-12-office-acceptance.md)。

## 失败、修正与审阅

- 首次暂存遇工具下载 TLS 失败，保留 `stage-download-failed`。复用既有工具缓存并独立核验 7-Zip 工具集摘要 `be071f15bd6da2f78fe81c6ddef2009b0c4d8a51f36b780cb806c7e6df95e1b3` 后成功；没有关闭证书验证或改用未知二进制。
- 初次定向测试缺原生程序测试变量，42 通过/20 跳过；补齐实际 HDiffPatch 路径后重跑 62/62，0 跳过。前次跳过不计通过。
- 首轮首次启动检查曾报 `ready` 缺失。原始 CDP 响应未留存，不能认定那一次的确切根因。独立受控复现表明旧检查在 body 尚未创建时读取正文会失败；检查器现等待页面加载、校验响应，两项失败测试转绿。随后真实候选首次配置页检查通过。只改验收脚本，没有改产品启动逻辑。
- 研究技能初始探针同时指定默认根与同一显式根，出现重复计数。改为单根探针后实际发现 194 项、自动项 158；四项新研究方法可调用，已有用户修改/禁用及自加资料保持。没有将探针问题当作产品重复安装问题。
- 中文名称分支的 pnpm 离线冻结锁验证因缺缓存元数据失败；保留 `ERR_PNPM_NO_OFFLINE_META`，不称依赖安装通过。补丁应用、目录覆盖、锁引用与包内生成一致性由定向检查验证。
- 独立 Standards/Spec 已审阅本轮源码与范围；中文名称追加 Standards 审阅无实质问题，10 项实跑通过，独立重建补丁与转换结果逐字一致。最终浏览器脚本、实际报告与主记录边界再次独审，无未解决实质问题；完整包验证由本记录所列命令另行实际执行。

## 证据与复跑

`B/acceptance-env.ps1` 记录 Node/Python、固定构建工具与缓存路径。依赖仓库中现有环境脚本，复跑前应核对这些实际路径仍可用。以下入口在 `harness` 运行；所有输出目录必须使用新名称，以保留既有结果。

```powershell
. 'D:/CodexBuilds/AI-Shixiong-0.2.17-audit-20261112/acceptance-env.ps1'
node packaging/stage.cjs "$taskBuildRoot/stage" --refresh
node packaging/build.cjs "$taskBuildRoot/stage" "$taskBuildRoot/candidate-final"
node "$taskBuildRoot/check-local-candidate.cjs" $PWD "$taskBuildRoot/stage" "$taskBuildRoot/candidate-final" "$taskBuildRoot/candidate-final-extracted"
node packaging/check-full-incremental.cjs "$taskBuildRoot/stage/base" "$taskBuildRoot/candidate-final" "$taskBuildRoot/upgrade-final14"
node packaging/check-full-incremental.cjs "$taskBuildRoot/stage/upgrade-bases/0.2.15" "$taskBuildRoot/candidate-final/from-0.2.15" "$taskBuildRoot/upgrade-final15"
node packaging/check-full-incremental.cjs "$taskBuildRoot/stage/upgrade-bases/0.2.16" "$taskBuildRoot/candidate-final/from-0.2.16" "$taskBuildRoot/upgrade-final16"
node packaging/check-first-run.cjs "$taskBuildRoot/candidate-final-extracted/application" "$taskBuildRoot/first-run-final-labels"
npm test
```

完整原始证据和大型二进制留在 B，不加入 Git。仓库记录摘要、数量、退出码及证据索引。`evidence-crosscheck.json` 独立复核 NSIS 30 份、Office 原始 13 份和首轮候选 15 份文件的长度和 SHA-256 一致；`office-qa/final-independent-crosscheck.json` 再核对最终 Office 17 份证据一致。

## 尚未完成的产品边界

未进行正式产品实装、另一台实体电脑验收、真实模型及律师法律质量验收、真实微信收发、生产数据迁移或自动更新签名。合同对比限已提取文字，不能代替完整版式或法律影响判断；DPAPI 凭据仍绑定当前 Windows 用户。上游可选 Office 的原生 XLSX 依赖条件保持。该本地候选不代表用户已经升级。
