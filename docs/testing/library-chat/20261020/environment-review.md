# 全套失败与环境恢复独立复核

2026-10-20；审查者 `/root/research_spec_review`。结论：证据支持本轮 38 项失败来自临时目录所在 C 盘低于既有磁盘余量门槛。原测试和产品输入未改，精确同一组 38 项改用 D 盘独立临时目录后全部通过。应报告 **全套 3233 通过 + 环境恢复 38 通过，共覆盖 3271 个不同用例**；不能写成“一次全套全绿”。本次独立工作只解析证据和源码，不另跑测试。

## 数量与失败分类

| 批次 | tests | passed | failed | errors | skipped | exit |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `full.xml` / `full-verification.json` | 3271 | 3233 | 38 | 0 | 0 | 1 |
| `environment-recovery.xml` / `recovery-verification.json` | 38 | 38 | 0 | 0 | 0 | 0 |

独立 XML 解析的失败分布：`test_library_cases` 7、`test_library_laws` 6、`test_library_search` 20、`test_library_sources` 5。37 项失败文本包含 `LIBRARY_DISK_BUDGET`；其余 `test_bulk_laws_committed_batch_survives_resource_stop` 是 `0 != 4`。该测试 `tests/unit/test_library_laws.py:120—132` 前两次调用真实预算检查，原意第三次才人工中断；首次真实预算阻断被 `pytest.raises` 捕获后，记录数变成 0，因而呈现后续断言失败。不能声称 38 项 XML 都直接报同一种异常。

## 环境与源码证据

- `environment-probe.json` 的空目录探针：C 盘空闲 **42,742,038,528** 字节，所需 **42,949,673,000**（40 GiB 加本次 40 字节），返回 `LIBRARY_DISK_BUDGET`；D 盘空闲 **237,967,073,280** 字节，同样请求允许。只记录该探针时点值，不推称全套每项开始时的精确空间。
- `src/cn_contract/library/budget.py:48—49` 的门槛仍是 `40 * GIB + additional_bytes`。与基线 `13f53bf986fb672834d2952c0276b52ea41b3d9c` 逐字节相同，两者 SHA256 均为 `b5e7634d04ed913984b099d5e30aaf73e920efeeab49d3c3c75925f5c05ffa51`；Git diff 为空。
- 独立重算 `full-verification.json` 全部 **484** 个输入 SHA256：全套前、全套后、恢复后当前值完全相同，差异 **0**。没有用修改测试、降低预算或改产品的方式恢复。
- 恢复命令中的 38 个 nodeid、原全套失败 nodeid 和恢复 XML 用例集合完全一致，无遗漏、增加或重复；参数化名称也逐字匹配。恢复仅使用唯一的 D 盘 `--basetemp`，日志为 **38 passed in 13.54s**。
- 四项 gate（schema、defaults、sources、runtime dependencies）退出码均为 **0**；本审查核对既有记录，没有重复执行 gate。

机器可读独立核对：`environment-source-check.json`，核对脚本 `environment-check.py`。原始全套失败、恢复日志/XML 均保留。本次未删除全局临时目录、修改资源阈值或产品文件，也未验证真实模型、真实语料、安装包或 GUI。
