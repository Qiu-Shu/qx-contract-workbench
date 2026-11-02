# 统一实施计划：阶段验证记录

日期：2026-11-01。工作目录 `D:/Documents/ChatGPT/律所项目`。

## 阶段 0

已完成静态盘点，产品代码未改。见 `docs/architecture/2026-11-01-unified-current-state.md` 和本目录 `phase0-inventory.json`（实际命令、时间、退出码、锁摘要、三仓文件摘要）。基线副本位于 `.local/unified-plan-20261101/baseline/`。核对原有 213 文件不变，原计划复制一致。

实际发现没有 `.github/workflows/`、pytest.ini、tox.ini 或 Makefile；读取不存在路径的诊断不计验证成功。运行测试：NOT_RUN，不能继承 145、419、874 等历史数。

## 已从配置/脚本发现的验证入口

阶段 0 之后的实际验证记录见 [阶段 1 结果](phase1-results.md)；上文 NOT_RUN 仅描述只读盘点时点。本轮命令、日志、退出码与原审计/独立复核副本保留在本目录。

| 范围 | 命令（从主仓执行，另注明者除外） | 使用条件 |
| --- | --- | --- |
| S1/S2 原审计复现 | `.venv/Scripts/python.exe -X utf8 -m pytest .local/audit-20261101/standards/test_review_standards.py -q` | 独立虚构输入、临时 DB、内存传输；先读测试再执行 |
| 业务/微信路由 | `.venv/Scripts/python.exe -X utf8 -m pytest tests/integration/test_assistant_business.py tests/integration/test_weixin_service_routing.py tests/integration/test_weixin_service_runtime.py -q` | 测试内构造 runtime，不启动已安装程序 |
| 桌面业务控制器 | `node scripts/test_assistant_business.mjs` | 现有 Node 合成状态测试 |
| 微信前端 | `node scripts/test_assistant_weixin_personal.mjs` | 现有状态/回读保护测试 |
| 桌面完整 | `npm test`，cwd=`desktop` | package.json 的 node --test tests/*.test.cjs |
| Python 开发检查 | `.venv/Scripts/python.exe -X utf8 -m cn_contract.cli schema --check` | README 入口 |
| 默认配置 | `.venv/Scripts/python.exe -X utf8 scripts/verify_defaults.py` | README 入口 |
| 来源 | `.venv/Scripts/python.exe -X utf8 scripts/verify_sources.py --mode development` | 不等于 release 批准 |
| 运行依赖 | `.venv/Scripts/python.exe -X utf8 scripts/verify_runtime_dependencies.py --mode development` | 不安装或升级依赖 |
| 全量 Python | `.venv/Scripts/python.exe -X utf8 -m pytest tests -q` | 法库测试有 40 GiB 临时盘要求，pilot 需要独立 DuckDB 解释器；按改动影响选范围，不静默跳过后称全过 |

本轮不运行构建/安装；桌面文档记录的 `scripts/prepare_desktop.py` 与 `scripts/build_desktop.ps1` 是后续候选构建入口。环境为 Python 3.12.14 / Node v24.20.0 / npm 11.19.0。每次运行将原始日志与命令结果单独保存；RED 失败和 GREEN 通过不可混计。
