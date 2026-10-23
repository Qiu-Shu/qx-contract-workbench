# 旧断言更新补充复核

只读核对 `tests/unit/test_assistant_profile_preparation.py:244` 起的最终差异，文件 SHA256：`accd3abdfe95f0c7e25b6d14d5c112fc4787b85ee3911e984c41516745bdde43`。

结论：**0 项问题**。本片已明确支持完整 `MainProfilePreparedInput`，旧测试要求命中“尚未启用”的特定错误文本已过时。新断言仍要求空对象和离线 basis 单独进入账本解析时抛出 `ValueError`，并新增完整 prepared 的无损往返验证；没有削弱许可、费用或来源检查，也未改动产品代码。

统筹报告首轮关联为 667 passed / 1 failed（共 668），四门 exit 0、552 输入稳定；本测试文件修订后另行 53 passed / 1.437 秒，补验输入稳定。上述结果按两次运行分别记录，不称首轮全绿。本代理未重跑测试；原独立 7 项通过、19/19 输入稳定的产品 Spec 结论保持不变。
