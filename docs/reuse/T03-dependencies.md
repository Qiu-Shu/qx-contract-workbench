# T03 PDF 与安全 XML 开发依赖记录

记录上下文日期：2026-10-03，Asia/Shanghai；检查时间使用本机实际 UTC。正式应用/测试锁为 Windows AMD64、CPython 3.12.14 的 35 包完整闭包。应用根为 pydantic、sqlalchemy、fastapi、pwdlib[argon2]、pdfplumber、defusedxml；测试根为 pytest9.0.3、httpx0.28.1；setuptools84.0.0 为独立构建锁。以下先保留安装前候选审计历史，随后记录正式合并和安装后实读。仅使用公开元数据、目标 wheel 及独立虚构开发材料，没有真实合同或企查查材料。

根选择：pdfplumber==0.11.10（T00/G06 固定发行版）、defusedxml==0.7.1。官方逐版本 PyPI 元数据实际确认 pdfplumber 要求 pdfminer.six==20260107、Pillow>=12.2.0、pypdfium2>=5.9.0；defusedxml 无 Requires-Dist。pip 本机 binary-only dry-run 实际解析完整 35 包闭包；T02 原 28 包所有版本不变。

| 新包 | 固定版本 | 明确 SPDX | 实测目标 wheel SHA-256 |
| --- | --- | --- | --- |
| pdfplumber | 0.11.10 | unknown | 7741ea81bf165b474b153e6789d10d18e06b6ddcf3ec84289c3ef2fed6802580 |
| defusedxml | 0.7.1 | unknown | a352e7e428770286cc899e2542b6cdaedb2b4953ff269a210103ec58f6198a61 |
| pdfminer-six | 20260107 | MIT | 366585ba97e80dffa8f00cebe303d2f381884d8637af4ce422f1df3ef38111a9 |
| pillow | 12.3.0 | MIT-CMU | a2b55dd6b2a4c4b7d87ffa56bdb33fdc5fdb9a462173861a7bc097f17d91cb09 |
| pypdfium2 | 5.13.0 | unknown | 47dcca2a8d507b5fd24f94c3c9d48fb379430f097bc20f01beff6c963ffbcedb |
| charset-normalizer | 3.5.2 | unknown | 780fbe7cab297b81dad9fb8dc5eb003c0468ffb0d9e5f65068c53a34661a96bc |
| cryptography | 50.0.2 | Apache-2.0 OR BSD-3-Clause | 7afa5a6602a9f29af1f3a2965f831bae7c9d5d597b7cbb716d41ab3b7d89879c |

新 7 个 wheel 全部实际下载，独立 SHA-256 与官方逐版本 JSON 及 pip report 同时吻合；目标 CPython/abi3/纯 Python tag 与本机 sys_tags 兼容。原 28 个 T02 已下载 wheel 从历史缓存读取、逐个再次核对哈希，复制到本轮 wheelhouse；不冒称重新下载。完整离线 hash-lock dry-run 在本轮 wheelhouse 可解析全部 35 包。

新增 wheel 逐字节提取 27 个许可/NOTICE 等文件；加上继承 T02 33 份，应用/测试候选共 60 份。PDFium2 有 19 份证据，其中 BUILD_LICENSES 为 15 个名字/16 份文件（libjpeg_turbo 两份）；另有 Apache-2.0/BSD-3-Clause/CC-BY-4.0 全文。Pillow 单个 78016 字节组合 LICENSE 全文保留，不能把主包 MIT-CMU 当成所有内嵌库的统一许可。cryptography 主包双许可三份全文保留，原生 OpenSSL/构建依赖供应链未独立审计。

pdfplumber、defusedxml、pypdfium2、charset-normalizer 无明确 License-Expression，均登记 unknown，保留原始 License/Classifier/全文；未自行猜测 SPDX。PDFium BUILD_LICENSES 中 15 个原生组件的名称、证据与审批状态单独登记在 bundled_code_license_declarations，版本与独立源 commit 未知，SPDX 不推断，production 许可范围待审。

pypdfium2 wheel 内的两个 version.json 已提取并实测 SHA-256，声明 wrapper 5.13.0、PDFium 153.0.7999.0/origin pdfium-binaries/flags=[]，均 hash=null。这里只是构件内自声明，不能视为源提交独立核验或源构建安全批准。

