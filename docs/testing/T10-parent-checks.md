# T10 父节点最终检查

实际本机Windows/Python3.12.14，仅独立虚构数据。源码冻结后运行全套；未重装依赖、未请求真实供应商或外部账户。最终完整命令`.venv/Scripts/python.exe -X utf8 -m pytest -q --tb=short --junitxml=docs/testing/T10-results.xml`退出0：709 passed，0 fail/error/skip/warning，203.00秒。JUnit实际计数独立读取，源码未新增根业务测试。

作者332目标及必要关联、独审80独立/41正式/195关联均实际exit0；这些执行分母可重叠，不相加称新的唯一全套数量。依赖22正式/42独立已实际通过、55wheel/97主许可/79边/3467安装RECORD和71环境已核验；后补9模板静态检查不算普通浏览器执行。独审已关闭的撤销patch重放P2、作者failed-run/rule-evidence重放RED→GREEN保留原记录。

|父实际命令/动作|退出码|实际结果|
|---|---:|---|
|上述pytest全套|0|709/203.00秒/0警告|
|`scripts/verify_defaults.py --file config/defaults.json`|0|默认hash与规格一致|
|`-m cn_contract.cli schema --check`|0|唯一ReviewRun当前schema一致|
|`-m pip check`|0|无破损依赖|
|`scripts/verify_sources.py --mode development`|0|13来源、13未生产批准警告|
|同来源门`--mode release`|1|9实际阻断，非生产成功|
|`scripts/verify_runtime_dependencies.py --mode development`|0|55运行包/build1、native_build_verified=false|
|同runtime门`--mode release`|1|59实际生产阻断|
|`-B -S -X utf8 .audit-local/t10_parent_final_checks.py`最终|0|四普通浏览器案/16实际下载/0QCC ledger/0正式批准/190作者输入前后无漂移|

父纯校验解释器用-S；runtime门显式PYTHONPATH指向本机固定site路径以读取纯packaging，不处理.pth或导入目标native包，不称native安全/源码构建复现。七检查逐条argv/UTC/log hash及实际JSON在`.audit-local/t10-parent-final/checks.json`。首轮漏该pure路径引起ModuleNotFoundError/辅助JSON解析失败、SQLite decision列的辅助oracle错误与PowerShell内联检查引号错误均留记，非应用失败测试；最终按真实服务schema修正只读核验，业务无改动。

作者封证190项SHA `3789b6ff3a4bb14358ae1022cc0d08bc99a2d168e4c5d651f2aadc4632ac5ddc`于父检查初终均重算相同。独审160封证SHA `6ecf0ed616bcd02d1583dfc06b7daa5dc49735cc4c3278007a0ad00eb0a8c417`，共有97作者输入一致。依赖封证/模板补证SHA见T10-dependency-review及忽略目录，原旧53完整对象与T09安装记录不覆盖。父新增的状态、报告和计划文档位于后续时点，不改写旧封证。

根浏览器实证见T10-browser。完整网络捕获NOT_RUN，仅DOM声明资源/应用console/QCC账本分别核验。原固定四DOCX/provenance与默认raw不变；schema工程文本的既有CRLF/LF与HEAD不同仅辅助raw比较失败，LF规范化与JSON一致，未修改schema。Git缓存的原证据/lock/固定fixture另做原字节核验，提交结果附后；不运行旧T09假定53包的stage脚本。

缓存核验`.venv/Scripts/python.exe -B -S -X utf8 .audit-local/t10_parent_stage.py`实际exit0：258份source/lock/虚构原件raw与index逐字节相同、129作者业务/测试/固定输入与封证hash相同、默认加五份固定fixture共6项与HEAD原字节一致、48路径待提交，私人运行目录staged0。普通工程文本允许Git已配置的CRLF/LF规范化，未以此改写原始证据。cache diff check排除原始sources的有意空白后exit0，raw源已另证，不清理上游原bytes。

本阶段已执行工程范围通过；法律规则/gold/真实账户与数据政策、正式签发正例和生产依旧阻断。T11当前预检84全NOT_RUN、40材料0的历史时点准确保留，下一阶段实际实现后分别更新。
