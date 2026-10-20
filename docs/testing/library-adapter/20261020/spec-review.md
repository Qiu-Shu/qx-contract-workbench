# CH-06A Spec 独立审查（2026-10-20，复核后）

范围：基线 `ced22116edc736b55712d6c005917b37a3604ee1` 到工作树的 domain diff；完整审阅新增 tools 三文件、两份 integration 测试，及现有原文、分段、检索、权限调用链。依据本片计划和 v2.1 §7/9.4/9.5/CH-06。**未关闭发现 0；初始 2 项已处理。**

1. **初始 P2，已澄清核验范围并修正语义。** 原规格“原件变化均明确拒绝”过宽：CSV 未被引用行等长变化后，文件 SHA 改变，但原引用回读仍通过（`library.py:27-38, 178-184`）。本片明确选择逐记录验证，避免每次扫描多GB CSV；现字段为 `registered_source_sha256`，状态为 `record_quote_matched`（`domain.py:3211,3231`；`library.py:103,114`），计划说明登记来源身份不代表当前整源完整性。独立反例确认未引用行变化不影响已验证记录；被引用行变化仍拒绝。此项按准确披露范围关闭，**不是声称完整文件已重验**。

2. **初始 P3，已修复规范化边界漏检。** 规格“复用已有检索”及“中文范围”：`㍻年`查询`成年`，上游1条而原适配器0条。原 `library.py:80-84` 对整个原字符规范化结果作等值比较，拒绝展开字符内部起始命中。现以规范化映射重建位置；独立复测1条、原位置4:6、回读相等，并拒绝伪造title/body标签。

未发现额外越界功能；固定工具、权限前后复验、释放工作区事务和unverified业务状态符合本片。CH-06B持久回执/UI/模型编排明确未纳入。

## 实际证据

`git rev-parse <baseline>`、`git log <baseline>..HEAD --oneline`、`git diff <baseline> -- src/cn_contract/domain.py` 均 exit0；log为0提交但工作树diff非空，新文件另全文读取。CodeGraph指定实际仓库、maxFiles=4，成功定位权限链。

最终命令：

- `.venv/Scripts/python.exe .local/library-adapter-20261020/spec-probe.py`：exit0，7项断言通过（精确1200字边界、代际两项、片段语义、登记摘要范围、被引行损坏、兼容字映射）。
- `.venv/Scripts/python.exe .local/library-adapter-20261020/spec-match-field-probe.py`：exit0，1项错误命中类型拒绝。

中间状态如实保留：初版probe为5项通过＋2项观察；直接改索引尝试exit1（产品拒绝索引变动，探针未关闭SQLite句柄又导致清理失败），随后改为独立结果篡改探针；字段迁移期间一次probe exit1因旧`matched`断言，更新为`record_quote_matched`后最终7项通过。未将中间轮累加为最终数量。

## 最终 SHA256

| 文件 | SHA256 |
|---|---|
| domain.py | AD4DBCEA93859C716C7AE82ACD2A458D5ED8BE0A054F031C35DE5AD1429ECFEA |
| tools/__init__.py | 6CEDC11C9448204EFF763D37BAFC5659FD1A7D35191369B5D2D3AA0C55CBDD74 |
| tools/library.py | 1B25AD39C011BD2154FEA09C6DFF87981583111119766FA607884607E4E28581 |
| tools/service.py | 16FCD21A1FAA0609DF4F5409321B57A2DD862B31E274E008AF1BD8A5C8DA9E7E |
| test_assistant_library_adapter.py | A0640B00533359330047D098BAFDC04C194E24F10EB80D21AED5C085CF0D8573 |
| test_assistant_library_tools.py | CD836EA46382000DC5E955DE3C1CE56A7B27928707F09DD8107A5CDD472662ED |
| spec-probe.py | FF585180B174A049A613695AF42A7305B3E13CD12E5CFC82415A960DF9D3CA6F |
| spec-match-field-probe.py | 30B963F73E0373A0700CBDCE084429E5F8F0FFC1EE2C5F4960145242020D8CB3 |

仅独立合成临时数据；未动产品、既有测试、真实库或网络。未重复旧全套/主代理目标回归；整CSV当前完整性与完整CH-06/生产验收均不在本报告通过范围。

