# C2b2a 独立 Spec 复核（初轮）

基线：`2997d4602d842c6cab8e514a4c7340085910ad0c`。实际检查冻结的新产品模块 SHA-256 `a2690e45121d139e9cc9fa430add1558d2ab472460f5d3914d43e80116a0a2da` 与新测试 `0992ae8a708710e175054557ac3286fc956e989e138687caf98a9ab03e611948`。

## 结论：1 项需修复

**[P2] 非数组材料快照被误认作空选择。** `src/cn_contract/assistant/profile_preparation_service.py:47-49` 用 `records.items` 的真假判断是否有附件，而 `assistant/attachment_records.py:47` 直接迭代 `json.loads(raw)`。当前快照为 `{}` 或 `""` 时，两个值均被转换为空 tuple；预览和保存后装配均返回可用 basis/prepared，未拒绝损坏来源。违反本片可信数据库核验中的“当前选中的附件不属于本片支持范围”，以及独立计划第3点“损坏/缺失当前材料快照不得视为空”。应复用共享解码路径，先严格确认根为 JSON array，再验证元素；保持有界错误和无业务写入。无需添加第二套附件存储或恢复模型入口。

独立合成探针通过解除测试数据库的不可变触发器，篡改当前快照后调用真实服务，四个组合（2种错误根×basis/prepared）全部得到 **DID NOT RAISE**；这是对损坏数据拒绝约束的有效失败，不表示正常接口能修改不可变快照，也不表示实际模型已经开放。

## 已核对的符合项

- 当前身份/会话、权限、可写库、归档、作用域、正文与草稿匹配均沿既有服务；运行中的真实 actor/session 显式绑定，原 request 摘要完整重建。
- 固定原消息、请求ID和版本经纯 prepare 再核验；composer-only 增长保留原wire；当前档案固定归属及版本、接待目标/修订重新读取，不刷新旧 basis。
- 未取消 queued/generating 可一致性读取，已有生成元数据不会被误设为读取禁令；这不授予再次发送、claim、费用或写入权限。
- 复用已有 DTO、纯编解码与 caller-owned transaction；没有新 registry、队列、schema 或业务写入。保留共享权限帮助器的 flush/拒绝审计语义。
- registry/native/runner/HTTP/model_integrity 对基线无差异；源码与桌面脚本无对本模块的调用入口，原 `ASSISTANT_PROFILE_MODEL_NOT_ENABLED` guard 仍在。

## 本轮实际验证

独立8项：**4 failed / 4 passed，exit 1，4.15s**。通过项为共享调用方事务及完整 rollback、已有生成元数据仍允许读取、run.actor 显式身份核验、静态无入口与 guard 保留。未重复作者49项或统筹的六文件关联套件/四门。

命令：

```text
.venv/Scripts/python.exe -X utf8 -m pytest .local/profile-trusted-preparation-20261023/review-spec/test_independent_spec.py -q --tb=short --basetemp=.local/profile-trusted-preparation-20261023/review-spec/probe-temp --junitxml=.local/profile-trusted-preparation-20261023/review-spec/results-initial.xml
```

记录：`results-initial.xml`、`output-initial.log`、`inputs-before.json`、`input-stability-initial.json`。审阅及探针期 **13项输入哈希不变**；首次生成清单误填旧 native 路径，执行探针前已用实际 `assistant/native_model_control.py` 补齐，最终清单13项均有效。

只写本独立证据目录；未改产品/开发测试/规格，未提交，未访问真实材料或活动桌面，未联网调用供应商。等待上述1项修复后复验。
