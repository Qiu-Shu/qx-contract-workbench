# T02 应用与测试依赖记录

本轮为 Windows AMD64、CPython 3.12.14 固定应用及测试依赖完整闭包，共 28 个发行包。应用根为 `pydantic==2.13.5`、`sqlalchemy==2.0.54`、`fastapi==0.142.2`、`pwdlib[argon2]==0.3.1`；测试根为 `pytest==9.0.3`、`httpx==0.28.1`。归一化 `roots.base` 中的 `pwdlib` 配合 `enabled_extras=["argon2"]` 和 `root_requirements` 记录实际 extra。SQLAlchemy 用于 SQLite 持久化；pwdlib 使用维护的 Argon2 库；httpx 用于 ASGI 接口测试。

版本从公开 PyPI JSON 实际读取，随后由本机 pip `--dry-run --ignore-installed --only-binary=:all:` 解析。目标 wheel 全部实际下载并独立计算 SHA-256，同时匹配逐版本 PyPI JSON 与 pip report；target tags 与本机 `sys_tags()` 兼容。完整依赖边及目标条件排除项保存在 `sources/runtime-dependencies.lock.json`，`requirements.lock` 对目标 wheel 强制二进制与 SHA-256。其他发行构件的哈希只来自登记元数据，没有逐个下载测量。

| 包 | 固定版本 | 上游明确 SPDX 表达式 |
| --- | --- | --- |
| annotated-doc | 0.0.5 | MIT |
| annotated-types | 0.8.0 | MIT |
| anyio | 4.15.1 | MIT |
| argon2-cffi | 25.1.0 | MIT |
| argon2-cffi-bindings | 26.1.0 | MIT |
| certifi | 2026.7.22 | unknown |
| cffi | 2.1.1 | MIT-0 |
| colorama | 0.4.6 | unknown |
| fastapi | 0.142.2 | MIT |
| greenlet | 3.5.6 | MIT AND PSF-2.0 |
| h11 | 0.16.0 | unknown |
| httpcore | 1.0.9 | BSD-3-Clause |
| httpx | 0.28.1 | unknown |
| idna | 3.20 | BSD-3-Clause |
| iniconfig | 2.3.0 | MIT |
| opentelemetry-api | 1.45.0 | Apache-2.0 |
| packaging | 26.3 | Apache-2.0 OR BSD-2-Clause |
| pluggy | 1.6.0 | unknown |
| pycparser | 3.0 | BSD-3-Clause |
| pydantic | 2.13.5 | MIT |
| pydantic-core | 2.46.5 | MIT |
| pwdlib | 0.3.1 | unknown |
| pygments | 2.21.0 | BSD-2-Clause |
| pytest | 9.0.3 | MIT |
| sqlalchemy | 2.0.54 | unknown |
| starlette | 1.7.0 | BSD-3-Clause |
| typing-extensions | 4.16.0 | PSF-2.0 |
| typing-inspection | 0.4.4 | MIT |

上表由目标 wheel `License-Expression` 或明确 PyPI `license_expression` 记录，7 个缺少该字段的包保留 `unknown`，不根据常见许可名称自行推断 SPDX。目标 wheel 的 33 个 LICENSE/NOTICE/COPYING 或许可目录署名文件逐字节保存在 `sources/third-party-notices/runtime/<name>-<version>/`，内部路径、字节数、SHA-256 与来源构件 URL 均登记。完整原始 `License`、许可分类声明和证据全文保留以待范围审阅。

