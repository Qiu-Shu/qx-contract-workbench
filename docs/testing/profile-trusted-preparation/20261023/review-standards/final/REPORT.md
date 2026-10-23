# CH-07C2b2a Standards 最终复核

固定基线 `2997d4602d842c6cab8e514a4c7340085910ad0c`，2026-10-23。收到共享解码修复冻结后，重新检查扩展范围及关联入口。**最终无待修的 Standards 发现。**

此前上一级 `REPORT.md` 和 6 项日志只对应首轮冻结窗口；随后 Spec 发现空对象/空字符串被误读成空选择，本最终报告取代其作为合并前结论。原始记录均保留，没有覆盖或把初轮当作最终证据。

## 依据与核验

- 仓库 AGENTS：DTO 保持 domain 单一归属，权限/版本由后端核验，保留原件/审计，开发只用合成数据。CONTRIBUTING：复用已有授权及短事务，不将一致性当发送或费用许可。ponytail/codebase-design 为设计启发；没有额外强制重构或未来执行策略要求。
- 新 `profile_preparation_service.py:52/72` 仍从实际数据库核验用户/会话、原请求摘要、固定作用域、当前档案/接待版本和完整 basis；保存后的新草稿不替换原消息。拒绝访问保留现有 flush、调用方回滚及独立审计语义。
- `attachment_records.py:39` 的 `decode_items` 复用既有严格 JSON 解码和 `AssistantMaterialSelectionInput.distinct_attachments`，数组根、20 项上限、重复 ID、Ref 类型共同生效；错误统一为无正文回显的 `VERSION_CONFLICT`。
- 当前选择 `attachment_records.py:58` 与历史找回 `attachments.py:131` 使用同一解码器，避免历史入口继续把畸形数据读成空集合。没有修改 DTO、schema、provider/native/runner/HTTP 接线或新格式 guard。

## 最终独立实测

```powershell
.venv/Scripts/python.exe -X utf8 -m pytest .local/profile-trusted-preparation-20261023/review-standards/test_trusted_standards.py .local/profile-trusted-preparation-20261023/review-standards/test_shared_decode_supplement.py -q --tb=short --basetemp=.local/profile-trusted-preparation-20261023/review-standards/final/tmp --junitxml=.local/profile-trusted-preparation-20261023/review-standards/final/results.xml
```

最终一次运行 **11 passed，4.91 秒，退出码 0**，不是根代理 13 文件回归，也不与其累计。原 6 项因共享依赖修复而复验；补充 5 项检查深层 JSON、非有限数、布尔修订号、UUID 规范化后的重复 ID，以及“当前选择有效、旧请求选择损坏”时历史找回仍拒绝。原 6 项包括调用方脏事务的拒绝审计、运行 actor、同版本接待替换、固定档案作用域和独立冷导入。

本目录 `output.log`、`results.xml` 保留结果。`inputs-before.json`、`inputs-after.json`、`verification.json` 确认 **15 个产品/测试/计划/依赖输入 SHA-256 在最终验证前后一致**；原产品及正式测试与首轮冻结 SHA 不变，共享两个源码和新增正式测试与根代理最终冻结 SHA 相同。没有与根或实现代理并写产品/正式测试。

## 边界

仅本地合成探针；未重复根关联回归/四门、未运行全套、未连接真实模型/WorkBuddy，未动安装版/活动桌面/真实材料。数据库一致性返回值仍不是发送、费用预留、claim 或档案保存许可；C2b2b 的授权/账本/原子保存/历史重放及 guard 开放继续待办。
