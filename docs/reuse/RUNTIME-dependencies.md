# T01 运行与测试依赖记录

T01 的应用基础依赖为 `pydantic==2.13.5`，测试依赖为 `pytest==8.4.2`。本次固定了 Windows AMD64、CPython 3.12.14 的完整 Python `Requires-Dist` 依赖闭包，共 11 个发行包；构建后端 `setuptools==84.0.0` 单独固定。实际安装由父任务执行；本审计只读取安装元数据、公开 PyPI JSON 和 wheel，没有安装包或运行下载的 wheel。

版本、全部发行构件的登记哈希、实际目标 wheel 的下载哈希、来源项目网址和依赖边保存在 `sources/runtime-dependencies.lock.json`。`requirements.lock` 为每个包固定一个匹配目标环境的 wheel SHA-256，并强制使用二进制发行包；因此该文件仅适用于所记录的目标环境。PyPI 登记的其他平台 wheel 和源码包没有逐个下载，不能据此声称已经实测。

| 包 | 固定版本 | 用途组 | 上游登记的 SPDX 表达式 |
| --- | --- | --- | --- |
| pydantic | 2.13.5 | base | MIT |
| annotated-types | 0.8.0 | base | MIT |
| pydantic-core | 2.46.5 | base | MIT |
| typing-extensions | 4.16.0 | base | PSF-2.0 |
| typing-inspection | 0.4.4 | base | MIT |
| pytest | 8.4.2 | test | unknown |
| colorama | 0.4.6 | test | unknown |
| iniconfig | 2.3.0 | test | MIT |
| packaging | 26.3 | test | Apache-2.0 OR BSD-2-Clause |
| pluggy | 1.6.0 | test | unknown |
| pygments | 2.21.0 | test | BSD-2-Clause |

应用与测试的许可和署名证据从已校验的目标 wheel 的 `.dist-info` 目录逐字节提取，共 15 个文件，保存在 `sources/third-party-notices/runtime/<name>-<version>/`；每个文件的 wheel 内部路径、本地相对路径、大小和 SHA-256 均有记录。`packaging` 的三份许可文件全部保留；`pytest`、`pygments` 的 AUTHORS 文件也随 wheel 的许可目录保留。`pytest`、`colorama`、`pluggy` 没有明确 `License-Expression` 字段，故保留 `unknown`，同时记录原始 `License`、分类声明和许可全文，不由本审计自行推定 SPDX 标识。

构建后端单独位于 `requirements-build.lock`、依赖锁的 `build_packages` 与 `roots.build`。该 wheel 的主包登记 MIT，实际 `Requires-Dist` 仅有未启用的 extras；wheel 内另嵌入 12 个分发包，共保留 17 份主包/嵌入包 LICENSE、COPYING、NOTICE 文件。嵌入包元数据与证据记录在 `vendored_distributions`，不能将主包 MIT 登记视为所有内嵌内容的统一许可。其中 `autocommand==2.2.2` 的原始声明为 `LGPLv3`，未提供 SPDX 字段，故记录 `unknown` 并保留全文，其分发使用范围审批仍待审。两份 NOTICE 另登记 `validate-pyproject` 的 MPL-2.0 与 `fastjsonschema` 的 BSD-3-Clause，保存在 `bundled_code_license_declarations`；原包未说明该嵌入代码的版本与源提交，明确保留为空并记录生产阻断。

候选构建版本 82.0.0 的 [PyPI 元数据](https://pypi.org/pypi/setuptools/82.0.0/json) 登记了 `CVE-2026-59890` / `GHSA-h35f-9h28-mq5c`，修复版本为 83.0.0；据此排除 82.0.0。实际采用的 [84.0.0 元数据](https://pypi.org/pypi/setuptools/84.0.0/json) 在核验时返回 `vulnerabilities=[]`。这只说明该接口当时未列出告警，不等于完成安全审查；两个版本的原始 JSON、SHA-256 与排除理由已保存。

包记录统一为 `review_status=read_verified`、`scope=development`、`approved_by=null`。该状态表示公开发行元数据与证据已读取、目标构件哈希吻合，尚未取得许可使用范围、安全、规则或数据政策的生产批准。原生 `pydantic-core` 的 Rust 构建依赖树、源代码供应链和漏洞评估尚未审计；上游 GitHub commit 没有本轮独立实证，明确保留为空。

Scrapling 及其 fetchers、浏览器和开发工具链继续按 G10 的现有记录管理，不进入本应用锁；pydantic 的 email/timezone extras、pytest 的 dev extras 和其他 T00 候选包也未纳入。Windows 下的 `colorama` 已纳入；Python 3.12 不触发 `exceptiongroup`、`tomli` 的低版本条件依赖。`transitive_requires` 保留全部原始依赖声明，`resolved_dependencies` 与 `excluded_requirements` 记录目标环境的实际选择。

公开发行来源为 [pydantic 2.13.5 的 PyPI 元数据](https://pypi.org/pypi/pydantic/2.13.5/json) 和 [pytest 8.4.2 的 PyPI 元数据](https://pypi.org/pypi/pytest/8.4.2/json)，其他逐版本 URL 见依赖锁。原始 JSON、已校验 wheel、METADATA、`pip inspect` 结果和执行证据保存在 Git 忽略的 `.audit-local/t01-dependencies/`，不含真实合同或企查查材料。

实际执行记录：

| 实际命令 | 退出码 | 结果数量 |
| --- | --- | --- |
| `.venv/Scripts/python.exe -m pip inspect --local` | 1 | Windows GBK 输出失败；无完整结果，不能标 PASS |
| `.venv/Scripts/python.exe -X utf8 -m pip inspect --local` | 0 | 完整 JSON，436776 字节；本轮 11 个固定版本核对吻合 |
| `.venv/Scripts/python.exe -X utf8 .audit-local/t01-dependencies/audit_dependencies.py` | 0 | 应用/测试 11 包、构建 1 包；12 个目标 wheel 下载哈希、32 份许可/署名证据；依赖闭包和本地 METADATA 核对通过 |
| `.venv/Scripts/python.exe -X utf8 .audit-local/t01-dependencies/verify_dependencies.py` | 0 | 离线核对 12 个构件哈希、32 份证据哈希、12 个嵌入分发元数据、2 份代码许可声明、2 个 requirements 文件；0 个失败、单元测试数量 0 |

这不是生产完成、法律样本验收或真实试点批准。mock 仍不能正式签发。锁只支持开发复现，后续变更版本或目标环境时必须重新检查依赖闭包、目标 wheel 与许可证据。
