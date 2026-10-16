# 仓颉用于群兴法律方法卡的限定研究

> 本文为 2026-10-14 的固定源码研究。资料库与桌面应用后续进展见 [任务实际状态](../TASK_STATUS.md)；本研究没有因此升级为仓颉运行或法律质量验收。

核验日期：2026-10-14（Asia/Shanghai）。状态：SOURCE_REVIEW_ONLY；未安装或运行上游，未接入产品运行目录，未作法律准确性或生产验收。

## 结论与范围

建议把 `kangarooking/cangjie-skill` 作为“由已核验材料整理方法卡、再编译成受控能力包”的候选。现有原文库继续独立保存；不能用仓颉的词法索引替代总法库。这个判断来自编译入口、来源契约和索引实现的职责差异，属于本项目接入建议，不是已完成实施。[编译入口][cli]、[能力包结构][bundle]、[索引实现][index]

用户本轮已明确：当地法规首批范围为**吉林省**。当前不扩为全国地方规范，也不推断包含某个市的全部文件。按主任务已核对的工程上下文，复用 `D:\Documents\裁判文书数据库试点2025\data\judgments.duckdb` 的既有 10,000 条来源记录；本研究子任务没有打开该数据库、读取真实文书正文或重新导入。该数量不是本子任务重新统计的结果。

## 固定研究基线

GitHub 插件读取的仓库默认分支最新提交为 `a28de55ba881b9928956a55048f743f7a9e3b23e`，提交时间 `2026-10-02T03:17:51Z`，树对象 `1a0171f46b7647ed245b957c43ce802fb1e94d11`。以下全部源码链接固定到该提交，避免把后续上游变动混入结论。[提交记录][commit]

| 文件 | Git blob SHA | 本轮用途 |
|---|---|---|
| `scripts/cangjie.py` | `279f2b174d77ae7c72545a00ddab3b4c870dca94` | 统一编译、暂存校验与发布流程 |
| `scripts/compile_single.py` | `79574ef02510b054f1861daea419896ee49edd69` | 单入口编译、能力卡和资源复制 |
| `scripts/compile_pack.py` | `247247f1391d3e5225fb98501bee01f03bbb8453` | 路由入口与晋级能力编译 |
| `schemas/capability.schema.json` | `a53e96c38f5d62992144e7afe4a896f6fe40f68d` | 能力状态、修订及来源字段 |
| `schemas/capability-bundle.schema.json` | `56a0b4bac732298568949ac8866423f70a53b622` | 编译事实源 |
| `schemas/source-manifest.schema.json` | `5836b09bc2c93b418797051d655e682a6fc61af4` | 来源、权利、信任和版本状态 |
| `schemas/contracts/source-document.schema.json` | `d2d6808257202ae5915be73d9fda186b588eb140` | 来源文档及原文元素定位 |
| `schemas/contracts/chunk.schema.json` | `d30cd33b71170c1d5b221b2971892c3063b7109a` | 分块的来源与版本契约 |
| `scripts/build_index.py` | `91a04a9d23c695c9abddfcd65c422dc73d371f73` | SQLite FTS5 建库与邻接查询 |
| `scripts/validate_skill_pack.py` | `0c90bee3102ef55d3ee91361612d49046ffa8220` | 包结构静态检查范围 |
| `LICENSE` | `14fac913ccf80234b1848540089a3bbcb6e5283d` | MIT 许可文本 |

上述 SHA 来自同一固定提交的 GitHub 文件接口与树对象，不是本机安装版本或本机运行校验。[固定树][tree]

## 源码实际说明了什么

### 1. 编译不负责自动形成可靠法律知识

`cangjie.py` 的统一入口明确把蒸馏交给 Agent；`compile` 的输入是已经准备好的 Capability Bundle。`compile_single.py` 读取 `verified.yaml`，把活动能力的卡片、显式资源、索引和入口组织为输出；自身不调用模型。`compile_pack.py` 则构造一个来源路由入口和少量晋级入口，检查去向、入口数量以及自包含等不变量。文件名 `verified.yaml` 是流程约定，不能当作律师已经核验的证明。[统一入口][cli]、[单入口编译器][single]、[能力包编译器][pack]、[包结构][bundle]

