# T09/T10 离线候选依赖独立核验

2026-10-03，workspace `D:\Documents\ChatGPT\律所项目`。状态 **OFFLINE_CANDIDATE_BYTES_VERIFIED**，独立于候选作者。未观察到候选字节、闭包、许可证据或冻结记录偏差；未知许可/native构建和审批仍是阻断，不能称许可全面通过或业务验收。

本轮没有网络、安装、目标库/native import、SDKserver、Word/COM、UI/render或业务测试；未改正式锁、源文件、环境或候选缓存。当前正式 **51包/环境68分发**；T09 53、T10当前53/未来55全部未正式合并/未安装，不能把prospective当实际安装数量。T08稳定API交接仍优先恢复预算审阅。

|独立实际范围|目标包|wheel总bytes|完整主license/notice|活跃PEP508边|结果|
|---|---:|---:|---:|---:|---|
|T09候选|53|42,340,118|95|78|本地字节/metadata/许可成员匹配|
|T10当前候选（正式51+模板2）|53|38,230,334|94|77|匹配；actual_formal_count仍51|
|T10 prospective（假定采用T09后）|55|42,489,320|97|79|匹配；prospective=true，准确绑定T09 manifest SHA|

三组旧51版本/filename/bytes/SHA全部保持不变；独立build仍1wheel/17完整许可。T09 freeze96与T10 freeze100逐文件bytes/SHA验证前后196/196匹配；正式5文件hash、实际68个项目dist-info metadata完全一致，lxml6.1.3开发环境已存在，python-docx/Jinja2/MarkupSafe均未安装。未重新检查全部旧T07 installed文件，也未导入它们。

独立校验器仅标准库ZIP/JSON/email/AST/struct与项目已有纯Python packaging（`-B -S`，跳过site/.pth，不写pyc）。对三组全部目标wheel重hash、缓存registry SHA/逐版本目标size/non-yanked、METADATA精确bytes及PEP508语义、Python/tag和版本约束复核；从roots进行extras固定点传播，重算完整可达及78/77/79边，不照抄作者计数。每份主许可从wheel member读取，与保存文件逐byte/hash相等。已有离线pip报告只读复核53/53/55项且全file URL；本轮不重跑pip或声称独立安装。

新增4包的RECORD与所有对应成员完整集合、长度和SHA逐项核验：python-docx123、lxml177、Jinja2 30、MarkupSafe10个含digest成员，共340；另外4份RECORD自文件无digest是wheel规范例外。没有执行wheel代码。

G08的固定commit仍`e45454602b53e8e572b179ccf1c91093ec9f4ed7`；独立重比docx/api.py、docx/document.py两份来源与完整LICENSE一份。只证明这三份字节，不证明整个wheel对应该commit或native可复现构建。python-docx/lxml/Jinja2的License-Expression空字段继续记录unknown；legacy MIT/BSD文字不自动填补批准。

lxml实际7PYD、0独立DLL/.pth，12个完整inline/header资源与11组件声明匹配。LICENSES含iconv LGPL及zlib/libxml/libxslt等多组件声明，并明确RNG2Schtrn/XSD2Schtrn未许可；目标wheel无声明中的GPL test.py。资源/header声明不证明PYD实际链接版本或完整源构建；组件来源、准确grant、使用/分发范围和native供应链未知均保留，所有approved_by/at为null、scope为空。未执行XML/XSL或原生库。

Jinja2 3.1.6的3份静态源来自真实wheel，AST证实Environment.autoescape默认False。T10需显式autoescape（含string/default）、可信自有模板目录及适当上下文编码；候选审计没有render/XSS验收，也不授权任意用户模板。缓存旧3.1.5两条advisory的aliases指向同一CVE-2025-27516、fixed_in3.1.6；选定版本缓存vulnerabilities空仅是该接口未列示，不是全面漏洞结论。

MarkupSafe实际1PYD、1完整C source，PE目录独立解析得到4个DLL名字，与证据匹配；这不是加载DLL或证明构建/Windows runtime分发许可。native审批均未补，未import Jinja/MarkupSafe，未浏览器或UI操作。继承旧包多组件与生产许可阻断亦不变。

实际主命令：`.venv/Scripts/python.exe -B -S -X utf8 .audit-local/t09-t10-candidate-review/verify.py`，修正后两次exit0，最终实际UTC `2026-10-03T06:29:09.381598+00:00`；上述数量及findings=[]来自独立执行的`verification.json`。完整命令/退出记录在`.audit-local/t09-t10-candidate-review/commands.json`。

辅助错误分别记录，不算依赖或业务RED：inline shape初次把native成员计数7当list（TypeError，exit1）；独立校验器初次猜错G08 LICENSE目录（FileNotFoundError，exit1，修正为实际third-party-notices路径）；额外读不存在T09 prospective-source文件导致只读命令exit1。没有以这些失败伪造功能RED，未编造未知启动时间。

最终机器证据及独立seal在`.audit-local/t09-t10-candidate-review/`。根节点仍独占正式采用、真实安装、状态/记忆记录和提交；native/许可/真实外查/Word视觉/业务/生产各自独立验收。
