# T09 python-docx依赖候选（未安装、未集成）

2026-10-03，workspace=`D:\Documents\ChatGPT\律所项目`。仅本候选说明及`.audit-local/t09-dependencies/`变更；正式锁、sources、业务、status、env和build均未改，未提交。当前 **NOT_INSTALLED / NOT_INTEGRATED**；所有production审批null/空，候选字节核验和pip dry-run不等于T09测试、Word视觉、native安全、使用/分发许可批准或生产完成。

## 固定来源与本地先查

根为G08已读`python-docx==1.2.0`，commit `e45454602b53e8e572b179ccf1c91093ec9f4ed7`，不追latest。实际查项目及已知bundled解释器的dist-info和两份选取源码，不导入docx/lxml、不把host site-packages放入项目sys.path。项目当前68分发有lxml6.1.3、没有python-docx；host有python-docx1.2.0/lxml6.1.1，仅作只读发现，不当项目运行依赖或目标wheel证据。

本项目`.audit-local/scrapling-wheelhouse/lxml-6.1.3-cp312-cp312-win_amd64.whl`已存在；实际复用其4,005,999 bytes并对官方逐版本registry的SHA校验。Python-docx缺目标wheel，仅取得[官方1.2.0逐版本metadata](https://pypi.org/pypi/python-docx/1.2.0/json)、[lxml6.1.3逐版本metadata](https://pypi.org/pypi/lxml/6.1.3/json)和固定python-docx wheel，共3个公开HTTPS GET，wheel实际下载252,987 bytes。没有旧51重下、真实材料/账户/费用/协议、真实模型、Word/COM/native导入或启动；URL/bytes/hash/UTC在network-evidence.json。

## 实际候选闭包

**53包=已实装T07冻结51+python-docx1.2.0+lxml6.1.3**。后两者是正式应用锁的新增2包；lxml已在项目开发环境，不能误称实际新增安装2包。本轮安装0，后续若正式采用，作者须以实际安装report记录新增量。保留全部51版本/目标wheel/hash/bytes，独立build setuptools84.0.0及1wheel/17许可原样。当前68项目分发/版本和5正式文件SHA前后完全一致。

|新增候选|版本/目标|实测wheel SHA256|bytes|METADATA License-Expression|
|---|---|---|---:|---|
|python-docx|1.2.0，py3-none-any|3fd478f3250fbbbfd3b94fe1e985955737c145627498896a8a6bf81f4baf66c7|252,987|unknown；legacy MIT，实际完整LICENSE匹配G08|
|lxml|6.1.3，cp312-cp312-win_amd64|3e9a00d1c2c30936f7add097c41afc5da6556c580909104aafd382cac92a855c|4,005,999|unknown；legacy BSD-3-Clause，另有组件例外声明|

全53目标wheel实测42,340,118 bytes；95份主许可/NOTICE文件=继承92+新增3，每份完整保存并与wheel member逐byte/hash核对；另有12个lxml inline资源/header完整成员证据、11组件声明。数量不能解读为每个bundled组件的源提交/完整grant/分发义务均已核验。

PEP508语义复核METADATA与PyPI Requires-Dist、Requires-Python、Windows/Pythonwheel tag/non-yanked及版本约束；固定点传播原pwdlib[argon2]/pyjwt[crypto]，有效边78。python-docx仅增加`lxml>=3.1.0`和`typing_extensions>=4.9.0`两边，冻结typing-extensions4.16.0符合；lxml四个cssselect/html5/htmlsoup/html-clean extra均未启用，不把开发Scrapling extras或host库偷纳闭包。PyPI本次vulnerabilities=[]仅表示该接口无列示，不是漏洞/供应链全面评估。

G08的docx/api.py、docx/document.py及LICENSE与固定目标wheel逐字节相同；g08-source-audit.json记录2源码/1许可实测hash。只证明选取文件，没有证明整个wheel源提交/可复现构建，也没有docx import/生成报告/修订/渲染结果。

## lxml原生及内嵌许可范围

实际wheel有7个PYD、0独立DLL、0.pth/postinstall；仅ZIP byte/hash读取，未加载。LICENSE.txt为完整BSD3条款；LICENSES.txt另外声明ElementTree/cElementTree、CPython xml.etree/difflib PSF、ISO RNG/skeleton XSL、source test.py GPL及binary zlib/iconv/libxml2/libxslt/libexslt，不能将整个wheel折叠BSD。

|组件/资源|实际证据与仍未核实|
|---|---|
|libxml2/libxslt/libexslt|LICENSES.txt含完整MIT grant及版权例外；实际header成员已保存，libxml xmlversion.h声明2.11.9、libxslt xsltconfig.h声明1.1.45，但header不能证明PYD实际链接版本。真实源提交、构建/静态链接对应和使用/分发范围未知，component version/source_commit仍null、expression unknown、审批null。|
|iconv/zlib|LICENSES.txt声明iconv LGPL2.1、zlib-license并给链接；准确only-or-later grant、组件完整独立notice、版本/源码/链接构建和分发义务未核实。此记录不把声明链接当生产许可。|
|ElementTree/CPython|声明派生代码和PSF v2；完整原组件grant/精确版本源未另核验，unknown/未批准。|
|ISO/skeleton资源|9个完整rng/xsl/readme成员保存，包含inline版权/许可数据，绝不执行XSL或导入isoschematron；独立组件来源和运行/分发范围未批准。|
|RNG2Schtrn/XSD2Schtrn|LICENSES.txt明确描述为unlicensed；实际两文件完整保存，不用顶层BSD遮盖。未来最小XML/报告路径不得宣称这些资源已获准；相关runtime/分发决定须独立审阅。|
|GPL test.py|声明存在于LICENSES.txt，但目标wheel无test.py，不把它误记实际安装代码或采用GPL测试工具；仍保留原声明。|

component-audit.json与candidate manifest保存11组件独立声明、各approved_by/at=null、approved_scope=[]；12个完整嵌入成员路径/hash见该证据。未知项保持production blockers，不能以lxml原已开发安装、MIT主包、header字串或归档hash替代native供应链/许可批准。后续作者采用须限定真实所用docx/XML路径，安全解析/禁止任意网络/实体/XSL范围另做实际测试，不由本候选宣称通过。

## 实际命令、退出与数量

所有审核解释器用`.venv/Scripts/python.exe -B -S -X utf8`，跳过site/.pth、禁止pyc，pure packaging只从项目既有site-packages加载；host目录始终只作明确文件/metadata读取。下述没有安装或SDK/docx/native导入。

|实际命令|exit|实际结果|
|---|---:|---|
|Get-Content T09-preflight/pyproject与rg项目.audits wheel缓存、-S本地G08/metadata读取|0|G08固定源、项目lxml6.1.3、hostpython-docx1.2.0/lxml6.1.1；未借host运行|
|`… .audit-local/t09-dependencies/prepare_audit.py`|0|基线51/68/5正式SHA；53wheel/95主notice/78边；3官方公开GET，下载1wheel252,987 bytes，缓存lxml复用|
|主license及wheel成员静态读取|0|BSD主文+LICENSES内嵌例外、7PYD/无postinstall及9inline资源|
|`… .audit-local/t09-dependencies/components.py`|0|11组件声明、12嵌入完整成员、两header版本仅声明、GPLtest.py实际不在wheel|
|`… -c` pure pip run_module，`install --dry-run --ignore-installed --no-index --no-cache-dir --find-links .audit-local/t09-dependencies/wheelhouse --only-binary=:all: --require-hashes --report .audit-local/t09-dependencies/offline-pip-report.json -r .audit-local/t09-dependencies/candidate.lock`|0|实际53包离线hash dry-run，全部file://，网络0/安装0；完整argv在commands.jsonl|
|`… .audit-local/t09-dependencies/verify.py`|0|53实wheel/42,340,118bytes/95主notice/12inline/78边；source2/LICENSE1、build1/17、5正式SHA/68env不变，findings0|
|记录辅助命令初次inline Python|1|PowerShell嵌套双引号ParserError，在Python执行前拒绝，无写入/安装/网络；改为保存finalize.py再运行，不计业务RED|
|`… .audit-local/t09-dependencies/finalize.py`|0|记录原4条审核命令与该辅助失败、freeze所有实际owned文件hash并读回核对；不运行业务|

本轮辅助记录命令的1次shell解析失败如上保留，候选下载/依赖核验没有已观察偏差；不把unknown组件批准、NOT_RUN/预检当功能RED或掩盖成许可PASS。候选继承T07原偏差/生产阻断，不改写既有历史。命令日志没有冒造未知开始时刻；可用UTC证据来自实际network/verify文件。

机器候选：candidate.lock/candidate.manifest.json；actual基线baseline-state.json/baseline.manifest.json；registry/metadata/notices/wheelhouse/source/embedded-evidence/native-metadata；g08-source-audit.json/component-audit.json/local-metadata-discovery.json；offline-dryrun.log/offline-pip-report.json、verification.json/wheel-inventory.json/notice-inventory.json、commands.jsonl。所有缓存Git忽略。

## 交接限制

后续solewriter在T09实际任务范围决定开发采用、正式source/runtime锁和notice路径后，才执行首次项目离线hash安装与actual inspect/check/源码匹配；本候选始终未正式合并、**NOT_INSTALLED / NOT_INTEGRATED**。不能以本轮53dry-run为T09工程完成，不能以hostdocx库或XML检查为Word视觉验收。

业务tests=0、T09tests=0、Word/COM/renderer=0、docx/native imports=0、postinstall/startup额外执行=0、project installs=0、真实材料/模型/QCC请求=0、生产审批=0。公开依赖metadata/wheel GET仅上述3次，不写真实材料或敏感信息；root统一status/Obsidian和后续阶段实施。
