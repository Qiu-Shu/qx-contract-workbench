# 当前聊天原生插件验收

日期：2026-10-09，Asia/Shanghai。沿 `codex/contract-review-v2`，业务实现基线 `c6617de`。本轮不修改业务代码或增加依赖。

## 结论

本机 Codex 当前聊天的四个插件工具已可调用；登记虚构案件的选案读取、候选写回、相同输入重放、不同内容拒绝、撤销后拒绝已实际执行。此前“父聊天仍旧两工具拒绝”是历史状态，本记录关闭该缺口。网页 ChatGPT 接入仍未验收。

候选入库后仍为 `awaiting_lawyer`，来源 `local_plugin_unverified`，模型身份 `UNVERIFIED`；不能将本次工程链路通过当作法律质量或现实律师批准。

## 安装证据

通过宿主支持的 `plugin/install` 安装本地 marketplace 中的 `qx-contract-offline-codex`，实际物化缓存0.1.5。四个关键文件与源一致，旧0.1.3缓存五文件未改；全局配置只允许目标插件设置改变。新的独立宿主发现四工具，无 toolsError。

安装及发现原始结果保留在 `.audit-local/plugin-refresh-20261009/install-summary.json`、`install-015.json`、`discovery.json`。安装不是原生聊天成功的替代证据；聊天证据见下表。

## 本轮实际结果

|实际调用|次数|结果|
|---|---:|---|
|workbench_status|1|成功，真实模型和QCC关闭、生产阻断|
|deepseek_offline_example|1|成功，固定人工构造响应，非供应商推理、非法律意见|
|read_selected_case，明确选案后|1|成功，sales-01，8个锚点、1项已确认虚构事实|
|submit_selected_candidates，首次|1|成功，收据待律师处置|
|submit_selected_candidates，相同输入|1|成功，返回同一收据|
|submit_selected_candidates，同一授权不同内容|1|按预期拒绝，-32602 OFFLINE_REQUEST_REJECTED|
|read_selected_case，撤销后|1|按预期拒绝，同上|
|submit_selected_candidates，撤销后|1|按预期拒绝，同上|

共8次当前聊天原生调用：5次成功、3次符合预期的拒绝。不同输入的拒绝不是超时重试，相同输入重放也仅在首次明确成功后作为幂等性测试进行。

## 工作台落库与导出

- 复用现有 `assisted_api`、`ready_case` 及 `proposal_body`，只用已登记独立虚构 `sales-01`。测试账户及数据库均在独立审计目录，不建立用户持久账户。
- 测试前确认默认 `.local/workbench` 不存在，并独占绑定127.0.0.1:8767；仅临时创建固定路径凭据，原8766服务和真实审查材料未触碰。
- 测试角色通过现有鉴权及CSRF端点明确授予读案及一轮候选权限。此为测试授权，不冒充用户在真实案件的律师批准。
- 数据库实际只有1条候选；在测试角色处置前，发现无人工决定，案件状态为待律师处置。
- 再由虚构测试角色通过工作台端点处置，生成并下载40,438字节DOCX。核对关键字 `DRAFT PLUGIN-UNVERIFIED`，各节页眉含“插件候选”、页脚含“未核验”。这一步是文件内容验证，本轮未新增Word视觉验收。
- 撤销后凭据删除；有界测试服务自然退出0，临时默认凭据目录已清除。虚构数据库及下载稿留在审计目录，未删除旧工作区。

可提交摘要：[原生调用收据](plugin-native-20261009/receipt.json)。完整本机证据在 `.audit-local/plugin-refresh-20261009/native-case-20261009/`，包括 `native-calls.json`、`inspection.json`、`cleanup.json` 和虚构下载稿；测试入口为上级目录 `native_case_harness.py`，10分钟上限且最终清理。

## 执行中断及限制

早前SDK验收助手曾受Windows管道权限、SDK属性名称及异常返回方式差异影响；最后一次SDK脚本没有完整成功结果，不计作通过。本轮使用当前聊天原生工具完成上述验收，不以旧脚本输出代替。

本轮第一次读取 inspection.json 时导出还未结束，文件暂不存在；随后测试服务打印INSPECTED/REVOKED，实际文件与清理结果已核对。没有因此重交候选。

本轮无业务变更，不重跑既有全套pytest、48页OCR或Word版式。8次原生调用也不替代既有工程测试分母。真实DeepSeek/QCC仍关闭；真实材料产品准入与数据政策、网页ChatGPT、法律gold、完整修订后语义重审、正式签发及生产仍未完成或阻断。之前真实合同的直接文档审查，不表示已开放工作台真实资料入口。
