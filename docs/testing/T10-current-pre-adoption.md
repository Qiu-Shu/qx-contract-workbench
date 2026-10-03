# T10 当前 T09 基线下的采用前只读核对

2026-10-03，workspace `D:\Documents\ChatGPT\律所项目`。状态：**STATIC_PRE_ADOPTION_CHECK_COMPLETE / T10_NOT_INSTALLED / UI_NOT_RUN / PRODUCTION_UNAPPROVED**。此记录只核现有候选与当前正式依赖；不构成安装、UI、实际服务、native、字体、法律或生产验收。

当前正式锁是 T09 已采用的 **53 包**，当前静态环境 **69 分发**。T10 历史 `candidate.manifest.json` 的 53=旧正式51+模板2，与当前正式53=旧51+DOCX2不是同一组合。历史 `prospective.manifest.json` 的55才包含当前53及模板2，但其 actual51/env68/T09_NOT_INSTALLED 字段仍是候选历史时点，不能复制为当前事实。

## 实际字节与闭包

独立脚本没有执行候选 verify.py 或任何 pip 命令。以项目 Python `-B -S` 跳过 site/.pth，显式仅使用 pure packaging 做 requirement/specifier/tag 语义；读完整 wheel、cached registry、METADATA、notice、JSON 锁及实际 installed metadata，不导入 Jinja2/MarkupSafe/lxml/docx/native。

| 核对 | 实际结果 |
|---|---|
| T10 候选原 freeze | 100/100 文件 bytes/SHA 匹配，drift0；未刷新候选 checked_at 或改变旧 freeze |
| 当前53 vs prospective55 | 53 个 wheel 完整 bytes、53 METADATA、95 notice 完整 bytes 与 current cache/正式证据/installed 对应文件一致；原78 resolved/excluded/extras 精确一致 |
| prospective55 | 55 wheel、42,489,320 bytes；97 主 notice，79 独立推导有效边，55 reachable；只有新 `Jinja2→MarkupSafe>=2.0` 一边 |
| build | 完整 build 1 package 对象与当前正式记录一致；独立17 notice 当前 bytes 匹配 |
| 新增包集合 | 仅 Jinja2 3.1.6 与 MarkupSafe 3.0.4；没有升级旧53、开启 Babel/i18n 或新增前端框架 |
| 历史 offline report | prospective-pip-report 55 条 file://、目标 hash 与实际缓存 wheel 一致；这里只读历史 dry-run，不声称本轮重新解析/安装 |
| 当前环境 | 69 静态 METADATA 分发；Jinja2/MarkupSafe/docling/docling-slim 未安装 |

新 wheel 实际仍为 Jinja2 `85ece4451f492d0c13c5dd7c13a64681a86afae63a5f347908daf103ce6d2f67`（134899 bytes）、MarkupSafe `11935df9bf455ed0c04eb87bcd720f02b1fe5e02128a9430f23aed6f93336fc7`（14303 bytes）。55组合字节一致不代表新库已经安装或 UI 安全通过。

## 完整记录不能覆盖

当前53与 prospective 中对应53的**完整 JSON 对象均不完全相同**；独立逐叶记录共164个 evidence_location 差异、61个 state_or_time 差异，invariant_change 0。具体 JSON pointer、current/prospective 原值在 `.audit-local/t10-current-pre-adoption/current53-prospective-differences.json`，24个顶层字段差异在 `manifest-top-level-differences.json`，没有把差异隐藏成全记录一致。

旧51各有 `/packages/<name>/wheel_cache`、`inherited_wheel_cache`、`installed_metadata_scope` 差异。例如当前 pydantic 使用 `.audit-local/t07-dependencies/wheelhouse/...`，prospective 使用 `.audit-local/t10-dependencies/wheelhouse/...`，两份实际 wheel bytes 相同；历史安装scope仍应保留原正式值。

docx/lxml 另有推广位置差异，例如 `/packages/python-docx/metadata_cache` 当前是 `sources/evidence/runtime/T09/metadata/python-docx-1.2.0.METADATA`，prospective 仍为 `.audit-local/t09-dependencies/metadata/...`；registry、主 notice 的 local_target、lxml inline local_target 亦分别指向正式 sources 与候选证据目录，实际 bytes 匹配。当前 `scope=development_runtime_only`、`installed_metadata_verified=true`、`installed_metadata_status=T09_actual_project_installed_metadata_byte_verified`、`installed_version` 正确版本，prospective 仍是 candidate/false/T09_NOT_INSTALLED/未登记版本。

采用时唯一 writer 应以**当前 runtime manifest 的53完整 package 对象**和 build 完整记录为基线，保留现有锁条目、T09_actual_installation、环境证据和历史；只 append 两个模板库，再明确新根 `jinja2==3.1.6`。不要以 prospective55 全对象覆盖正式锁、回退 old records 到候选scope，也不要将历史 actual51/env68 写成新事实。需要改变证据保存位置时明确新增证据登记而不抹原历史。

