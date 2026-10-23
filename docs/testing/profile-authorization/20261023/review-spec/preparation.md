# 独立 Spec 探针准备状态

依据 `docs/plans/2026-10-23-profile-authorization.md` 和固定基线 `60eb041536dc36dfd4133f0d09b909681146500c`。

已准备 `test_independent_spec.py`，仅使用独立合成的 registry、DTO、provider。涵盖完整保存计划在相同wire下的隔离、原文/wire摘要不能替代用途摘要、自洽伪造wire、忽略preflight的provider晚到后仍保留费用证据并撤掉候选、缺少完整计划的请求、原生/HTTP/运行器/guard不变。

**尚未执行、未检查施工中的实现或作者新测试，不作通过/失败判断。** 冻结通知后再捕获输入摘要、审查两文件实际差异并运行此独立探针。既有合成fixture/API信息来自基线文件；测试中不访问真实数据、密钥或供应商。
