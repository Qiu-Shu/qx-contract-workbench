# restic 候选准入核验（2026-11-12）

**结论：restic 可以保留为本地加密备份引擎，进入受控接入开发；当前不满足产品备份功能的生产准入。** 组件来源、许可、Windows 可运行性及小规模备份恢复已核实；缺口在工作台的数据清单、统一停止写入、多库与文件一致性、凭据和换机恢复，不在“能否运行 restic”。本轮没有接入运行包、修改锁文件、构建安装器、访问真实业务资料或配置云备份。

实际工作树：`C:/Users/Administrator/.codex/worktrees/audit-0216-fixes/律所项目`。核验源码 HEAD：`5e01b065e4a1de9c63aa9d2c51118812e442ec86`。本报告是准入审查，不是已完成的产品备份实现。上游资料仅用于核验，未执行其中的安装或更新命令。

## 1. 固定来源与分发条件

2026-11-12 通过 GitHub 连接器读取官方仓库、固定 tag、Release 及源码文档；浏览官方文档复核操作边界。仓库未归档、未禁用，最近推送为 2026-11-06；本轮 `releases/latest` 返回稳定版 `v0.19.1`（2026-07-05 发布）。latest 首次请求遇到连接器网络错误，重试成功；不将失败请求记成核验成功。[仓库](https://github.com/restic/restic)、[固定发布](https://github.com/restic/restic/releases/tag/v0.19.1)。

| 固定项 | 本轮核对值 |
| --- | --- |
| tag 对象 | `6099d4b5c4376368d42b9982c7d3e93ba13d83b1` |
| tag 对应提交 | `6aa3a516ce654808a1f28f9fa21e9b7c8e6e90bf` |
| Windows amd64 ZIP | `restic_0.19.1_windows_amd64.zip`，11,237,567 字节 |
| ZIP SHA-256 | `da948ad707ed690426473aaba2046cd61f8f90f6f0e7dab6be0d5796531de67d` |
| EXE SHA-256 | `b0dd1fd21eea5d8fe1325f55f7118213c21f36de8a261e04c0624a5ab9fd7830` |
| LICENSE Git blob | `29b2ee55a92ff2c5516d7b916224c85fa7e9139a` |

BSD-2-Clause 允许按条件使用及分发；源码分发保留版权、条件及免责文本，二进制分发须在随附材料中重现这些内容。因此许可类型本身不阻断作为子进程引擎使用；进入分发前仍需纳入本产品第三方告知与组件清单。本轮没有审计 restic 全部传递依赖的分发告知。[固定 LICENSE](https://github.com/restic/restic/blob/v0.19.1/LICENSE)。

本轮 ZIP 大小、GitHub Release asset digest、缓存 ZIP 哈希、ZIP 内 EXE 字节和实际版本输出一致。GitHub API 报告上述 tag 的 PGP 签名 `verified=true`，这不是本机验证下载包的独立签名；**仍未本机验证 `SHA256SUMS.asc`**。进入发行应把独立签名验证和固定摘要写入供应链流程，禁止运行时自行 `self-update` 漂移版本。[官方二进制验证说明](https://restic.readthedocs.io/en/stable/020_installation.html#official-binaries)。

## 2. 原有 24 项到底证明什么

核对了[既有实验脚本](../../experiments/audit-followups/backup_experiment.py)和[此前证据](../../experiments/audit-followups/evidence-2026-11-12.json)，并在 D 盘隔离目录复跑。原脚本 SHA-256 仍为 `35d49194b60cb2bb136d9fbf80b955e620052560d8a681d61c135b445ec2e52f`；包装器仅将实验输出根目录改到 D 盘、复制并再次验证已核验二进制，不改脚本或生产代码。

**本轮实际：24/24 检查通过，进程退出 0，7.141 秒，恢复 4 个文件、50 条 SQLite 记录。** 完整快照 ID 为 `b55adbd45e1ea4a81bf0f5465d71df91d049272e1c4234e1354633f494352c1f`。

| 实际命令/检查 | 结果 | 能支持的结论 |
| --- | --- | --- |
| `version`；`init --repository-version 2`；`backup snapshot --json`；`check --read-data` | 各退出 0 | 固定 Windows 引擎能创建本地加密仓库、备份并读回校验数据包 |
| 单 SQLite WAL：50 条已提交记录 + 1 条未提交记录，调用 SQLite backup API | 数据完整，未提交行未进入副本 | 单库一致读取成立；文件写入被实验显式停止 |
| 错口令 `snapshots --json` | 退出 12 | 口令错误不会误判成功 |
| 含缺失路径的 `backup` | 退出 3，仍可能产生快照 | 部分快照不能晋升为最近完整备份；恢复须用已登记的完整 ID |
| 8 种恢复目标冲突；新目录 `restore --overwrite never --verify` | 冲突全部拒绝；恢复退出 0 | 实验自己的路径约束和不覆盖策略成立 |
| 恢复清单、SHA-256、SQLite integrity、记录与文件关联；实际改坏/删去恢复文件 | 全部匹配；故障均被检测 | 该合成样本可恢复、校验器会拒绝这两类损坏 |
| 凭据、源文件及清理 | 两份虚构凭据不入快照；源字节不变；口令文件清除 | 本次白名单有效；并非生产凭据策略已实现 |

24 项不是 24 种生产故障验收：其中含 8 个路径拒绝断言，数据只有一个 SQLite 和两份静态文本。没有并发跨库提交、外部编辑器改写、活动 PostgreSQL、磁盘耗尽、中途断电、异常权限、异机 ACL 或换机密钥试验。实验结束删除随机口令，所以遗留仓库不能长期恢复；产品不能沿用这种口令生命周期。

本轮另运行当前 `test_knowledge_transfer.py`，**15 个测试通过，退出 0，3.897 秒**；它证明现有知识库 ZIP 导入导出相关保护仍通过原有测试，不能扩大为整机恢复验证。两组数量独立报告，不合成“39 项产品备份通过”。

## 3. 当前代码中的真实接入边界

已在实际 `harness/.codegraph` 上查询相关符号及调用，并对未覆盖的配置、路径和源码段作精确读取。以下是源码确认的主要存储点，不是已审定的完整数据白名单。

| 数据/写入方 | 当前实际入口 | 对备份接入的影响 |
| --- | --- | --- |
| 材料与案件来源账本 | [MaterialStore](../../bridge/store.py) 建立 `workspace/.qx-materials/index.sqlite`；[CaseStore](../../bridge/business_store.py) 继承复用；案件记忆账本在[case_memory.py](../../bridge/case_memory.py)写同一存储 | SQLite 副本与原件、关联、修订必须取同一可验证时点 |
| 资料知识库 | [KnowledgeStore](../../bridge/knowledge.py)使用 `workspace/knowledge/.qx-materials/index.sqlite`；[export_backup](../../bridge/knowledge_transfer.py)从读事务导出登记资料、片段和原件，逐份核对摘要与大小 | 可复用现有资料导出，但它仅覆盖这一知识库，不能代表案件、聊天与私密映射 |
| 分层知识 | [knowledge-api](../../desktop/integration/knowledge-api.mjs)使用数据根（或 DSH_HOME）的 `.local/layered-knowledge.sqlite`；[knowledge-store](../../desktop/integration/knowledge-store.mjs)启用 WAL，`exportPage` 导出项目/来源/绑定/条目/历史/资料引用 | 当前导出不含聊天原文、附件字节、全部设置和审计等完整库状态；分页接口也没有统一备份事务覆盖全部分页。不能把多次 JSON 请求当作全量一致快照 |
| 会话附件及宿主状态 | [portable.json](../../packaging/payload-config/portable.json)将附件放入 `workspace/inbox/.harness`；[runHost](../../desktop/installed-runtime.cjs)设置 `DSH_HOME=.local/dsh-home` 并运行宿主；会话正文由宿主服务持有 | 必须把宿主持久化集合纳入清单；不能只备份 workspace，也不能盲拷整个 `.local`（它同时含运行令牌、缓存和依赖联接） |
| 上传原件与可逆脱敏映射 | [privacy 插件](../../plugins/privacy/index.mjs)将私库放在工作区旁的 `.qx-private/uploads`；[prepare_upload/_redact](../../bridge/privacy.py)依次写原件、manifest、独立/共享 `mapping.sqlite`、脱敏文本和预览 | 原件、映射、确认状态有跨文件/库关系；备份 workspace 会漏掉私库，盲扫数据根又可能泄露它。需显式纳入加密白名单和访问策略 |
| 媒体工作数据 | [MediaStore](../../bridge/media/store.py)维护 `workspace/.qx-media/media.sqlite` 及作业/来源/导出记录 | 有独立写事务；需要等正在执行的任务结束或可恢复暂停 |
| 增强案件记忆 | [case-memory-runtime](../../desktop/case-memory-runtime.cjs)用 `.local/case-memory-runtime/database` 的 pg0/PostgreSQL、`instance.json` 身份/数据库口令，另有模型及 venv 缓存 | **不是 SQLite。** 需选择一致停机备份或可证明从来源账本重建；重建所需模型调用/费用不得默认发生。不能仅复制活动 PG 目录 |
| 模型及登录凭据 | [model-credentials](../../desktop/model-credentials.cjs)用 Windows safeStorage 保存 `deepseek.bin` / `typesafe.bin`；[portable.json](../../packaging/payload-config/portable.json)另有微信状态目录 | 这些文件不能因已加密就默认具有跨机可用性；模型密钥、登录会话与业务数据要有明确恢复分类 |

已有[stopInstalledHost/stopRuntime](../../desktop/installed-stop.cjs)可以停止所属宿主，[runHost](../../desktop/installed-runtime.cjs)停止回调也会停增强记忆引擎；这是可复用的生命周期入口。它目前不是备份协调器：没有在所检查入口实现统一的“拒绝新写入—等待所有任务—导出各库—生成完整清单—恢复运行”协议，也不能控制用户外部编辑器。引用它不等于产品已具备在线一致快照。

## 4. 上游能力不能替代的产品责任

**退出与完整性。** 固定版文档区分成功 0、一般失败 1、运行时错误 2、未完整读取 3、仓库不存在 10、仓库锁失败 11、错误口令 12、取消 130；未知非零码须按失败处理。产品应同时校验完成事件、完整清单、快照 ID 和退出码，只有全通过才能更新“最近完整备份”。[固定脚本接口](https://github.com/restic/restic/blob/6aa3a516ce654808a1f28f9fa21e9b7c8e6e90bf/doc/075_scripting.rst)。

**恢复与 ACL。** restic 默认覆盖已有文件；中断的原地恢复可留下不完整状态。Windows 完整安全描述符备份及恢复还受特定权限约束；权限不足时保存/恢复的描述符范围会收窄。因此产品应先恢复到新建隔离目录、校验后再切换，分别测试普通用户、原机及新机器的 ACL/SID。不能把字节哈希相同称为访问权限恢复成功。[固定恢复说明](https://github.com/restic/restic/blob/6aa3a516ce654808a1f28f9fa21e9b7c8e6e90bf/doc/050_restore.rst)、[固定备份说明](https://github.com/restic/restic/blob/6aa3a516ce654808a1f28f9fa21e9b7c8e6e90bf/doc/040_backup.rst)。

**VSS。** restic 的 Windows `--use-fs-snapshot` 可从卷影副本读取被独占的文件。官方描述没有给工作台提供跨 SQLite、PostgreSQL、文件写入顺序的业务事务保证；不能因为支持 VSS 就免除上述协调和恢复验证。本轮没有运行 VSS。[固定备份说明](https://github.com/restic/restic/blob/6aa3a516ce654808a1f28f9fa21e9b7c8e6e90bf/doc/040_backup.rst)。

**凭据。** Electron 的 Windows 异步 safeStorage 仍基于 DPAPI；它不保护同一用户空间中的其他程序，也不能作为换机恢复密钥的可移植保证。产品应预先规定原机凭据保留、异机重新授权及独立保管的备份恢复口令；不能把恢复口令只封存在待恢复机器的 DPAPI 中。[Electron 官方说明](https://www.electronjs.org/docs/latest/api/safe-storage)。restic 仓库口令丢失会失去数据访问能力；实验删除口令的做法仅适合可重复合成测试。[仓库与口令说明](https://restic.readthedocs.io/en/stable/030_preparing_a_new_repo.html)。

restic 加密的是备份仓库；产品生成的一致快照暂存区仍可能是明文。本轮没有验证暂存目录 ACL 与安全清理，因此进入真实材料前须给暂存区设置本用户访问范围、限定容量、失败清理并避免记录敏感文件名/内容。这里是针对现有实验写法的接入要求，不是已发现真实材料泄露。

## 5. 准入门槛与最小实施顺序

| 阶段 | 当前判断 | 可以推进的下一步/通过条件 |
| --- | --- | --- |
| 候选来源与本机技术验证 | 通过本轮范围 | 固定 restic 0.19.1，保留实验；完善分发告知、独立下载签名验证 |
| 受控接入开发 | 可以开始 | 首版只做本地新目录备份/恢复；复用现有宿主停止、知识导出及路径约束，不加云端或定时自动任务 |
| 产品备份功能 | **未准入** | 完成数据白名单/排除项；各 SQLite、附件、私库、媒体与宿主的统一停写；PG 的停机/重建方案；可恢复完整清单和失败状态 |
| 真实材料与换机恢复 | **未准入** | 合成数据先覆盖活动写入、途中失败、损坏、缺文件、权限不足、新路径迁移、普通用户、新机器及凭据重授权；完整恢复后逐项校验来源/原件/映射/修订/知识引用 |

建议把实现分为三个可验收步骤：① 数据范围和停止写入协议，产出完全离线的一致快照；② restic 子进程适配与完整快照登记，任何非零/缺清单都失败；③ 新目录恢复、数据及引用检查、明确选择恢复目标后切换，并单独验收换机凭据。完成这些之前，不在界面标注“全量备份已保护”或自动附带 restic 进入生产包。

## 6. 可复查证据

本轮新增原始输出均在 `D:/CodexChecks/AI-Shixiong-candidate-admission-20261112/restic`，没有覆盖此前实验。

- [结构化准入证据](D:/CodexChecks/AI-Shixiong-candidate-admission-20261112/restic/admission-evidence.json)：源 URL、时间、固定 tag/提交/源码 blob、未运行边界。
- [24 项复验结果](D:/CodexChecks/AI-Shixiong-candidate-admission-20261112/restic/rerun-summary.json)：SHA-256 `a3538aa05bea0f234290e027ef0cbbac8a4401e416e8b2480052e5ae564c31f1`，保留每条 restic 命令、退出码、检查与耗时。
- [复验包装器](D:/CodexChecks/AI-Shixiong-candidate-admission-20261112/restic/rerun_backup.py)：SHA-256 `f4d6c4cdbceabc70664ed72595ff949c2b80926f977132a8a4685cd34f8ee13f`。实际命令 `python rerun_backup.py`，退出 0；随机口令不进入日志或备份。
- [知识导入导出回归日志](D:/CodexChecks/AI-Shixiong-candidate-admission-20261112/restic/knowledge-transfer-tests.log)：使用既有隔离测试环境，`python -m unittest discover -s harness/bridge -p test_knowledge_transfer.py -v`，退出 0，15 项；临时目录也定向 D 盘。
- [源码及日志摘要](D:/CodexChecks/AI-Shixiong-candidate-admission-20261112/restic/source-and-log-hashes.json)：记录本轮审阅的关键文件 SHA-256，便于区分后续实现。

未运行：产品全量备份、真实材料恢复、自动定时任务、云端上传、VSS、异机 ACL/DPAPI、PG 恢复、断电/海量数据和最终安装包构建。
