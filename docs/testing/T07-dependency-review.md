# T07 依赖独立审核

2026-10-03，workspace=`D:\Documents\ChatGPT\律所项目`。仅本文件及`.audit-local/t07-dependency-review/`可写；唯一业务作者负责正式合并与安装。审核者不安装、不修改锁/源码/业务/status、不提交、不联网、不运行SDK或原生/postinstall/startup钩子。root统一Obsidian及状态。

当前阶段：**DEPENDENCY_BYTES_AND_INSTALLED_METADATA_REVIEWED**，当前审核findings=0。正式依赖字节与实际安装元数据一致，不等于生产批准、协议握手、法律样本或T07业务验收。

## 实际独立方法与命令

采用`verification-before-completion`的实际证据边界；未引用作者“已通过”代替复测。独立脚本`.audit-local/t07-dependency-review/review.py`从固定workspace读取已缓存wheel、manifest、METADATA、逐版本PyPI JSON、许可文件与G13选取源码，重算bytes/hash；只写本审核目录。

命令：`.venv/Scripts/python.exe -B -S -X utf8 .audit-local/t07-dependency-review/review.py candidate`，实际两次运行exit=0（第二次补各base/test根的依赖采用范围固定点检查）。`-S`跳过site和`.pth`处理，`-B`不写pyc，仅将项目已安装site-packages加入path读取pure packaging；没有SDK/native模块导入。Read/AST/metadata操作不计业务测试。

| 项目 | 独立实测 |
|---|---|
|候选包与实字节|51目标wheel，38,081,132 bytes；每个filename/version/platform tags/size/SHA与METADATA、PyPI缓存一致|
|冻结基线|T03 35包version/filename/SHA/byte size全部保留；新增16包|
|许可|92份完整许可证据逐wheel member与本地缓存bytes/hash核对；继承35包正式许可路径被实际读取|
|依赖图|METADATA和PyPI Requires-Dist经PEP508语义比较，固定点传播pwdlib[argon2]/pyjwt[crypto]；Windows CPython3.12.14的76active边、排除marker、版本约束、全51可达、各base/test采用范围一致|
|锁|candidate.lock 51条精确version/hash与manifest一致|
|SDK源码|mcp2.2.0实际wheel内client/__init__.py、session.py、streamable_http.py与G13固定3源码逐字节一致；G13 LICENSE也与wheel相同|
|pywin32|15许可证据、8组件保留审批null；2份LGPL2.1全文证据，不能把legacy PSF当全wheel统一许可；55 DLL/PYD、4startup/postinstall相关文件仅归档读取|
|批准|51包及pywin32组件approved_by/at=null、approved_scope=[]；总approved_for_production=false|
|本审核发现|候选及正式依赖/实装均0；不涉及SDK业务验收|

候选manifest SHA256=`70aef6563387216cfc5fab1a0db4de37737e6a40109ab8643277ca7b4c5bcbc8`，candidate.lock=`fae7beb1a672e9ced6e1752c9b27a54a509dad112b8a0f60277f04b8af817eab`。机器证据为candidate-result.json、candidate-wheel-inventory.json、candidate-notice-inventory.json、candidate-active-edges.json；每个许可证据完整路径/hash保存在inventory。

## 审核边界与剩余阻断

pywin32.pth会导入pywin32_bootstrap，bootstrap增加DLL搜索目录。审核没有执行它，也没有单独运行两份postinstall脚本或导入55个native文件。作者安装后的普通Python启动已实际观察automatic bootstrap=true，manual postinstall=false；正式manifest native_execution_scope及新说明准确保留此区别。旧native_member_evidence.executed=false属于候选历史静态证据，不能解释为当前startup从未执行；整个原生构建及每个DLL运行安全未认证。

选取SDK文件匹配不证明整个wheel对应源提交、可复现构建或协议兼容。mcp使用httpx2，不能混用既有httpx对象；streamable transport两元tuple及snake_case只能静态确认。真实MCP/QCC endpoint、schema、价格、账户、数据政策、模型及握手仍未经审核者执行。

