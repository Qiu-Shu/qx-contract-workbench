# T09 实际采用依赖独立静态审核

2026-10-03，workspace `D:\Documents\ChatGPT\律所项目`。状态：**STATIC_ADOPTION_CHECK_COMPLETE / BUSINESS_NOT_REVIEWED / NATIVE_AND_PRODUCTION_UNAPPROVED**。仅审核实际依赖采用及证据字节；业务、Word、字体许可、native 安全与生产验收不在本审核范围。业务尚在作者实现阶段。本审阅未安装、未访问网络、未运行 pip、未导入 docx/lxml/native、未手动调用启动 hook、未运行 Word/COM 或文档解码。

## 已实际核得

独立脚本直接从 `git show e48e83c:<path>` 取得旧正式记录，不用作者或候选 verifier 代替独立结果；直接解析当前 `.venv/Lib/site-packages` 静态 METADATA/RECORD、缓存 registry、wheel archive 和正式证据。以 `.venv/Scripts/python.exe -B -S -X utf8` 跳过 site/.pth，显式路径仅加载 pure packaging 做 PEP 508/440/tag 语义，不导入目标包。

| 项目 | 实际数量/核对 |
|---|---|
| 正式应用/测试锁 | 53 包，旧 51 + python-docx 1.2.0 / lxml 6.1.3；固定版本、wheel hash、root/extras 与 pyproject 一致 |
| 旧记录 | 旧 51 的完整 package 对象与 e48e83c 一致；独立 build 1 个完整对象、17 份 notice 及 requirements-build.lock 保持原样 |
| Wheel | 53 个、42,340,118 bytes；逐包核完整 bytes/SHA、registry 目标 filename/size/hash/non-yanked、CPython 3.12 Windows 兼容 tag |
| Metadata | 53 个实际 installed METADATA 与 wheel/cache 字节一致；Requires-Dist / Requires-Python 与 cached registry 语义一致 |
| 许可/NOTICE | 95 份完整实际 wheel member = 正式证据 = installed bytes/SHA/size；另 build 17 份按同一方式核对 |
| 实际安装 RECORD | 3423 个带 hash 文件，逐个核实际内容、算法 digest、size、路径限定在项目 .venv 内；不声称无 hash 的 RECORD 行已获密码学证明 |
| 依赖闭包 | 从实际 wheel METADATA/root 固定点传播 extras，独立推导 53 reachable / 78 有效边；stored resolved/excluded/extras 一致 |
| 环境 | 当前静态 69 分发；旧 68 版本与先前固定 inspect 一致，唯一新增 python-docx 1.2.0；Jinja2/MarkupSafe/legal-redline-tools/fpdf2 未采用或安装 |
| 安装报告 | actual install report 1 条 python-docx 1.2.0，file:// 源及 hash 与目标 wheel 一致；actual pip-inspect 的 69 名称/版本与当前静态环境一致；安装/check/inspect/verification 保存证据 hash 与正式 T09_actual_installation 一致 |
| promoted 证据 | 23 文件当前完整 bytes/SHA/size 与作者清单一致；不继承候选 freeze 结论 |

旧 68 核得的是版本保持；正式 53 包的实际文件由 3423 RECORD 校验进一步覆盖。未宣称额外开发工具所有安装字节也已与旧时点逐个比较。

## G08 / G04 与未知范围

G08 commit `e45454602b53e8e572b179ccf1c91093ec9f4ed7` 的 `docx/api.py`、`docx/document.py` 两个选取源码及完整 LICENSE，实际锁定 source = promoted source = wheel = installed。采用登记为 development runtime dependency；这不能证明整个 wheel 都来自该 commit、可复现构建、修订功能或文档视觉通过。

G04 commit `1dbc70ddfdf594fc4699c31b9077d15e74be56a0` 的锁定文件 bytes/SHA 通过；当前 adoption 声明 `incorporated_method`、dependency_review `not_applicable`，并记录独立 exact anchor 的 OOXML ins/del 方法。没有安装上游工具或 fpdf2，不因方法引用把上游整包纳入运行闭包。这里核对的是采用声明和未安装事实，业务 adapter 仍待功能审核，未声称已验证其实现。

lxml 7 个 PYD 仅静态字节核对；12 个 inline/header 资源逐个与实际 wheel、installed、正式 source 一致。11 组件声明的表达式 unknown、version/source_commit 未知及生产审批空值均保留，包括 iconv LGPL、libxml/libxslt 例外、CPython/ElementTree/ISO、未许可 XSL 声明；不折叠成顶层 BSD 已批准。LICENSES 所述 GPL test.py 不在该目标 wheel 内。本轮未执行 XSL/schematron/native。header 版本声明不能证明 PYD 链接的真实组件版本。