SQLAlchemy 初次发现候选为 2.1.2；本轮最终按已批准实现选用实读存在的 [2.0.54](https://pypi.org/pypi/SQLAlchemy/2.0.54/json)，以适配官方 2.0 SQLite/Session 设计。Windows 下该版本的条件依赖 `greenlet==3.5.6` 已纳入。应用及测试闭包没有 `itsdangerous` 或 JWT 库，会话采用服务端随机令牌，不自行实现密码算法。

最初要求保留 `pytest==8.4.2`。本轮 [8.4.2 PyPI 元数据](https://pypi.org/pypi/pytest/8.4.2/json) 实际返回 `CVE-2025-71176` / `GHSA-6w46-j5rx-g56g` / `PYSEC-2026-1845`，描述涉及 UNIX `/tmp/pytest-of-{user}` 目录，并声明修复版本 9.0.3；据此获准改用 [pytest 9.0.3](https://pypi.org/pypi/pytest/9.0.3/json)。Windows 开发目标没有该 UNIX 路径，仍明确保留告警及排除原因在 `excluded_test_releases`，不据此宣称完成漏洞评估。T01 的 `RUNTIME-dependencies.md`、11 包分母及 8.4.2 历史实测不回写；旧版许可目录保留。其余 T01 应用/测试传递包版本未改变。

FastAPI [0.142.2](https://pypi.org/pypi/fastapi/0.142.2/json) 普通 `Requires-Dist` 包含 `opentelemetry-api==1.45.0`；闭包没有 OpenTelemetry SDK/exporter，也没有启用 FastAPI `standard`/`all`/`opentelemetry` extras。应用必须保持遥测默认禁用，无 exporter 配置；审计没有运行遥测或启动对外服务。pwdlib [0.3.1](https://pypi.org/pypi/pwdlib/0.3.1/json) 启用 argon2 extra，完整传递闭包包括 argon2-cffi、argon2-cffi-bindings、cffi 与 pycparser。httpx [0.28.1](https://pypi.org/pypi/httpx/0.28.1/json) 仅为测试根。

全部包的状态为 `review_status=read_verified`、`scope=development`、`approved_by=null`、`approved_at=null`、`approved_scope=[]`，顶层 `approved_for_production=false`。最终 PyPI 接口返回 28 个包 `vulnerabilities=[]`，仅表示当时此接口没有列出的告警，不是安全批准。上游 commit 未独立核验，保留 null；pydantic-core、SQLAlchemy、greenlet、argon2-cffi-bindings、cffi 的原生构建依赖和嵌入库供应链未审计，列为生产阻断。规则、数据政策及许可使用范围审批仍待完成。

独立构建锁 `requirements-build.lock`、`build_packages`、`setuptools==84.0.0` 及其 12 个内嵌分发、17 份许可/NOTICE、MPL 和 LGPL 等声明从 T01 原样保留，本轮没有重新下载或声称重新核验该构建包。Scrapling、浏览器工具链与未启用的 extras 不进入应用闭包。

本依赖审计员没有安装包或导入执行下载的 wheel；父任务随后实际执行 `--require-hashes --no-index` 本地安装。本轮 UTF-8 `pip inspect` 再核对全部 28 个应用/测试包及 1 个独立构建包的实际安装版本和 `Requires-Dist`，正式锁记录 `installed_metadata_verified=true`；候选锁的 false 保留以区分安装前证据。正式 `installed_environment_evidence` 更新为 T02 安装后实读结果，T01 历史实装证据留存原缓存与报告。父任务的真实 install report 每个变更包 SHA-256 均与正式锁相同，未变更的已安装包由实际元数据确认；本审计另执行 `pip check` 退出 0。

实际命令记录（下列是依赖核验，单元测试运行数均为 0）：

| 实际命令 | 退出码 | 结果数量 |
| --- | --- | --- |
| `.venv/Scripts/python.exe -X utf8 .audit-local/t02-dependencies/prepare.py` | 0 | 4 个公开根 discovery JSON；实际版本发现 |
| `.venv/Scripts/python.exe -X utf8 -m pip install --dry-run --ignore-installed --only-binary=:all: --index-url https://pypi.org/simple --report .audit-local/t02-dependencies/pip-report.json -r .audit-local/t02-dependencies/roots.txt -c .audit-local/t02-dependencies/baseline.constraints` | 0，执行 3 次 | 初次候选 27 包；SQLAlchemy2.0/pytest8 候选 28 包；最终 SQLAlchemy2.0/pytest9 候选 28 包 |
| `.venv/Scripts/python.exe -X utf8 .audit-local/t02-dependencies/audit.py` | 0，前两轮 | 初次 27 wheel/32 许可；SQLAlchemy2.0/pytest8 的 28 wheel/34 许可，仅为中间候选 |
| `.venv/Scripts/python.exe -X utf8 .audit-local/t02-dependencies/audit.py` | 1 | 最终候选首轮下载响应 `IncompleteRead(2756 bytes read, 1873 more expected)`；无完整新结果，不能标 PASS |
| `.venv/Scripts/python.exe -X utf8 .audit-local/t02-dependencies/verify.py` | 1 | 过早在下载失败后执行；旧 manifest 与新 pip report SHA-256 不同，拒绝校验，不能标 PASS |
| `.venv/Scripts/python.exe -X utf8 .audit-local/t02-dependencies/audit.py` | 0，重跑 | 最终 28 个目标 wheel 哈希、33 个许可/署名证据、7 个 unknown SPDX；未安装 |
| `.venv/Scripts/python.exe -X utf8 .audit-local/t02-dependencies/verify.py` | 0 | 28 构件哈希、33 许可哈希、34 依赖边、1 requirements 文件、0 本次失败 |
| `.venv/Scripts/python.exe -X utf8 -m pip install --dry-run --ignore-installed --no-index --find-links .audit-local/t02-dependencies/wheelhouse --only-binary=:all: --require-hashes --report .audit-local/t02-dependencies/offline-pip-report.json -r .audit-local/t02-dependencies/candidate.lock` | 0 | 离线 hash-lock 完整解析 28 包，未安装 |
| `.venv/Scripts/python.exe -X utf8 .audit-local/t02-dependencies/merge.py` | 0 | 合并 28 包锁、33 份许可证据；保留旧 pytest 目录和独立 1 个构建包 |
| `.venv/Scripts/python.exe -X utf8 .audit-local/t02-dependencies/installed_verify.py` | 0 | 28 应用/测试与 1 构建安装元数据匹配；UTF-8 pip inspect 46 个环境分发；父真实 install report 中 12 个安装/变更包哈希相同；pip check 0 |
| `.venv/Scripts/python.exe -X utf8 .audit-local/t02-dependencies/verify.py --merged` | 0 | 正式锁 28 构件/33 许可/34 依赖边；安装元数据 29 包；继承构建 1 构件/17 许可原字节；0 失败 |

原始 JSON、目标 wheel、METADATA、候选锁、pip 解析报告及失败/成功执行证据在 Git 忽略的 `.audit-local/t02-dependencies/`；未纳入任何真实合同、企查查结果或密钥。目标环境改变时必须重算 wheel、依赖条件与许可证据。该记录是开发依赖准备，不是生产完成、工程演示、法律样本验收或真实试点批准，mock 仍不能正式签发。
