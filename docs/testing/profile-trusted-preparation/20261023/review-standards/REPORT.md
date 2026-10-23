# CH-07C2b2a Standards 独立审查

基线 `2997d4602d842c6cab8e514a4c7340085910ad0c`；时间 2026-10-23。先读计划与既有调用规范，收到根代理冻结通知后开始源码复核与探针；无产品并写。

## 结论

**未发现当前切片需修复的 Standards 问题。** 依据仓库 AGENTS 的 DTO 单一归属、后端权限/版本核验、合成证据要求，CONTRIBUTING 的 caller-owned 短事务与取消/许可边界；ponytail/codebase-design 仅作设计启发，不据其扩展当前切片。

- `profile_preparation_service.py:52` 和 `:72` 是两个受数据库核验的入口，DTO 均复用 domain。现有 `_writable` / `_owned_run` 负责当前会话身份、所有权、案件访问、恢复和归档；没有自行复制授权算法或吞掉拒绝审计。
- `:29` 的档案基线增加固定作用域/版本不领先核验；数据库中的接待目标及当前修订构成保存计划。即使旧档案 JSON 摘要有效或另一接待具有相同标题/版本，也不能替换已准备目标。
- 保存后使用实际同会话 user message 重建原 MessageInput 与 request digest，并比较完整 basis。继续输入的草稿不进入保存过的正文或来源；固定 composer 保留原提交版本，不要求停止打字。
- 无新 DTO/schema/依赖/运行入口；源码检索只有新模块中的两个定义，没有 registry/native/runner/HTTP 调用，新格式 guard 未改。冷导入未加载 Web、桌面、主供应商、HTTP 客户端或 PDF 解析入口。
- 两层纯装配/数据库装配各有不同责任，不是无必要包装；少量固定字段检查与既有合并语义一致，未发现值得扩大重构的可复现 Fowler 设计问题。

## 独立验证

```powershell
.venv/Scripts/python.exe -X utf8 -m pytest .local/profile-trusted-preparation-20261023/review-standards/test_trusted_standards.py -q --tb=short --basetemp=.local/profile-trusted-preparation-20261023/review-standards/tmp --junitxml=.local/profile-trusted-preparation-20261023/review-standards/results.xml
```

一次 pytest：**6 passed，3.76 秒，退出码 0**，无失败重跑。覆盖：

1. build/prepare 两阶段权限拒绝观察待 flush 的撤权，回滚调用方未提交业务修改，保留一条独立拒绝审计；调用方随后 commit 也不会误存业务修改。
2. 即使会话归属仍有效，运行 actor 被替换也拒绝。
3. 同版本同标题接待替换仍拒绝。
4. 旧档案摘要、修订、cid/workspace 均有效但固定 scope 不同仍拒绝。
5. 独立冷进程导入检查（由第六项测试运行一次 Python 子进程，退出码 0）。

原始证据：`output.log`、`results.xml`、`test_trusted_standards.py`。12 份直接及关联源码/测试/计划输入的前后 SHA-256 相同，见 `inputs-before.json`、`inputs-after.json` 和 `verification.json`。冻结产品 SHA 为 `a2690e45121d139e9cc9fa430add1558d2ab472460f5d3914d43e80116a0a2da`，正式测试 SHA 为 `0992ae8a708710e175054557ac3286fc956e989e138687caf98a9ab03e611948`。

## 保留边界

没有重跑根代理的六文件回归、四开发门或全套；没有真实模型/网络/WorkBuddy、真实资料、安装版或活动桌面操作。结果证明当前数据库一致性，不代表获得发送、费用预留、claim 或档案写入许可。后续 C2b2b 必须在实际使用时重新核验并闭合授权、账本、保存与历史重放；现阶段仍不得开放新格式 guard。