packages/build/source 的 approved_by/approved_at 都为 null，approved_scope 空，global approved_for_production false。实际源门禁 development exit 0、13 来源及 13 条非生产批准提示；release exit 1、9 项阻断：G04/G06/G08/G10/G13 生产批准，以及 G06/G08/G10/G13 依赖范围。release 不是 PASS。

## 历史与辅助错误

旧候选 96 freeze 的通过只代表原审阅时点；作者采用前刷新候选 verification checked_at 的历史已记录。本轮不执行候选 verify.py、不覆盖旧 freeze、不假称其当前 96 字节仍一致。实际安装以当前独立检查和作者实际 pip reports 核实。历史正常 pip 自动 pywin32 bootstrap 的作者说明保留，本独立审核不手动运行 hook。

初读猜测不存在的根 `requirements.txt`，PowerShell 在后续读取成功后整体 exit 0，但该子读取报错已实记，随后定位实际 requirements.lock。独立 audit 初次 exit 1，原结果/script 已保存为 `audit-first-adaptation-*`：审阅脚本误用 JSON 重序列化比较 CRLF 基线、未去除 lock extras、大小写 root 原始字符串比较、PEP508 单/双引号与空格原文比较，以及手列 tags 漏 cp311/旧 CPython abi3。实际旧51完整对象、wheel bytes、installed bytes、3423RECORD 已匹配；上述属于 reviewer 适配错误，不计业务/依赖功能 RED。改用原 git bytes、标准 canonical requirement/specifier 语义、installed interpreter 的 supported tags 后独立 exit 0 / findings 0。

曾发现正式新增两 package 仍有 candidate/NOT_INSTALLED 字段，作者仅更正新增两记录的 development_runtime_only/installed 状态并重核，独立读取已一致；旧51/build 保留。正式 requirements.lock 首行残留候选未安装标注已由作者改为 `T09 fixed G08 development runtime; INSTALLED; Windows CPython3.12.14`，同冻结最终独立审核 annotations 0。作者 PowerShell JSON 日期重序列化失配的辅助失败和恢复记录由作者保留，不冒充依赖 RED/GREEN。

## 命令证据

证据目录 `.audit-local/t09-dependency-review/`。所有纯检查只写审阅目录，不修改正式锁、candidate、环境、source、业务、status。

| 实际命令 | exit | 实际结果 |
|---|---:|---|
| Get-Content/rg 定位正式锁、作者 actual reports、候选说明与源门禁源码 | 0 | 初读 requirements.txt 不存在报错如上；正确定位 requirements.lock |
| `.venv/Scripts/python.exe -B -S -X utf8 .audit-local/t09-dependency-review/audit.py` 首次 | 1 | reviewer 适配问题保留；不是依赖功能缺陷 |
| 同命令，修正独立语义适配后 | 0 | 53/95/3423/78，旧51/build保持；findings 0 |
| `.venv/Scripts/python.exe -B -S -X utf8 scripts/verify_sources.py --mode development` | 0 | 13 来源、13 非生产批准提示 |
| 同脚本 `--mode release` | 1 | 实际 9 阻断 |
| `.venv/Scripts/python.exe -B -S -X utf8 .audit-local/t09-dependency-review/capture-final.py` | 0 | 同作者冻结后独立 audit exit0/findings0/annotations0；development exit0/13+13；release exit1/9。完整各子命令/退出码、stdout/stderr已保存 |
| `.venv/Scripts/python.exe -B -S -X utf8 .audit-local/t09-dependency-review/seal.py --author-seal .audit-local/t09-author-dependencies/freeze.json` | 0 | 3823/3823 读取来源、36/36 作者文件 SHA/bytes 匹配，drift/errors0，19 审阅自产证据封 SHA |

作者 `.audit-local/t09-author-dependencies/freeze.json` 为 T09_DEPENDENCY_FINAL_FREEZE，36 文件，清单 SHA `26e691e5fea6cec5d264e5f6f7e9a092854d4a5fb4eb2d52342dabf2147b39ba`，已逐项 36/36 核对。最终完整 argv、cwd、stdout/stderr、exit 在 commands-final.json；最终独立 audit-result.json 记录 3823 唯一读取来源，seal.py 已只读复核 3823/3823 无漂移，seal.json 保存本审阅自产证据清单。报告加入实际封存结果后重封自产 SHA，不改作者冻结文件或来源。此文档只记录静态依赖审阅，不称 T09 业务、法律、native/字体许可或生产完成。