统一 `compile` 流程会先构建 staging，调用 `validate_skill_pack.py`，再进入 WriterLock、旧版本快照和 `atomic_publish`；这是**生成技能包**的发布流程。它不使 `build_index.py` 自动获得事务切换或失败恢复能力。本轮没有执行这些流程，不能确认其在本机 Windows 上的运行表现。[统一入口][cli]

### 2. 来源契约值得复用，但法律约束需要加强

上游并非完全没有来源和版本：SourceDocument 必须有 `source_id`、`version_id` 和 `elements`；Chunk 必须有 `source_id`、`version_id`、`element_ids`、`content_hash`。Source Manifest 也登记来源 URI、权利、信任层级和版本状态。这些可作为适配参考。[文档契约][source]、[分块契约][chunk]、[来源清单][manifest]

但能力自身的 `source_evidence` 不在顶层必填列表，默认允许空列表；每条证据只强制 `source_id`，`version_id`、`location`、`chunk_ids` 都是可选。该能力结构没有强制的律师核验、法规范生效失效、地域或具体适用期间字段。因此“符合上游 schema”不足以成为法律方法卡准入条件。[能力结构][capability]

`validate_skill_pack.py` 主要检查 UTF-8、frontmatter 的非空名称与说明，以及本地相对引用是否存在；它不核对法律内容、原文引述是否准确、来源证据是否充分或法规时效。因此不能将其返回成功显示为“法律核验通过”。[静态检查器][validator]

### 3. 索引只适合作为可重建的检索候选

`build_index.py` 的 `build()` 先 `read_text(...).splitlines()` 整体载入分块，再删除目标数据库文件后重建。其 `chunks` 表只保留 `seq`、`chunk_id`、`heading_path`、`text`、`keywords`，没有把 Chunk 契约中的 `source_id`、`version_id`、`element_ids` 或 `content_hash` 存入该表。查询按全局 `seq` 的数值范围扩展邻接块，不按来源和版本约束；输出正文还截取为前 1,500 字符。中文采用 bigram 预处理，各词用 OR 组合，不能等同于已评估的法律相关性排序。[索引实现][index]

这些是本轮固定源码核验；用户转述的 Linux 合成实验（跨文书邻接、重建后标记表消失）是**用户提供的历史实验结果**，本轮没有取得其完整原始报告或重新运行。源码可以解释所述现象，但不能把历史实验改标为“今天 Windows 实测”。

### 4. 许可与材料授权分别管理

根 `LICENSE` 为 MIT，要求在软件复制件或实质部分中保留版权和许可说明；本轮仅读取，没有复制上游实现到产品。该许可文本不提供对用户原件、第三方裁判文书数据或法规网站访问方式的额外授权；具体来源权利仍须逐项记录。[许可证][license]、[来源清单的权利字段][manifest]

## 建议的群兴接入边界（尚未实施）

以下为基于上述源码缺口提出的工程设计建议，不是上游原生已具备的功能。