`adoption-preservation-contract.json` 保存当前 manifest SHA、53完整对象的 canonical JSON SHA、唯一可新增两包及建议离线 argv，便于实际采用后逐项比对。它是审阅资料，不是正式运行锁或已执行安装计划。

## 模板、source 与 native 边界

独立对实际 wheel `jinja2/environment.py` 做 AST 解析，确认 `Environment.__init__` 的 autoescape 默认 **False**；3个选取静态 API 源文件与实际 wheel bytes 一致。T10 自有 HTML 模板应显式 `Environment(autoescape=True)`，严格未定义变量、固定自有模板目录。不得对不可信原文/意见/标题/文件名使用 `|safe`、Markup 或自称 `__html__` 对象；不把用户内容变为 template source、loader path 或可调用对象。HTML 文本、属性、URL及JS JSON分别做上下文编码；JS用textContent，不能拼接原文到innerHTML/事件/CSS或双引号属性中的未处理JSON。以上是未来实现/攻击验证要求，本轮 render/浏览器/服务测试0。

G09 当前实际为 docling `reference_only`、`included_in_runtime=false`、`dependency_review=not_runtime_dependency`，生产批准 null/空。它不是 Jinja runtime 来源；使用参考方法不能顺带安装 docling/OCR/模型或开放 connector。G01–G13 等当前源批准空值保留；未来明确开发源采用声明由唯一 writer 按实际使用范围记录，不把候选或 reference 误标生产批准。G11 未批准范围仍阻断。

新两 package/build、current source 的 approved_by/approved_at 都是null、approved_scope空，当前与prospective全局生产批准false。Jinja2 License-Expression unknown 与完整 BSD条款证据分开保留；MarkupSafe BSD-3-Clause 不自动批准项目生产/数据政策。

MarkupSafe 1 PYD、11776 bytes及4527-byte `_speedups.c` 完整 hash 核对通过；startup/postinstall成员0，目标native未执行、whole_native_build_verified=false。历史PE import名字仍只是静态证据，不能证明DLL加载、源commit、可复现构建或MS runtime分发批准。当前T09的lxml组件/native未知限制、未许可XSL和继承旧build/PDFium/Pillow/OpenSSL/pywin32范围不得被模板采用消除。

## 后续实际离线采用命令（本轮 NOT_RUN）

唯一 writer 在已授权开发任务内先生成新的正式55锁，核旧53完整records/hash不变、新两包证据及开发使用范围，然后可使用新正式锁做实际离线安装，原候选保持历史：

```powershell
& '.venv/Scripts/python.exe' -X utf8 -m pip install --no-index --no-cache-dir --find-links '.audit-local/t10-dependencies/wheelhouse' --only-binary=:all: --require-hashes --report '<new-T10-actual-install-report>' -r '<new-formal-T10-requirements.lock>'
```

以上占位路径应由执行者换成新的实际证据/正式锁路径，并捕获真实 argv、exit、actual安装条目、check、inspect及安装后 METADATA/notice/RECORD。正常 pip 解释器可能执行既有 pywin32 自动bootstrap，须如实记录，不能将 pure static 0hook 结论移植给未来安装。当前69不能提前称未来71实装；安装发生后重新数实际分发、核旧69版本及新两包并保存独立实际证据。此预检不另发安装、native、字体、账号或生产授权。

## 本轮实际命令及证据

| 实际命令 | exit | 实际结果 |
|---|---:|---|
| Get-Content/目录清单读取T10候选、freeze、resolve/static-api与T10-preflight；pure Python摘要current/prospective/source G09 | 0 | 只读定位历史53/55与当前53/69；长输出截断部分未当完整证明 |
| `.venv/Scripts/python.exe -B -S -X utf8 .audit-local/t10-current-pre-adoption/audit.py` | 0 | 100freeze/53exactwheel+META/95notice/55-97-79、差异分类/记录如上，findings0 |
| `.venv/Scripts/python.exe -B -S -X utf8 .audit-local/t10-current-pre-adoption/capture.py` | 0 | 最终独立 audit exit0，实际argv/cwd/exit及stdout/stderr保存 |
| `.venv/Scripts/python.exe -B -S -X utf8 .audit-local/t10-current-pre-adoption/seal.py` | 0 | 566/566读取来源SHA/bytes无漂移，12自产文件封存（不将seal自身纳入循环hash） |

实际install/network/候选verify/target import/native load/Word/UI/business tests均0；本轮没有 observed 功能或辅助失败，不能虚造RED/GREEN。完整独立输出/输入SHA/差异和保留合同在审阅目录；最终 capture 和566来源重核已完成，读回当前来源无漂移。报告补入实际封存结果并显式补核global false后，仅重封审阅自产文件，不修改任何输入。当前/未来包计数、字节兼容和完整record差异必须一起阅读，不能把此静态结果称已安装或UI PASS。