原许可证据中unknown表达式、pywin32 LGPL具体grant/only-or-later/源码与使用分发义务、既有PDFium/Pillow/OpenSSL/setuptools等bundled组件阻断继续保留。每个包development/base/test/build采用范围是技术分组，approved_scope空仍表示生产未批准；任何本地hash、安装/源码读取状态不可替代真实批准。

候选说明保留首轮又下载旧35wheel、初始人工52/17估计及两次Requires-Dist原字符串辅助核验失败；本审核采用实际51/16及独立语义解析，不将这些偏差改写为业务RED或隐藏。

## 正式安装独立复核（实际执行）

|审核者实际命令|exit|结果|
|---|---:|---|
|`.venv/Scripts/python.exe -B -S -X utf8 .audit-local/t07-dependency-review/review.py formal`|0|正式51wheel/38,081,132 bytes、92完整许可路径/hash、76marker边/base-test范围、35冻结、批准null与G13源码/许可一致，findings=0|
|`.venv/Scripts/python.exe -B -S -X utf8 .audit-local/t07-dependency-review/installed.py`|0|当前68个明确project-site分发、旧53版本保留、新15且click8.5既有；51实际METADATA bytes/hash、92安装许可、3,120个有hash的RECORD文件、SDK3+LICENSE一致，findings=0|

正式manifest SHA256=`8acdae77590e638f3ea5e8c2aa8515a5d0a0d491782729fafff3fdfb0375cf9e`，requirements.lock=`50c19c2701a9609ed9afddcd3bf73c1a631df25711b2150f6255155d59de618a`。新16 METADATA与16registry已实际读取`sources/evidence/runtime/<package-version>/`；新32notices实际读取正式sources路径，与wheel原字节匹配。build setuptools84.0.0保持同一完整记录、1wheel/17许可逐字节hash实核，不纳入51分母。

独立读取作者实际post-editable-inspect.json并与明确`.venv/Lib/site-packages`逐分发metadata比较，不以-S下的base环境凑数；68包括51闭包、build和既有开发工具/本项目editable/pip。额外17分发名单在installed-result.json，未把Scrapling等混进应用锁。当前实际Windows/Python marker environment与pip inspect及manifest一致，51的真实Requires-Dist与wheel相同，76有效边/排除extra和各组采用范围由独立脚本重新求得。qx-contract-workbench实际Requires-Dist包含mcp==2.2.0。

独立核作者正式install report仅15新增、全部file://且archive SHA对应正式wheel；commands.jsonl中真实安装有--no-index/--require-hashes/--only-binary，exit0。早期formal-install.json实际install=[]且旧35noop不算51完成；首Windows Path转换断言exit1在正式说明中明确保留，不记业务RED。作者pip check实际exit0、原日志No broken requirements found；审核者未额外启动pip/site处理，只核原命令/完整原日志与实际新metadata。

6组正式安装/inspect/check/SDK/native证据原路径及hash独立复核保存formal-evidence-inventory.json；actual RECORD hash检查仅51声明文件且resolve限定本项目.venv，不扫描全机/私案。RECORD自身和生成pyc无hash条目不记入3,120，也不因此宣称全面源码构建可复现。

当前G13技术采用为runtime_dependency/included_in_runtime=true，实际固定commit与选取源码保持；所有生产审批仍null/空、总approved_for_production=false。开发采用范围与生产批准分开，不把安装、hash或G13源匹配升级为许可/账户/协议批准。SDK业务测试由唯一作者后续实际RED→实现→回归及独立业务审核负责。

机器证据：formal-result.json、formal-wheel-inventory.json、formal-notice-inventory.json、formal-active-edges.json、installed-result.json、installed-record-inventory.json、formal-evidence-inventory.json。review.py和installed.py全程-B/-S，审核者业务tests=0、SDK协议tests=0、SDKimports=0、native/hooks额外执行=0、网络/QCC/model calls=0、installs=0。依赖独立审核当前闭合，无剩余已知依赖字节/metadata缺口；生产/SDK协议安全状态仍阻断或待后续实际验收。