新 7 个逐版本 PyPI 接口 vulnerabilities=[]，仅表示当时该接口没有列告警，不是完整安全审查。T02 既有 pytest8.4.2 告警/排除历史、旧许可路径、独立 setuptools84.0.0/build packages/内嵌 NOTICE 均继承且不删除，构建包本轮未重新下载。T02 28 包已安装元数据证据明确限定 inherited_T02；新增7包 installed_metadata_verified=false，不能称T03已安装或pipcheck通过。

G06 的 T00 read_verified/development runtime_candidate 状态不等于 production 批准或法源批准。候选 manifest 保持 approved_by=null、approved_at=null、approved_scope=[]、approved_for_production=false，新增 G06 production/原生 PDFium-Pillow-OpenSSL 构建与许可范围/OCR 阻断。python-docx/G08 暂不安装；本任务未下载 OCR 或模型，没有真实网络识别。FastAPI 既有 OpenTelemetry 只继承 API，没有 SDK/exporter。

实际执行记录（所有单元测试运行数均为 0）：

| 命令 | 退出码 | 实际数量/结果 |
| --- | --- | --- |
| `.venv/Scripts/python.exe -X utf8 .audit-local/t03-dependencies/prepare.py` | 0 | 2 个逐版本公开根元数据；冻结 T02 28 包 |
| `.venv/Scripts/python.exe -X utf8 -m pip install --dry-run --ignore-installed --only-binary=:all: --index-url https://pypi.org/simple --report .audit-local/t03-dependencies/pip-report.json -r .audit-local/t03-dependencies/roots.txt -c .audit-local/t03-dependencies/baseline.constraints` | 0 | 完整 35 包；未安装 |
| 复制 T02 审计 helper 的首次 PowerShell 内联命令（完整原命令见下方代码块） | 1 | PowerShell ParserError: An expression was expected after `(`；Python 未启动；改为文件脚本，不标 PASS |
| `.venv/Scripts/python.exe -X utf8 .audit-local/t03-dependencies/copy_helpers.py` | 0 | 独立 helper 保存；原生内嵌许可目录纳入 |
| `.venv/Scripts/python.exe -X utf8 .audit-local/t03-dependencies/audit.py` | 0 | 新 7 wheel/27 许可实测；继承 28 wheel 哈希再核对；总 35 包/60 许可 |
| `.venv/Scripts/python.exe -X utf8 .audit-local/t03-dependencies/audit_bundles.py` | 0 | PDFium 15 原生组件名字/16 许可文件/2 个 version.json 实测 |
| `.venv/Scripts/python.exe -X utf8 .audit-local/t03-dependencies/verify.py` | 0 | 35 wheel/60 许可/40 依赖边；T02 原 28 包版本及正式锁未变；1 build 保留；0 本次失败 |
| `.venv/Scripts/python.exe -X utf8 -m pip install --dry-run --ignore-installed --no-index --find-links .audit-local/t03-dependencies/wheelhouse --only-binary=:all: --require-hashes --report .audit-local/t03-dependencies/offline-pip-report.json -r .audit-local/t03-dependencies/candidate.lock` | 0 | 完整35包离线hash解析可用；未安装 |

失败的 PowerShell 原命令（仅记录，未再次执行）：

```powershell
.venv/Scripts/python.exe -X utf8 -c "from pathlib import Path; p=Path('.audit-local/t03-dependencies/audit.py'); source=Path('.audit-local/t02-dependencies/audit.py').read_text(encoding='utf-8').split('def main():')[0]; source=source.replace('T02','T03'); source=source.replace('if not (in_licenses or', \"if not (any(part.lower() in {'licenses', 'license'} for part in path.parts[:-1]) or in_licenses or\"); p.write_text(source,encoding='utf-8')"
```

候选安装文件：`.audit-local/t03-dependencies/candidate.lock`。完整机器证据：candidate.manifest.json、baseline.manifest.json、root-discovery.json、pip-report.json、offline-pip-report.json、audit-result.json、bundled-audit-result.json、offline-verification.json、registry/、wheelhouse/、metadata/、notices/、native-metadata/。

以上为安装前候选的历史记录，未把当时的未安装状态改写为安装后通过。PowerShell ParserError 属于辅助命令失败，不计作应用测试失败。

## 正式合并与安装后实际复验