1. **原件与业务数据库保留现状。** 既有 DuckDB、CSV 原件和来源定位继续作为独立证据链；如需试验 FTS5，应在新的派生索引路径建库，禁止把现有数据库路径传给上游 `--db`。派生索引失败时仍可读取旧索引和原件。
2. **所有检索结果都携带来源与版本。** 唯一标识至少覆盖资料、版本和分块；邻接扩展必须同时约束 `source_id` 和 `version_id`。结果摘要与完整原文分别呈现，点击后定位原件及具体位置，并核对 hash。现有数据缺失的原始网站 ID 或 URL 继续显式缺失，不能由案号编造链接。
3. **方法卡采用本项目更严格的结构。** 每张卡必须有至少一条有效来源引用，每条强制版本、原文位置和引述校验；另有适用范围、反例、停止条件、法规范适用期间，以及 `draft / pending_review / approved / needs_recheck / withdrawn` 等独立审核状态。律师批准必须绑定审核人、时间及卡片内容版本，不能映射为上游 `active` 就视为批准。
4. **吉林省法规先做可回查版本台账。** 原文及公布机关、原始 URL、采集时间、文件 hash、公布和施行日期、修改/废止关系、地域与资料类别分别保存。法规历史有效期间与数据库收录时间分别保存。首批具体网站、文件目录和法规现行效力由独立来源核验任务决定，本研究没有确认任何具体法规现行有效。
5. **更新先触发复核。** 来源版本改变、撤回或规范效力变化时，按引用关系找出受影响的方法卡，标为待重新核验。未经核验的卡不得继续自动提供已批准结论；保留历史卡及当时所用依据，便于回放旧案件。
6. **先做小规模有留出样本的试点。** 选择一个律师熟悉的专题，准备约 50—100 份相关文书及对应时期法规，形成 3—5 张候选卡；这只是建议规模，尚未选取真实样本。验收原文定位、跨案件隔离、旧法误用、遗漏不利案例和停止条件，先于卡片数量或压缩比。

## 本轮完成与未完成

已完成：固定上游提交、读取 11 个源码/结构/许可文件、核对本轮研究涉及的字段和实现、形成接入建议及来源链接。采用 GitHub 插件只读接口；没有执行上游脚本，也没有发起模型蒸馏。

未完成：Windows 仓颉运行测试、增量索引适配、法律方法卡实现、吉林省法规范采集和效力核验、真实资料处理、律师验收、生产接入。WorkBuddy 实机连接属于主任务的独立验证，本笔记不作判断。

[commit]: https://github.com/kangarooking/cangjie-skill/commit/a28de55ba881b9928956a55048f743f7a9e3b23e
[tree]: https://api.github.com/repos/kangarooking/cangjie-skill/git/trees/1a0171f46b7647ed245b957c43ce802fb1e94d11?recursive=1
[cli]: https://github.com/kangarooking/cangjie-skill/blob/a28de55ba881b9928956a55048f743f7a9e3b23e/scripts/cangjie.py
[single]: https://github.com/kangarooking/cangjie-skill/blob/a28de55ba881b9928956a55048f743f7a9e3b23e/scripts/compile_single.py
[pack]: https://github.com/kangarooking/cangjie-skill/blob/a28de55ba881b9928956a55048f743f7a9e3b23e/scripts/compile_pack.py
[capability]: https://github.com/kangarooking/cangjie-skill/blob/a28de55ba881b9928956a55048f743f7a9e3b23e/schemas/capability.schema.json
[bundle]: https://github.com/kangarooking/cangjie-skill/blob/a28de55ba881b9928956a55048f743f7a9e3b23e/schemas/capability-bundle.schema.json
[manifest]: https://github.com/kangarooking/cangjie-skill/blob/a28de55ba881b9928956a55048f743f7a9e3b23e/schemas/source-manifest.schema.json
[source]: https://github.com/kangarooking/cangjie-skill/blob/a28de55ba881b9928956a55048f743f7a9e3b23e/schemas/contracts/source-document.schema.json
[chunk]: https://github.com/kangarooking/cangjie-skill/blob/a28de55ba881b9928956a55048f743f7a9e3b23e/schemas/contracts/chunk.schema.json
[index]: https://github.com/kangarooking/cangjie-skill/blob/a28de55ba881b9928956a55048f743f7a9e3b23e/scripts/build_index.py
[validator]: https://github.com/kangarooking/cangjie-skill/blob/a28de55ba881b9928956a55048f743f7a9e3b23e/scripts/validate_skill_pack.py
[license]: https://github.com/kangarooking/cangjie-skill/blob/a28de55ba881b9928956a55048f743f7a9e3b23e/LICENSE
