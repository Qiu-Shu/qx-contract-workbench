# CH-00B2 Standards 独立复核

基线 `4c303c541a6bfe08225642837ccda72fb761bcb2`。本轮重新读取三产品文件增量、新测试、本片计划及测量脚本/JSON；结合 AGENTS.md、CONTRIBUTING.md 与 ponytail full，未沿用 CH-06A 结论。

**结论：未发现需要修复的 Standards 问题。**

- `library/text.py:41-56` 复用既有逐字符 NFKC/casefold 规则，只保留指定区间两端；零宽删除期间空白状态延续，兼容字展开与非 BMP 坐标保持原有 Python 字符语义。`normalize(with_map=True)` 原实现未改，索引构建调用继续兼容。非法类型/空或越界区间返回固定异常。
- `library/service.py:192-201`、`assistant/tools/library.py:73-85` 复用同一 helper；不新增 DTO、依赖、持久 schema 或入口。没有为减少几行重复循环引入额外抽象；现有完整映射 API 和局部映射的职责清楚。
- 新测试以旧映射契约为对照，并直接约束长文临时分配；不是只复述新实现。独立探针从固定基线加载旧模块，对 585 个合成字符串、60,113 个非空区间比对；覆盖兼容展开、组合字符、CRLF、零宽及非 BMP，全部一致。

## 实际验证

- `.venv/Scripts/python.exe -m pytest tests/unit/test_library_span.py -q -p no:cacheprovider`：exit 0，18 passed。
- `.venv/Scripts/python.exe .local/library-memory-20261020/standards_probe.py`：exit 0，585 sources / 60,113 spans。
- `git diff --check`：exit 0。
- PowerShell here-string 输入 `.venv/Scripts/python.exe -` 的证据核对：exit 0；两 JSON 的源文件、代际及两种结果 hash 相同，baseline 输入 hash 与固定 Git 基线一致、final 与当前文件一致，每操作均 3 次计时及 3 次 trace。
- 初次 `rg` 对 Windows 通配路径返回 exit 1；已改 `rg ... src tests -g ...` 重查成功。不是产品测试失败。

## 测量边界

同一 250,009 字符独立合成案例、热排名/字符缓存；计时与 tracemalloc 分开采样。Python 跟踪峰值：library 27,134,250→3,330,636 字节，adapter 27,135,867→3,332,261 字节，均约降低 87.7%。中位耗时分别 81.49→88.14 ms（+8.2%）、171.48→181.69 ms（+6.0%）。应披露这一内存/速度取舍；单记录三次样本不证明普遍性能变化，也不包含既有缓存全部占用、进程 RSS、冷启动、Electron 或安装器。

## 本轮 SHA256

| 文件 | SHA256 |
|---|---|
| library/text.py | 4F8C61A72B93FCB549604A711AFC511A2DE3E42D3A63C4E5EE0591B6E0A5A854 |
| library/service.py | 4BE2E576E9D40E90ACE8F6946D9D1FD67BC250A45DFE24B527DCFBD28CE7C155 |
| assistant/tools/library.py | D50E0DD0A82E556D7A314B41B5507A5416D206B5ABC14EE7E87EAA9C52BF4522 |
| tests/unit/test_library_span.py | A153082DE7DFF238F064C32E82DC122FFAD7E3F44062CB60C9701E1CD8BE8934 |

只读复核，产品未改；仅新增本记录和独立探针。未重跑整套/完整性能基准，未读真实资料，未涉及安装版或网络。
