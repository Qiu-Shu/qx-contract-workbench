# T07 SDK依赖候选审计（未安装、未集成）

记录日期：2026-10-03，显示时区Asia/Shanghai；证据时间为实际UTC。范围仅Windows AMD64、CPython 3.12.14的公开PyPI逐版本元数据、目标wheel及G13已选SDK源码静态核对。仅候选缓存和本候选说明；没有修改正式requirements.lock、requirements-build.lock、pyproject.toml、upstream或runtime正式锁、TASK_STATUS、README及环境，没有提交、账户、真实QCC、付费、真实模型或协议接受。

状态：**NOT_INSTALLED / NOT_INTEGRATED**；全部approved_by/approved_at=null、approved_scope=[]、approved_for_production=false。候选哈希/许可读取和pip dry-run不代表应用测试PASS、SDK运行兼容、法律样本验收、真实试点或生产完成。

固定根：[mcp 2.2.0官方逐版本元数据](https://pypi.org/pypi/mcp/2.2.0/json)与G13 v2.2.0、commit `9972c21aa42054fb1450c5fc614761ed11847ec6`一致；依赖包括固定mcp-types==2.2.0、httpx2、jsonschema、pyjwt[crypto]、python-multipart、Windows pywin32、sse-starlette、uvicorn及已冻结公共依赖。未启用mcp[cli]/[rich]，无OpenTelemetry SDK/exporter。

实际闭包：**51包=既有T03固定35包+新增16包**，35个版本与目标wheel hash全部不变。新16目标wheel实际下载并哈希核对，共8,265,045 bytes；32份新增许可/NOTICE，加既有60份共92份；Windows/Python/extra条件下有效依赖边76条。独立构建setuptools84.0.0的1 wheel/17许可保持原样并从历史缓存复核，不纳入51应用/测试分母。

click8.5.0此前因开发工具已在环境中，本轮将其列入应用候选闭包，未安装或改动其版本。环境53分发在候选审计前后完全一致；既有正式5文件hash一致。新候选没有安装后pip inspect/pip check证据，旧T03安装历史在manifest中明确继承，不能当作T07实装。

| 新包 | 固定版本 | METADATA明确License-Expression | 实测目标wheel SHA-256 |
| --- | --- | --- | --- |
| mcp | 2.2.0 | unknown | bde982589473a060ae145e3406e9a5333fe538c97229ba841f5a7f92be004f81 |
| mcp-types | 2.2.0 | unknown | ea476b73ee86709ab5abc9452385ed36cc05907e582355622e294595c9a04f13 |
| httpx2 | 2.13.1 | BSD-3-Clause | 6dff50fabc270ee5fd25d845d0b078ed20564579744d6d962850975996d2f9a4 |
| httpcore2 | 2.13.1 | BSD-3-Clause | e1e05d4f25f7d7d496bfb96748f6f4b67657b03da069b3a68c36069f3db73d0a |
| jsonschema | 4.26.0 | MIT | d489f15263b8d200f8387e64b4c3a75f06629559fb73deb8fdfb525f2dab50ce |
| pyjwt | 2.15.1 | MIT | 42d59d631f7768a1028a64c7ff581a9bf7519804daf91fc5b6c56e30eec5e193 |
| python-multipart | 0.0.32 | Apache-2.0 | ff6d3f776f16878c894e52e107296ffc890e913c611b1a4ec6c44e2821fe2e23 |
| pywin32 | 312 | unknown | b457f6d628a47e8a7346ce22acb7e1a46a4a78b52e1d17e1af56871bd19a93bc |
| sse-starlette | 3.5.0 | BSD-3-Clause | 3e6e1070df3f0f5d9cea81496de92dbb72f6721871d99748ece67441dd8b7997 |
| uvicorn | 0.54.0 | BSD-3-Clause | 505bdb0f318731d45f1f712071fc781a8981f6847a31c902c9f5e652d4f67faf |
| attrs | 26.1.0 | MIT | c647aa4a12dfbad9333ca4e71fe62ddc36f4e63b2d260a37a8b83d2f043ac309 |
| click | 8.5.0 | BSD-3-Clause | 255bc9599cf7748b4b1a446ccc735421bd08a2ae529a8b88597d3de5664ee360 |
| jsonschema-specifications | 2025.9.1 | MIT | 98802fee3a11ee76ecaca44429fda8a41bff98b00a0f2838151b113f210cc6fe |
| referencing | 0.37.0 | MIT | 381329a9f99628c9069361716891d34ad94af76e461dcb0335825aecc7692231 |
| rpds-py | 2026.6.3 | MIT | 2c958bf94822e9290a40aaf2a822d4bc5c88099093e3948ad6c571eca9272e5f |
| truststore | 0.10.4 | MIT | adaeaecf1cbb5f4de3b1959b42d41f6fab57b2b1666adb59e89cb0b53361d981 |

每个新包均读取官方`/pypi/{name}/{version}/json`，核对目标wheel文件名、size、SHA-256、Requires-Python、Requires-Dist、非yanked及Windows兼容tag；目标wheel原字节和METADATA、许可逐字节保存。所有新包当时PyPI vulnerabilities=[]只表示该接口未列告警，不是全面漏洞或供应链审核。

最终16份PyPI Requires-Dist与wheel METADATA均经PEP508解析比较，依赖语义一致；5个包原始要求字符串因引号/冗余括号等规范化而不同，6个无依赖包PyPI为null而wheel为空列表。完整原字符串仍保留，未强称二者原字节相同。

mcp/mcp-types的legacy License字段声明MIT；mcp LICENSE原文与G13固定许可字节完全相同。但这两个wheel没有明确License-Expression，本记录保持unknown，不把classifier/legacy字符串猜成统一SPDX。pywin32 legacy License=PSF而其内嵌许可并非统一PSF；其License-Expression同样unknown。

pywin32==312含15份许可/NOTICE，按归属路径登记8个组件名：adodbapi、pythonwin、pythonwin-idle、pythoncom、MAPIStubLibrary、isapi、Scintilla、win32。adodbapi有2份相同LGPL Version2.1全文；only/or-later、组件独立版本及源提交未核验，使用和分发范围需另审，不能自动批准。其他许可/版权证据全文保存，组件version/source_commit仍null、license_expression=unknown、审批null。

pywin32静态归档测量55个DLL/PYD与4个startup/postinstall相关文件；rpds-py测量1个PYD。仅核对归档字节/hash，没有加载native模块、运行.pth/postinstall或执行SDK；原生源构建及Rust/Windows组件供应链保持待审。继承PDFium/Pillow/OpenSSL/setuptools等既有许可/生产阻断不删除。

SDK静态核对：mcp/client/__init__.py、session.py、streamable_http.py共3文件与G13已选来源完全相同，G13 LICENSE也完全相同。选取文件匹配不等于整个wheel源提交/构建可复现已核验。mcp-types固定同版2.2.0。

`streamable_http_client(url: str, *, http_client: httpx2.AsyncClient | None=None, terminate_on_close: bool=True)`静态yield为2元(read_stream,write_stream)，ClientSession的initialize/list_tools/call_tool是snake_case。list_tools参数为`self, *, params: types.PaginatedRequestParams | None=None`，不能直接搬旧v1 cursor参数或3元transport tuple。http_client类型为httpx2.AsyncClient，既有httpx0.28.1仍独立保留，不能把两个库的对象混用。

真实MCP/QCC endpoint、账户、权限、工具schema、价格/账单、握手均未验证；runtime contract tests=0、unit tests=0、QCC calls=0、real model calls=0。候选阶段不能宣称真实兼容；G13 runtime使用/传递许可/数据政策仍生产阻断。

## 已纠正且保留的首轮偏差

首轮pip --find-links只增加候选位置，并未使同版本本地wheel优先；实际日志显示pip又从PyPI重取了35个旧wheel，约29,816,087 bytes。因此整个过程不能虚称“旧35包从未重新下载”。没有安装。随后改用35条显式本地wheel direct references（local-roots.txt）重跑解析；corrected report中旧35条download_info.url均为file://，后续审计只下载并测量新增16个wheel，离线hash dry-run全部file://。原日志和偏差记录完整保留。

早期沟通人工估计52/17也已更正：两个pip report机器计数都是51/16；最终候选、校验和本说明仅使用实际51/16，不把估计当证据。

收尾辅助handoff检查曾两次退出1：初次直接比较Requires-Dist原字符串，第二次仅补null/空列表处理，仍被mcp的单双引号差异拒绝。实读确认PyPI规范化与wheel原文语义相同后改用PEP508结构比较，最终16/16一致、退出0。原两次AssertionError及命令保留，不是pip版本冲突，也不计作应用单元测试失败；没有把首次失败改写为PASS。

## 实际命令与数量（均未安装）

| 实际命令 | 退出码 | 实际结果 |
| --- | ---: | --- |
| `.venv/Scripts/python.exe -X utf8 .audit-local/t07-dependencies/prepare.py` | 0 | 1根逐版本元数据；35缓存wheel hash，29,816,087 bytes，冻结35版本/5正式文件/53环境分发 |
| `.venv/Scripts/python.exe -X utf8 -m pip install --dry-run --ignore-installed --only-binary=:all: --no-cache-dir --index-url https://pypi.org/simple --find-links .audit-local/t07-dependencies/wheelhouse --report .audit-local/t07-dependencies/pip-report.json -r .audit-local/t07-dependencies/roots.txt -c .audit-local/t07-dependencies/baseline.constraints` | 0 | 51包计划；首轮偏差：重取旧35wheel；未安装 |
| `.venv/Scripts/python.exe -X utf8 .audit-local/t07-dependencies/local_roots.py` | 0 | 35显式本地wheel refs+固定mcp2.2.0 |
| `.venv/Scripts/python.exe -X utf8 -m pip install --dry-run --ignore-installed --only-binary=:all: --no-cache-dir --index-url https://pypi.org/simple --report .audit-local/t07-dependencies/local-pip-report.json -r .audit-local/t07-dependencies/local-roots.txt -c .audit-local/t07-dependencies/baseline.constraints` | 0 | 51包计划；旧35全部file://、新16HTTPS；未安装 |
| `.venv/Scripts/python.exe -X utf8 .audit-local/t07-dependencies/copy_helpers.py` | 0 | 独立cache helper，未执行下载wheel |
| `.venv/Scripts/python.exe -X utf8 .audit-local/t07-dependencies/audit.py` | 0 | 新16wheel/32许可/8,265,045 bytes；总51包/92许可/76边 |
| `.venv/Scripts/python.exe -X utf8 .audit-local/t07-dependencies/sdk_audit.py` | 0 | 3选取源码+G13 LICENSE原字节匹配；2元tuple/静态签名；0运行测试 |
| `.venv/Scripts/python.exe -X utf8 .audit-local/t07-dependencies/verify.py` | 0 | 51wheel/92许可/76边；35冻结；53环境和5正式文件未变 |
| `.venv/Scripts/python.exe -X utf8 .audit-local/t07-dependencies/bundles.py` | 0 | pywin32 8组件/15许可/55 native/4 hook；rpds 1 native，全部未执行 |
| `.venv/Scripts/python.exe -X utf8 -m pip install --dry-run --ignore-installed --no-index --find-links .audit-local/t07-dependencies/wheelhouse --only-binary=:all: --require-hashes --report .audit-local/t07-dependencies/offline-pip-report.json -r .audit-local/t07-dependencies/candidate.lock` | 0 | 51包离线--require-hashes dry-run，0网络/0安装 |
| `.venv/Scripts/python.exe -X utf8 .audit-local/t07-dependencies/finalize.py` | 0 | T03安装历史隔离继承；T07 NOT_INSTALLED/NOT_INTEGRATED |
| `.venv/Scripts/python.exe -X utf8 .audit-local/t07-dependencies/verify.py` | 0 | 51wheel/92许可/76边/35冻结/1 build+17许可；53环境和5正式文件未变 |
| `.venv/Scripts/python.exe -X utf8 .audit-local/t07-dependencies/write_report.py` | 0 | 只写本候选说明及忽略缓存report.md；未写正式锁/业务 |
| `.venv/Scripts/python.exe -X utf8 .audit-local/t07-dependencies/handoff.py` | 1 | 辅助检查失败：Requires-Dist原字符串严格比较；保留退出1 |
| `.venv/Scripts/python.exe -X utf8 .audit-local/t07-dependencies/handoff.py` | 1 | 辅助检查失败：修正null后仍因mcp单双引号严格比较；保留退出1 |
| `.venv/Scripts/python.exe -X utf8 .audit-local/t07-dependencies/handoff.py` | 0 | 16/16 PEP508依赖语义一致；0报告空白错误；5正式文件/53分发版本不变 |

每条命令的实际argv、工作目录、UTC开始/结束、退出码和log在`.audit-local/t07-dependencies/commands.jsonl`。不存在“未运行标PASS”。辅助写报告及最终handoff核验在收尾追加；应用测试运行0。

## 候选交接

候选文件：`.audit-local/t07-dependencies/candidate.lock`、candidate.manifest.json。机器证据：baseline-state.json、baseline.manifest.json、baseline.constraints、root-discovery.json、pip-report.json（首轮偏差）、local-roots.txt、local-pip-report.json（纠正）、offline-pip-report.json、audit-result.json、sdk-source-audit.json、bundled-audit-result.json、offline-verification.json、handoff.json、commands.jsonl，以及registry/metadata/notices/wheelhouse/sdk-source/native-metadata。所有缓存Git忽略。

后续root确认T07范围后，才可将候选合并为正式锁/许可、实际离线hash安装并复核环境元数据/pip check，再实现独立mock握手/schema/secret/no-network用例。不得修改既有35版本、跳过pywin32 LGPL等许可门、启用真实QCC或把候选读取状态写成应用PASS。