T02 提交 f30ea73 的 28 个固定包版本、目标 wheel SHA-256、旧 pytest8.4.2 许可及排除告警保留。独立 requirements-build.lock 和 build_packages 原样保留；本轮再次读取继承缓存核验 setuptools84.0.0 的 1 个 wheel、12 个 vendored 分发和 17 份许可/NOTICE，没有重新下载构建包。T02 安装元数据、真实安装和 pip check 历史证据留在正式 manifest.history 与原阶段报告；候选 baseline.manifest.json 仍保存旧 28 包全文。

正式 requirements.lock 使用 --only-binary=:all: 与每包目标 wheel SHA-256，pwdlib[argon2] extra 原样保留。逐 wheel METADATA 原字节、Requires-Dist 在 Windows CPython3.12 及启用 extra 下的条件、完整 40 条依赖边、根可达闭包和 60 份 LICENSE/NOTICE 等原始字节均已核对。新 7 包的 27 份许可被纳入正式 sources/third-party-notices/runtime；全部 60 份应用/测试许可可从锁内 local_target 寻址。两个 pypdfium2 version.json 原字节也纳入正式证据，PDFium 153.0.7999.0 是构件自声明，其原始源 hash/commit 仍未独立证实。

根节点已执行本地 --no-index --require-hashes 安装；其 .audit-local/t03-install.json 实际 7 个新增包 SHA-256 全部与锁一致。本审计员没有安装环境。随后 UTF-8 pip inspect 实读环境 53 个分发，核对正式应用/测试 35 个包及独立构建 1 个包的版本和 Requires-Dist；其余环境分发属于开发工具等，不纳入应用锁。pip check 实际退出 0。离线 --ignore-installed dry-run 在正式 requirements.lock 上重新解析 35 包，未重装环境。

全部发行包保持 review_status=read_verified、scope=development、approved_by=null、approved_at=null、approved_scope=[]；顶层 approved_for_production=false。PDFium BUILD_LICENSES 的 15 个组件名字/16 份文件保持独立组件版本及源提交 null，许可表达式 unknown，使用范围未批准；Pillow 的组合 LICENSE 和 cryptography 的双许可全文原字节保留。公开登记 vulnerabilities=[] 只表示接口当时未列告警，不是安全批准、源供应链批准、法源批准或生产批准。原生 PDFium/Pillow/OpenSSL、既有原生扩展、setuptools MPL/LGPL 等使用范围、规则与数据政策仍为生产阻断；OCR 未部署，真实模型和 QCC 保持关闭，mock 不能正式签发。

下列实际命令均为依赖核验，单元测试运行数为 0：

| 实际命令 | 退出码 | 结果数量 |
| --- | --- | --- |
| `.venv/Scripts/python.exe -X utf8 .audit-local/t03-dependencies/verify.py` 合并前实际复核 | 0 | 35 wheel/60 许可/40 边；冻结 T02 28 个固定版本；0 失败 |
| `.venv/Scripts/python.exe -X utf8 .audit-local/t03-dependencies/merge.py` | 0 | 35 包、60 份许可复制或同字节匹配、2 个原生版本 JSON；保留构建及旧 pytest 目录 |
| `.venv/Scripts/python.exe -X utf8 .audit-local/t03-dependencies/installed_verify.py` | 0 | 实读 53 分发；35 应用/测试+1 构建元数据；7 个 root install 哈希；pip check 退出 0 |
| `.venv/Scripts/python.exe -X utf8 -m pip install --dry-run --ignore-installed --no-index --find-links .audit-local/t03-dependencies/wheelhouse --only-binary=:all: --require-hashes --report .audit-local/t03-dependencies/formal-offline-pip-report.json -r requirements.lock` | 0 | 正式 hash-lock 完整离线解析 35 包；未安装 |
| `.venv/Scripts/python.exe -X utf8 .audit-local/t03-dependencies/verify.py --merged` | 0 | 35 wheel/60 许可/40 边、36 个安装元数据、7 个 root install 哈希；独立构建 1 wheel/12 vendored/17 许可；0 失败 |
| `git diff --check -- requirements.lock sources/runtime-dependencies.lock.json sources/third-party-notices/runtime docs/reuse/T03-dependencies.md` | 0 | 0 差异空白错误；未提交 |

本阶段完成开发依赖正式合并及实装复验，不代表 T03 文档解析功能、工程演示、法律样本验收、真实试点批准或生产完成。完整本地报告、wheel、METADATA、JSON 和核验脚本在 Git 忽略的 .audit-local/t03-dependencies/；本说明与正式 hash 锁及第三方许可可提交，未提交缓存或真实材料。
