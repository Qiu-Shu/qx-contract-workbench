# T09 DOCX 开发依赖实际采用

2026-10-03，workspace `D:\Documents\ChatGPT\律所项目`。正式应用/测试锁53包=旧51包+python-docx1.2.0+lxml6.1.3；旧51的完整package记录、版本/wheel hash/bytes和独立build1/17保持原样。环境原68分发已有lxml6.1.3，实际离线hash安装只新增python-docx1.2.0一包；安装后69分发，原68版本全部不变。Jinja2/MarkupSafe未采用、未安装。

G08固定commit的docx/api.py、docx/document.py和完整LICENSE与实际安装和目标wheel逐byte相同。G04仅实际采用已读的OOXML ins/del构造方法并独立实现exact anchor适配；未安装上游工具、未执行模糊匹配或Latin1 PDF路径。两来源明确开发使用、生产批准仍空；不是整个wheel源提交/native可复现构建证明。

正式新增23份证据（metadata/registry、3主license、12inline/header等）以原始bytes保存；完整53闭包95主license/NOTICE、78有效依赖边保留。lxml11组件独立声明、7PYD和12资源/header只是历史静态证据，unknown及审批null不改写。iconv LGPL、zlib/libxml/libxslt/CPython/ElementTree/ISO和两声明unlicensed XSL不能折叠顶层BSD。业务仅安全解析与新DOCX/OOXML，不启用任意实体、网络、XSL或schematron资源；分发/native完整来源与生产使用仍阻断。

|实际命令/检查|exit|实际结果|
|---|---:|---|
|`python -B -S -X utf8 .audit-local/t09-dependencies/verify.py` 采用前|0|53wheel/95主许可/78边、旧51和build一致、当时68env/G08匹配；未安装/业务|
|`.audit-local/t09_merge_dependencies.py`|0|53正式锁、旧51完整records/build原样、promote23证据；G08 runtime与G04 incorporated_method登记，审批null|
|`.venv/Scripts/python.exe -X utf8 -m pip install --no-index --no-cache-dir --find-links .audit-local/t09-dependencies/wheelhouse --only-binary=:all: --require-hashes --report .audit-local/t09-author-dependencies/install-report.json -r requirements.lock`|0|actual新增1 python-docx、全部其他already satisfied，report1条file://正确hash，网络0|
|`pip check`|0|No broken requirements found，实际log保留|
|`pip install --no-index --no-deps --no-build-isolation -e .`|0|更新实际editable Requires-Dist python-docx固定版本；未装额外依赖|
|`pip inspect --local`|0|实际69分发，未用候选dry-run代安装|
|`python -B -S -X utf8 .audit-local/t09_verify_installed.py` 修正后|0|53安装METADATA、95安装/保留许可、3423实际RECORD带hash文件/G08源2/LICENSE1核对；旧68版本不变、build不变|
|`scripts/verify_sources.py --mode development`|0|13来源开发门通过、13条非生产批准提示|
|`scripts/verify_sources.py --mode release`|1|实际9阻断：G04/G06/G08/G10/G13生产批准，G06/G08/G10/G13依赖范围待批；不是生产PASS|

上述python/pip命令均使用本项目`.venv/Scripts/python.exe`；pure审核用-B -S跳过site/.pth，不借bundled或host库。实际正常pip解释器会执行既有pywin32自动bootstrap，不误称从未启动hook；未手动postinstall，未运行Word/COM/native测试。

辅助错误实记：读取Word/G04文件初次猜错目录，后来用rg定位真实plans/apply.py；安装审核首次没有规范化pdfminer.six为pdfminer-six产生KeyError，修正后又因METADATA read_text换行转换导致byte断言失败，改读实际文件bytes后通过。均非依赖缺失或业务RED，没有隐藏成业务成功。

独立复核指出new2 package仍带候选NOT_INSTALLED字段和正式lock首行历史标注，现窄改为实际installed/dev范围，候选原文件不改。一次PowerShell JSON序列化把日期转换格式，旧51全record断言拒绝；保留该bad snapshot，随后从immutable baseline和固定candidate恢复原51/build/history，并只以Python更新new2安装字段，实际53/95/3423/69再复核exit0。没有重装或用新审计掩盖辅助失配。

采用前复跑候选verify.py会刷新verification.json的checked_at（库存JSON字节保持），作者未先复制故造成旧候选96freeze的verification路径不再代表旧bytes；已通知父节点，不改旧seal、不伪还原。独立候选报告的96/96只表示其审核当时事实；candidate manifest原`cc1c2449…`和lock原`bf5ea9ec…`仍完整核验。新的正式实际安装/证据在`.audit-local/t09-author-dependencies/`独立封存，不继承候选PASS。

依赖阶段 BUSINESS_TEST_PENDING；随后业务RED/GREEN/Word视觉分别记T09作者、独立和父报告。本记录不证明报告/修订/中文glyph/法律验收/许可或生产批准。
