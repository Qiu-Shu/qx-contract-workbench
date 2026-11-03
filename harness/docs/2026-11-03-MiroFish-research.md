# MiroFish 源码研究与庭审能力取舍

日期：2026-11-03。只读 GitHub 官方仓库；未安装、未运行、未下载依赖、未发送案件材料。默认分支为 main，本次固定提交 [7657031ac01184afe2cb220f5ee3545573b5e843](https://github.com/666ghj/MiroFish/commit/7657031ac01184afe2cb220f5ee3545573b5e843)，提交时间 2026-10-01 18:20:36 UTC。所有下列链接固定到此提交。

## 实施结论

本轮庭审能力继续使用现有 Harness 会话、角色任务和 Python 材料/Word 工具。借鉴 MiroFish 的角色资料、逐轮运行记录、向指定角色追问、按记录复盘，不接入它的社交模拟运行时和 Zep 图谱。理由是其核心代码针对社交账号、帖子、点赞和传播，移成庭审仍需改本体、人设、动作、报告和证据模型；不会比当前 Harness 增加少量庭审角色更短。此为基于代码的工程判断，不是运行性能结论。

## 实际架构

| 层 | 源码实际行为 | 对庭审的取舍 |
|---|---|---|
| 本体与图谱 | 本体提示明确针对社交媒体舆论，要求 10 种可发声实体；材料切块后提交 Zep Cloud 建图。 | 当事人、证人、证据、争点可以建立关联；目前先用案件底稿与来源定位，不必引入云图数据库。 |
| 角色 | 从图谱实体及检索上下文生成 persona，再保存 Twitter CSV / Reddit JSON。个人模板要求年龄、MBTI、教育、经历和立场等详细设定。 | 仅采用角色的任务、已知材料、主张、可见范围。未知经历或心理不得靠人物生成补成案件信息。 |
| 模拟 | CAMEL 建模，OASIS 创建本地 Twitter/Reddit 环境及各自 SQLite；按活跃时间和概率选人，逐轮执行 LLMAction。 | 改成主持/法官追问、对方质疑、己方应答、复盘；按争点顺序推进，用户可继续/停止，无需随机社交活跃度。 |
| 记录与记忆 | 从模拟数据库读取实际动作，生成每轮 action 日志；有意义的动作被整理为带时间、平台、轮次的文本，再追加到同一 Zep 图谱。 | 保存原始材料和模拟记录两个类别。模拟发言继续标为推演，不能覆盖原证据或被提升为已确认事实。 |
| 追问与报告 | IPC 向仍存活的模拟环境指定 agent 发送 INTERVIEW；ReportAgent 先列提纲，逐章调用检索/采访工具并保存 Markdown。 | 可向指定庭审角色追问；最终输出争点、双方回应、未答问题和补证清单，并回指本轮材料/发言。 |

固定源码依据：

- [ontology_generator.py:48](https://github.com/666ghj/MiroFish/blob/7657031ac01184afe2cb220f5ee3545573b5e843/backend/app/services/ontology_generator.py#L48)：社媒本体；[graph_builder.py:142](https://github.com/666ghj/MiroFish/blob/7657031ac01184afe2cb220f5ee3545573b5e843/backend/app/services/graph_builder.py#L142)：切块、建图、批量提交、等待处理。
- [simulation_manager.py:294](https://github.com/666ghj/MiroFish/blob/7657031ac01184afe2cb220f5ee3545573b5e843/backend/app/services/simulation_manager.py#L294)：实体→角色→平台资料→运行配置；[oasis_profile_generator.py:734](https://github.com/666ghj/MiroFish/blob/7657031ac01184afe2cb220f5ee3545573b5e843/backend/app/services/oasis_profile_generator.py#L734)：个人设定要求。
- [run_parallel_simulation.py:177](https://github.com/666ghj/MiroFish/blob/7657031ac01184afe2cb220f5ee3545573b5e843/backend/scripts/run_parallel_simulation.py#L177)：平台动作；[同文件:1040](https://github.com/666ghj/MiroFish/blob/7657031ac01184afe2cb220f5ee3545573b5e843/backend/scripts/run_parallel_simulation.py#L1040)：概率选活跃角色；[同文件:1138](https://github.com/666ghj/MiroFish/blob/7657031ac01184afe2cb220f5ee3545573b5e843/backend/scripts/run_parallel_simulation.py#L1138)：OASIS 与本地数据库；[同文件:1253](https://github.com/666ghj/MiroFish/blob/7657031ac01184afe2cb220f5ee3545573b5e843/backend/scripts/run_parallel_simulation.py#L1253)：执行后从数据库读取实际动作。这里的 Twitter/Reddit 是模拟环境，不能据此称向真实平台发帖。
- [zep_graph_memory_updater.py:494](https://github.com/666ghj/MiroFish/blob/7657031ac01184afe2cb220f5ee3545573b5e843/backend/app/services/zep_graph_memory_updater.py#L494)：模拟动作写回图谱，metadata 包含 simulation_id 与模拟来源；[zep_tools.py:87](https://github.com/666ghj/MiroFish/blob/7657031ac01184afe2cb220f5ee3545573b5e843/backend/app/services/zep_tools.py#L87)：报告检索视图以关系、fact 和时间字段表达图谱内容，未直接提供案件证据类型隔离。
- [run_parallel_simulation.py:317](https://github.com/666ghj/MiroFish/blob/7657031ac01184afe2cb220f5ee3545573b5e843/backend/scripts/run_parallel_simulation.py#L317)：指定角色采访；[report_agent.py:925](https://github.com/666ghj/MiroFish/blob/7657031ac01184afe2cb220f5ee3545573b5e843/backend/app/services/report_agent.py#L925)：四个报告工具；[同文件:1665](https://github.com/666ghj/MiroFish/blob/7657031ac01184afe2cb220f5ee3545573b5e843/backend/app/services/report_agent.py#L1665)：提纲和逐章持久化。角色底层会话记忆由 OASIS/CAMEL 提供，本次未展开审阅其依赖源码。

## 部署、限制与依赖

- 后端 Python >=3.11,<3.13、Flask；前端 Vue 3、Vite 7、D3。固定直接依赖为 zep-cloud 3.25.0、camel-oasis 0.2.5、camel-ai 0.2.78，另有 OpenAI SDK、PyMuPDF 等。见 [pyproject.toml:5](https://github.com/666ghj/MiroFish/blob/7657031ac01184afe2cb220f5ee3545573b5e843/backend/pyproject.toml#L5)、[frontend/package.json](https://github.com/666ghj/MiroFish/blob/7657031ac01184afe2cb220f5ee3545573b5e843/frontend/package.json)。未展开完整传递依赖，也未验证 Windows 安装。
- LLM 走 OpenAI 兼容接口，可配置 base URL/model；脚本另有可选 boost LLM。Zep 明确固定为 https://api.getzep.com/api/v2，并拒绝 ZEP_API_URL；不是现成纯本地记忆方案。见 [utils/zep.py:21](https://github.com/666ghj/MiroFish/blob/7657031ac01184afe2cb220f5ee3545573b5e843/backend/app/utils/zep.py#L21)、[同文件:65](https://github.com/666ghj/MiroFish/blob/7657031ac01184afe2cb220f5ee3545573b5e843/backend/app/utils/zep.py#L65)、[create_model:984](https://github.com/666ghj/MiroFish/blob/7657031ac01184afe2cb220f5ee3545573b5e843/backend/scripts/run_parallel_simulation.py#L984)。材料图谱与模拟动作都会进入该云服务；本次没有配置或发送。
- Docker 只打包应用并挂载 uploads，仍读取外部服务配置；映射 3000/5001。见 [docker-compose.yml](https://github.com/666ghj/MiroFish/blob/7657031ac01184afe2cb220f5ee3545573b5e843/docker-compose.yml)。
- 它也有明确上限：HTTP 上传 50 MiB、图谱活动分片 9,500 字符、报告每章最多 5 次工具调用；报告代码还要求至少 3 次工具调用、最多 5 次迭代，并处理工具文本与 Final Answer 冲突。不能把它当作取消所有限制的方案。见 [config.py:36](https://github.com/666ghj/MiroFish/blob/7657031ac01184afe2cb220f5ee3545573b5e843/backend/app/config.py#L36)、[memory_updater:241](https://github.com/666ghj/MiroFish/blob/7657031ac01184afe2cb220f5ee3545573b5e843/backend/app/services/zep_graph_memory_updater.py#L241)、[report_agent:1324](https://github.com/666ghj/MiroFish/blob/7657031ac01184afe2cb220f5ee3545573b5e843/backend/app/services/report_agent.py#L1324)。这些强制次数和文本工具协议不建议迁到已具备原生工具调用的 Harness。
- 资源消耗随角色数、活跃轮数、平台数、人物生成和报告检索/采访增长。未运行，无法给出本机吞吐、费用或准确率。

## 许可证与证据范围

仓库 [LICENSE](https://github.com/666ghj/MiroFish/blob/7657031ac01184afe2cb220f5ee3545573b5e843/LICENSE) 为 GNU AGPL 第 3 版全文，后端 [pyproject.toml:6](https://github.com/666ghj/MiroFish/blob/7657031ac01184afe2cb220f5ee3545573b5e843/backend/pyproject.toml#L6) 声明 AGPL-3.0。这里只记录许可证事实，不作具体分发/组合适用判断；本轮没有复制产品源码、安装或分发该项目。依赖各自许可未逐一核验。

README 的“预测万物”是项目定位。本次读到的测试目录主要覆盖 JSON、人设、图谱生命周期、重试和报告工具结果处理；未获得庭审效果、裁判预测、法律准确率或真实案件验证证据。角色意见数量、反思提示和图谱存在本身都不能当作这些效果的证据。

可立即采用的最小流程：固定本次材料与来源 → 按争点让对方提出质疑 → 己方依据材料应答 → 主持追问未解决处 → 复盘争点和补证事项 → 保存可续接记录与 Word。模型角色输出属于演练；依据不足保留问题，不生成胜诉概率或将模拟法官当成真实裁判。

