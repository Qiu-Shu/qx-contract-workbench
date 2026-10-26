# dhb_law 合并前修复与验证

2026-10-26，Windows。用户已批准落实审查建议：修复回归、保全未提交工作并整合分支。共同基线 `43257111f0d6ad03b1b8ef1f4bc86151ee58937a`，接收 `dhb_law` 三个提交至 `afb6ab64f81d0167efb309e7f28998e31725450d`，涵盖接待/历史/成果导出、事实证据底稿和待补跟进。源码`042b9d3`已合并并正常同步主分支，原WIP恢复，合并后57项补验通过；[实际回执](github-sync.md)。

## 修复范围

仅四个测试文件，`12+/2-`；产品代码、schema指纹和安全守卫不因修复改变。

- 三处第16/17版夹具先从最新空库移除新增的跟进、事实表，再执行原有降级准备；完整历史结构相等断言保持。
- library完整升级差集补齐四张既有微信表和两张新增底稿表。旧断言在我方共同基线已失败，本轮一并补正，仍使用精确集合相等。
- 私有知识导入测试读取JSON时明确UTF-8，不依赖中文Windows的GBK默认编码。

上轮对照真正共同基线确认：13个原生历史升级测试异常是整个`dhb_law`分支新增的验证回归。其最后一个提交使用`4afbd62`作基线时，这些异常已存在；两种口径不能混用。此处修复历史夹具，不据夹具失败推断产品实际迁移损坏。

## 本轮实际结果

| 检查 | 结果 | 退出码 |
|---|---|---|
| 修复前四模块 | 258项：243通过、9失败、6错误 | 1 |
| 同四模块修复后 | 258通过、0失败/错误/跳过 | 0 |
| 接待、底稿、导出、历史业务回归 | 97通过 | 0 |
| 新schema与微信兼容回归 | 217通过 | 0 |
| 关联前端 | 388通过 | 0 |
| 桌面Node逻辑 | 369通过 | 0 |
| schema/defaults/development sources | 三项通过；来源仍有13项未生产批准警告 | 0 |
| runtime dependencies | 55运行包、1构建包通过，0网络请求 | 0 |

三个最终Python组按完整节点去重，共572项通过；修复前结果不相加。XML及原始完整日志留在本机`.audit-local/dhb-law-integration-20261026`；此目录保留日志脱敏副本、[结构化结果](verification.json)、[开发检查](gates.json)和[双轴独立复审](independent-review.md)。修复后验证期间登记800份源码、测试与配置输入，结束时摘要一致。

运行依赖清单文件实际存在，且与基线一致。此前隔离副本中的`FileNotFoundError`由本机忽略缓存缺失造成，不能称清单缺失；本轮使用候选检查器与候选清单，复用主目录已存在的证据缓存核验。[回执](runtime-gate.json)不代表原生构建或生产批准。

## 未提交工作的保全

原主目录六份未提交文件已逐字节备份并记录SHA256。只在集成时临时保存，合并后恢复；`domain.py`保留接收分支的所有定义并追加原有三个WeixinPending DTO，候选语法树不变。其余五份文件须与备份逐字节一致。待收件服务及尚未接好的HTTP测试继续作为原工作保留，不纳入本轮提交，不宣称D2g5g功能已完成。

## 复现

Python 3.12，本机原有`.venv`，`PYTHONPATH=src`，cwd为冻结候选副本。默认Windows编码运行，没有使用`-X utf8`掩盖测试问题。

```powershell
python -m pytest tests/integration/test_assistant_library_schema.py tests/integration/test_weixin_generation_schema.py tests/integration/test_weixin_provenance_schema.py tests/unit/test_reception_knowledge.py -q --tb=short
python -m pytest tests/integration/test_followup_worksheet.py tests/integration/test_evidence_worksheet.py tests/integration/test_reception_worksheet.py tests/integration/test_reception_worksheet_model.py tests/integration/test_assistant_outputs.py tests/integration/test_assistant_output_models.py tests/integration/test_assistant_conversation_history_flow.py tests/integration/test_conversation_history_review.py tests/integration/test_reception_assistant.py tests/unit/test_assistant_conversation_history.py -q --tb=short
python -m pytest tests/integration/test_followup_schema.py tests/integration/test_evidence_schema.py tests/integration/test_weixin_generation_dispatch_schema.py tests/integration/test_weixin_generation_dispatch_integrity.py tests/integration/test_weixin_generation_ingress.py -q --tb=short
node --test scripts/test_assistant_*.mjs scripts/test_reception_worksheet.mjs scripts/test_evidence_worksheet.mjs scripts/test_followup_worksheet.mjs
node --test desktop/tests/*.test.cjs
```

本轮未执行全仓Python、实际浏览器交互、Windows安装器、真实微信/模型或法律质量验收。既有WIN-PATH-02与原生崩溃保持开放，安装版0.4.1不更新。
