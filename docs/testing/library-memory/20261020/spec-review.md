# CH-00B2 Spec 独立复核（2026-10-20）

本轮基线：`4c303c541a6bfe08225642837ccda72fb761bcb2`。审查本轮3个产品文件差异、新增单测、本片计划及 `baseline.json` / `final.json` / `measure.py`；没有将历史 CH-06A 审查代入本轮。**可操作缺陷 0，未发现规格缺失或越界。**

规格“保留旧normalize契约”“按同一字符规范化规则定位指定范围”“不保留整篇坐标列表”已满足：`library/text.py:41-56` 保持空白合并、兼容展开、零宽与原字符位置语义，仅保存计数和两个边界；`library/service.py:192-201` 与 `assistant/tools/library.py:70-86` 沿用原查询、排序、片段范围和首个命中选择。权限、代际与原文摘要检查未改。索引构建仍可使用旧完整映射，未越界改迁移或代际格式。

独立探针：`.venv/Scripts/python.exe .local/library-memory-20261020/spec-probe.py`，实际 **exit 0**。与保留的旧映射对照 **9,880 个 Unicode 区间**；实际独立合成库上 `library.search` / `adapter.search` 两路径分别替换为旧映射定位后，完整输出与新路径及两份证据摘要均相同。核对合成 CSV 仅1条、正文250,009字符、源文件与代际相同，当前3个产品文件摘要均等于final.json。未运行完整回归。

性能证据表述准确，但应保留以下范围：

| 路径 | Python追踪峰值中位数 | 降幅 | 未追踪计时中位数 |
|---|---|---|---|
| library.search | 27,134,250 → 3,330,636 B | 87.725% | 81.49 → 88.14 ms（+8.15%） |
| adapter.search | 27,135,867 → 3,332,261 B | 87.720% | 171.48 → 181.69 ms（+5.95%） |

残余风险：仅单条合成长文、命中靠近末尾、热排序缓存、每组3次样本；不是统计显著的普遍耗时结论。可以称本样本Python分配峰值下降约87.7%，同时披露约6–8%的样本中位耗时增加；不能称整体提速、整机RSS/GUI/冷启动/安装包改善。更长记录或临近2秒搜索截止的多候选负载未测，时间成本仍可能影响分页/超时出现频率；本片没有改变截止机制。

已读取真实RED日志（旧算法峰值21,241,164 B，断言1 MiB限额失败）及目标日志21 passed，但这些不是本代理重跑结果。`git rev-parse` / `git diff` /文件读取退出码均0；产品差异为28增8删。

最终核对摘要（SHA256）：

| 文件 | 摘要 |
|---|---|
| library/text.py | 4F8C61A72B93FCB549604A711AFC511A2DE3E42D3A63C4E5EE0591B6E0A5A854 |
| library/service.py | 4BE2E576E9D40E90ACE8F6946D9D1FD67BC250A45DFE24B527DCFBD28CE7C155 |
| assistant/tools/library.py | D50E0DD0A82E556D7A314B41B5507A5416D206B5ABC14EE7E87EAA9C52BF4522 |
| tests/unit/test_library_span.py | A153082DE7DFF238F064C32E82DC122FFAD7E3F44062CB60C9701E1CD8BE8934 |
| docs/plans/2026-10-20-library-memory.md | 9C67BAD7A1E1DFFF5C3B485716320ADD254991CD71131B9806934865E5FF79C9 |
| measure.py | 437F4C8AF7A29798EE00F93C7D07EA51014E03B985FCA2077772CE794E7CD616 |
| spec-probe.py | A77882D8D70D9BC5FF287BB5BAC6CE88D117361336815F7251A31CEA585C68E5 |

未读真实法库、未联网、未改产品或既有测试。完整权限回归由主代理执行；本报告不替代其实际结果。
