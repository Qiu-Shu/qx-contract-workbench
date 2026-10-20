# CH-06A Standards 独立审查

基线 `ced22116edc736b55712d6c005917b37a3604ee1`；审查未提交工作树（空提交日志不代表无改动）。已全文读 domain 增量、tools 三文件及两项新测试，核对原件、权限、数据库复用链；适用 AGENTS.md、CONTRIBUTING.md、v2.0 与本片计划，按 ponytail full 审查。

## 初审：2 项 P2，复核已修

- **硬边界问题：命中字段未按原件核实。** `src/cn_contract/assistant/tools/library.py:78-86`：标题标签只核枚举；查询词在正文即可接受 title 命中。独立合成正文在 1200 字之后含关键词、原题无关键词，损坏 hit 标题及 match_field 后仍输出 title 引用，摘录也无关键词。违反本片计划第 7、9 行的标题/正文分开与不信索引标题。需对 title 分支用原件标题独立核验；不是命名或抽象偏好。
- **硬边界问题：拒绝前泄露查询内容到警告。** `src/cn_contract/assistant/tools/service.py:22`：`model_dump` 默认发序列化警告；复制 DTO 中不合法 bytes 查询虽被固定码拒绝，警告仍包含完整输入。探针捕获 `PRIVATE_QUERY_MARKER`。与敏感材料不得进入公开日志的 AGENTS.md 第 29 行及错误脱敏边界冲突。沿用 adapter 的 `warnings=False` 即可；不是判断式 smell。

无额外 smell 发现：DTO 集中 domain；适配器复用现有读取/清洗/分段，授权复用 `_owned/_expected`；未把逻辑塞入主入口；无新依赖、持久 schema、网络、HTTP/UI。

## 实际验证

- `.venv/Scripts/python.exe -m pytest .local/library-adapter-20261020/standards_probe.py -q -p no:cacheprovider`（初版仅标题探针）：exit 1，1 failed。
- 同命令加 `::test_rejected_copied_input_does_not_log_query_content`：exit 1，1 failed。
- `.venv/Scripts/python.exe -m pytest tests/integration/test_assistant_library_tools.py::test_file_io_does_not_hold_business_database_transaction tests/integration/test_assistant_library_tools.py::test_real_search_read_and_repeat_keep_exact_source_without_creating_run tests/integration/test_assistant_library_tools.py::test_errors_are_sanitized_and_current_permission_wins -q -p no:cacheprovider`：exit 0，6 passed。
- 读取、diff、哈希及基线日志命令均 exit 0；只用临时独立合成库。未跑全套，未触碰 F 盘真实库、模型、安装版或网络。

## 初审 SHA256

| 文件 | SHA256 |
|---|---|
| domain.py | 89C7D21F5E87E3A0C4DCFBA645670EC5B45FC83638061996116DB9D5A4A6FB46 |
| tools/__init__.py | 6CEDC11C9448204EFF763D37BAFC5659FD1A7D35191369B5D2D3AA0C55CBDD74 |
| tools/library.py | B332CD208A6B907C6B9FBB461103BA31293AAAA67C730ECB013FF0AD1907A542 |
| tools/service.py | F3B69069090E60B57241FCC0DA997700A0BBDBED308B8F977960EF811261EB7E |
| test_assistant_library_adapter.py | CB6695BC23236883732EEFBAC0CACDF02757C2AD38C58ADE65734100E24A879D |
| test_assistant_library_tools.py | 51A2E8496217567A891514EB978114CA69B9A5E1D9804E89295F2D8A040BE308 |

## 修复复核

原 `standards_probe.py` 两项均通过：`.venv/Scripts/python.exe -m pytest .local/library-adapter-20261020/standards_probe.py -q -p no:cacheprovider`，exit 0，2 passed（1.43 秒）。修复后 `_matches:73-87` 重算原文规范化映射及首个命中位置，拒绝错误字段标签；`service.py:22,30,33` 关闭序列化输入警告，再作完整校验。新增正式回归已读取。无剩余 Standards 发现。

整源摘要已改为 `registered_source_sha256`，`source_match=record_quote_matched` 明示只重核引用记录及摘录；此界限与计划一致，不冒称整 CSV 重验。无新依赖/schema/入口扩张。

下列版本与两项独立 GREEN 后记录一致（__init__ 哈希同初审）：

| 文件 | 复核 SHA256 |
|---|---|
| domain.py | AD4DBCEA93859C716C7AE82ACD2A458D5ED8BE0A054F031C35DE5AD1429ECFEA |
| tools/library.py | 1B25AD39C011BD2154FEA09C6DFF87981583111119766FA607884607E4E28581 |
| tools/service.py | 16FCD21A1FAA0609DF4F5409321B57A2DD862B31E274E008AF1BD8A5C8DA9E7E |
| test_assistant_library_adapter.py | A0640B00533359330047D098BAFDC04C194E24F10EB80D21AED5C085CF0D8573 |
| test_assistant_library_tools.py | CD836EA46382000DC5E955DE3C1CE56A7B27928707F09DD8107A5CDD472662ED |
| standards_probe.py | 88189738761D80E47003FC6316A39CE0F925E1B979456CEDD987DFE1B877ACE8 |

未跑全套或真实库；完整 CH-06、整源完整性与生产验收不在本次结论范围。
