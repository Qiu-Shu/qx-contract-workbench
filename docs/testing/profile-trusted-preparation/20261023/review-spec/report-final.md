# C2b2a 独立 Spec 复核（最终）

基线 `2997d4602d842c6cab8e514a4c7340085910ad0c`。结论：**0 项未关闭的 Spec 问题；SPEC-01 已关闭。**

共享 `attachment_records.decode_items:39-48` 现复用既有严格 JSON 解码器，要求数组根、最多20项并沿用附件ID唯一规则；当前选择 `items:58` 与历史回执 `attachments.find_material_request:131` 共用，错误统一为有界 `VERSION_CONFLICT`。未复制解码器或引入新的模块依赖环；原已导入的 integrity 模块继续复用。没有改变有效空列表和原选择顺序的契约。

原8个独立探针未修改，冻结修复后重新运行：**8 passed，exit 0，4.11s**。其中4项原有效失败现通过，覆盖 `{}` / `""` 在预览与保存后装配两阶段的拒绝；另外4项继续验证调用方事务回滚、已有生成元数据仍可一致性读取、真实run.actor绑定、静态入口和封闭guard。初轮 `4 failed / 4 passed` 证据原样保留，未用最终结果覆盖失败记录。

修复前其余契约符合结论见 `report.md`，仍成立：新模块返回数据库一致性快照；不授予许可、费用、claim或保存权；没有运行入口、模型调用、schema变更或业务写入。registry/native/runner/HTTP/model_integrity 对基线仍无差异。下一片的许可/账本/原子保存/语义重放工作未在本次完成。

## 冻结输入与证据

| 文件 | SHA-256 |
|---|---|
| assistant/profile_preparation_service.py | a2690e45121d139e9cc9fa430add1558d2ab472460f5d3914d43e80116a0a2da |
| assistant/attachment_records.py | d6384abc36f639908110494da6b781dfa7a67f510c1a5eee6e2cf8bfdf1c32ca |
| assistant/attachments.py | 9b69395f104e62913817e6290cc14f1eddfde59514f6b5f41f47592e0f26c0e4 |
| tests/integration/test_assistant_profile_trusted_preparation.py | 0992ae8a708710e175054557ac3286fc956e989e138687caf98a9ab03e611948 |
| tests/integration/test_assistant_material_snapshot_decode.py | 878f98ea31200ced34fa29fa8b47a48d3d9fce41ca06f69bcbe47add2a96cb48 |

最终验证期 **16项输入哈希全部不变**，完整清单见 `inputs-final-before.json`、`input-stability-final.json`。运行日志与JUnit：`output-final.log`、`results-final.xml`。执行命令：

```text
.venv/Scripts/python.exe -X utf8 -m pytest .local/profile-trusted-preparation-20261023/review-spec/test_independent_spec.py -q --tb=short --basetemp=.local/profile-trusted-preparation-20261023/review-spec/probe-final-temp --junitxml=.local/profile-trusted-preparation-20261023/review-spec/results-final.xml
```

未重复统筹的13文件最终回归、四门或完整套件；不将其未收到的结果标为通过。仅使用隔离合成SQLite，未改产品/测试/规格或提交，未触及真实资料、凭据和活动桌面。
