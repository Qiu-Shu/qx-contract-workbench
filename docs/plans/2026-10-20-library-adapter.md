# CH-06A：对话法库适配及当前权限边界

本片沿已批准的v2.1第7、9.4、9.5及CH-06推进，基线ced22116edc736b55712d6c005917b37a3604ee1。开始工作树干净、fetch后0/0，无开放PR，只有既有CodeGraph进程。Obsidian上片状态与仓库相符；Tencent自动摘要中的旧框架/待办并非当前事实，不据此重做CH-05D2。

## 本片接口与约束

先完成可独立验证的本机检索底座。新增`assistant/tools/library.py::LegalLibraryAdapter`，只复用已有`library.service.search/read_original/read_fragment`及清洗/分段能力。`search`返回查询、实际索引代际、覆盖范围、分页/timeout状态及最多8条候选引用；`read_original`重新核对一条引用并返回同一受限原文快照。每条引文最多1200字符，在同一文书和原始片段内截取，不能沿索引重叠区扩到下一条规则。标题、元数据命中与正文命中分别保留，snippet不能冒充原文。

引用DTO统一放domain.py，含generation、record/version/source标识、登记源摘要、引用记录的原始/正文摘要、kind、候选标题/日期等元数据、片段身份/角色/歧义、精确start/end和line位置、完整quote及SHA。业务核验只允许unverified；原文逐字匹配是独立source_match状态，不代表支持性或本案适用性。`registered_source_sha256`明确是入库时整个源文件的登记摘要，查询时只重核所读记录raw/body和quote；不声称查询已重新校验多GB CSV所有未引用记录，整源完整性沿用单独盘点/审计流程。没有原网站链接时不补造官方网站；不把源路径/别名或raw_fields返回给生成器。重算CSV清洗元数据、法规划分；不能直接信任索引标题、片段role/article或摘要snippet。

搜索完成及返回前重查代际；代际变化拒绝本批，不把旧结果自动重标当前。重读保持请求中的generation/version，缺库、失配、引用记录或引文变化均明确拒绝，不自动重建/下载/重试。同一CSV中未被引用行的等长变动不属于本次逐条回读的完整性证明范围。根目录仅由可信装配传入；本轮不触碰F盘真实库。检索query本身有长度、过滤字段与8条上限，不把20000字聊天默默裁成200字检索。

新增`assistant/tools/service.py::execute_tool(actor, call, database, adapter)`只允许固定的`legal_library.search`和`legal_library.read_original`。调用前后使用现有`service._owned/_expected`核对当前账户会话、角色、工作区、对话/接待/案件权限及scope/composer版本；文件读取期间不持有工作区数据库会话。未知工具/越权/过期请求不得读库，读取期间权限或版本变化不释放结果。DTO结果保留请求scope和工具名。读库不创建message/run/事件、费用、档案、授权或模型任务。

这是内部服务接口，不新增HTTP、界面按钮或模型tool调用入口。引用对象由此服务产生；后续持久化需由服务器按引用ID取回，不能允许模型自填引用快照作为“服务器已保存”证据。本片不冒称完整CH-06。

## 验证与后续

在临时独立合成法库和工作区先保留有效RED，再验证真实导入/检索/原件回读：重复文本准确位置、中文范围、标题/元数据、目录/引述角色、截断/片段边界、坏hash/ID/字段、原文损坏、代际切换、未配置与部分超时。会话服务覆盖调用前/中撤权、跨用户/案件、旧scope/草稿、未知工具、无副作用与读取不占事务。目标法库、对话及开发门按实际影响运行；不重跑未改桌面240或旧全套。独立双轴复核后记录证据并同步GitHub。

后续CH-06B才接固定event_seq/handler版本回执及持久引用，按同事务提交/重放/预算8次工具和4轮上限；再贯通检索→原文→意见和引用面板，并同步备份/恢复。无该回执不能把读取称自动技能执行完成。模块保持独立，不把新逻辑塞入app.py或workbench.js；无新依赖，本片不做无变化安装包重建或不相干资源测量。

## 本片实际结果

已完成内部adapter和权限服务；最终341通过、2项既有DuckDB前提不足跳过，四开发检查exit0，230输入前后一致。Spec/Standards发现已处理，剩余0；具体命令、失败过程、证据核验范围和未测项见[本片证据](../testing/library-adapter/20261020/README.md)。WorkBuddy本轮委派超时，无审查答案。新模块尚未接HTTP/UI或模型工具；后续按上述CH-06B接线，不把本片当整个CH-06完成。
