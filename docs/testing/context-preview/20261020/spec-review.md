# CH-06B2b1 独立 Spec 审查

固定点：`0d53fdfdae806c6fec90c01cab1531a7cb666831`。Commit list 为空；范围为 `git diff 0d53fdf` 加 `git ls-files --others --exclude-standard` 中本片源码/测试。依据：`docs/plans/2026-10-20-context-preview-execution.md`，最终发送、原生批准和存储迁移不属于本片。

**发现：0 项待修复。** 未发现缺失、越范围或表面符合却实现错误的要求。

- “当前用户与来源都须获权”“读取body前后复核”：服务复用 `_owned`、`_expected` 与 `read_saved_citation`，比较工作区/对话/案件/绑定及历史版本；HTTP两次认证。独立探针在 body 读取后撤销会话、改草稿、增加恢复 fence，均拒绝且零 attempt。
- “引用从既有持久回执重建”：损坏所选原引用摘要后返回 `LIBRARY_RECORD_INVALID`，没有生成干净预览或任务。引用正文保留字面内容，内部路径/metadata字段通过白名单排除；没有把字段过滤宣传为任意内容脱敏。
- “旧…哈希字节不变”：从固定提交提取 domain，比较 `MainRequest`、`MainPreparedInput`、`MainSendApproval` 规范 JSON 完全相同；普通文字 DTO 拒绝额外 sources。
- “不读取密钥…不改变旧grant”：配置读取的独立探针设置秘密访问/执行失败哨兵，读取成功且 grant 不变。完整系统模板/规范 wire、UTF-8预算与不截断状态有对应实现；全部预览固定 `sending_enabled=false`。

证据：`spec-probes.json` 保存完整命令、退出码0、输入 SHA 前后清单；`spec-probes.log/xml` 为 **6 passed / 6.63秒**。测试全部使用 D盘全新 `spec-temp-f1b615f3a1274c9cbf075edc9cf75e44`。首次 `spec-probes-fixture-error.*` 为审查脚本自身局部变量 NameError（5通过/1失败，未执行该产品路径），修正探针后重跑；没有产品修正。

只读审查，没有修改产品、运行全套、真实供应商或真实案件。独立探针不替代根任务完整回归；未来发送链的许可与归档安全尚不在此次结论内。

补充：完整收集发现 unit/integration 同名测试模块冲突；integration 文件仅改名为 `test_assistant_context_preview_service.py`。与探针输入清单的原文件 SHA256 对比一致（639b4a44e03a6f05b6977fbc8a9e6c919876aa5910b77c21601351719e2cfe28），产品未变，因此上述审查结论继续适用；未重复运行6项探针。
