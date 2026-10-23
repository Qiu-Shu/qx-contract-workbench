# CH-07C2b1 Standards 独立审查

基线：`e133d5c39475388c6f8763d488cbbf3808e6855e`。时间：2026-10-23。本报告仅覆盖当前迁移前置切片。

## 结论

未发现需要阻断本片的 Standards 问题。适用依据为仓库 `AGENTS.md` 的原件/审计不可覆盖、DTO 单一归属、合成验证及真实证据要求，`CONTRIBUTING.md` 的短事务/权限边界，以及 `docs/plans/2026-10-23-profile-model-schema.md` 的本片范围。Ponytail 和 codebase-design 提供设计启发，不作为额外硬性标准。

- 旧 11 版本、native/普通两种结构的原始和规范化摘要，与直接加载固定 Git 基线的结构构建器逐一相同。另核对其六个动态 schema 依赖：除初始化函数外 AST 与基线一致，避免仅用新增 fixture 自证。
- 结构升级保持原表内容，SQLite 自身拒绝早/中/末段 DDL 后完整回滚，失败重试可成功；真实 `BEGIN IMMEDIATE` 锁冲突也恢复外键约束。新初始化重复执行不改数据。
- `profile_model_schema.py:94–111` 明确围绕事务恢复 FK；`model_integrity.py:455–463` 在空账本早退前拒绝新格式/任意 handler；`profile_integrity.py:240` 继续纳入新版本。经 `_file_references` 入口，空新表里的旧档案破坏和孤立 handler 都被明确拒绝。
- 无新增 DTO、出站客户端、依赖、业务运行入口或许可。冻结版本重复接受分支及版本常量列表是沿用仓库约定，本片没有可复现的 Fowler 设计问题，未因启发式“重复”要求扩大重构。

## 独立实测

命令（一次 pytest 调用，无重跑/无全套）：

```powershell
.venv/Scripts/python.exe -X utf8 -m pytest .local/profile-model-schema-20261023/review-standards/test_standards_independent.py -q --tb=short --basetemp=.local/profile-model-schema-20261023/review-standards/tmp --junitxml=.local/profile-model-schema-20261023/review-standards/results.xml
```

**30 passed，37.57 秒，退出码 0**。22 个历史签名组合、1 个结构依赖 AST 检查、3 个 SQLite authorizer 故障与恢复、1 个真实写锁冲突、1 个成功后重复初始化、2 个备份公共校验入口破坏探针。

原始日志 `output.log`，JUnit `results.xml`，具体探针 `test_standards_independent.py`。输入 SHA-256 位于 `inputs-before.json` 和 `inputs-after.json`；核对结果和 Git HEAD 位于 `verification.json`。探针只写本目录合成库，未改 src/tests。

## 实际边界

本轮没有重跑完整套件、安装器、当前桌面工作库、真实模型、真实材料或 WorkBuddy。native marker 恢复、完整加密备份往返的正式测试仅审读，由主代理提供其当前运行结果。只确认存储前置切片：C2b2 必须继续验证 handler 与 run/attempt/output/receipt 的语义归属、授权、费用和原子保存；当前所有新 handler/新格式历史统一拒绝，不能宣称自动建档已启用。
