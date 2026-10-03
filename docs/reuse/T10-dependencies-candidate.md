# T10 Jinja2 / MarkupSafe依赖候选（未安装、未集成）

2026-10-03，workspace=`D:\Documents\ChatGPT\律所项目`；仅本说明和`.audit-local/t10-dependencies/`可写。依据spec默认Jinja2+少量原生JS及T10-preflight/detail，准备本地自有模板候选，不实施UI/API。正式基线仍 **51包/68实际环境分发**，T09的53包只是未合并候选。两个新库和本轮所有组合均 **NOT_INSTALLED / NOT_INTEGRATED**，production approved_by/at=null、approved_scope=[]、approved_for_production=false。

## 来源、实际版本和安全告警

先明确读取项目`.venv`和已知bundled Python的dist-info，二者均无Jinja2/MarkupSafe分发；项目.audits wheel缓存rg无命中（exit1为无匹配，不是业务RED）。host只读，不加host site-packages至项目sys.path，不借host库运行。当前51中的uvicorn/python-multipart/httpx2/MCP等wheel仅实际复制至候选本地cache再重hash，没有重下载或改版本。

从官方PyPI当前metadata的实际info.version选稳定release，再请求逐版本JSON确定；本次实际取得 [Jinja2 3.1.6](https://pypi.org/pypi/jinja2/3.1.6/json) 与 [MarkupSafe 3.0.4](https://pypi.org/pypi/markupsafe/3.0.4/json)，不依记忆猜最新版本。逐版本目标wheel与registry size/SHA/non-yanked/Requires-Python/tag一致；新2wheel共149,202 bytes。

旧[Jinja2 3.1.5 metadata](https://pypi.org/pypi/jinja2/3.1.5/json)实际列2条记录，aliases指向同一CVE-2025-27516/GHSA-cpwx-vrp4-4pq7，fixed_in=[3.1.6]，涉及不可信模板的attr sandbox绕过。因此不选3.1.5，也不把两条数据库记录说成两个独立漏洞。selected3.1.6/3.0.4的PyPI vulnerabilities=[]只表示该接口本次未列告警，不证明全面无漏洞、OS隔离或可运行任意用户模板；security-evidence.json完整保存原记录与来源hash。

|候选新包|固定目标|实测SHA256|bytes|Requires-Python / License-Expression|
|---|---|---|---:|---|
|Jinja2|3.1.6 py3-none-any|85ece4451f492d0c13c5dd7c13a64681a86afae63a5f347908daf103ce6d2f67|134,899|>=3.7；expression unknown，wheel完整LICENSE.txt实际为BSD3条款|
|MarkupSafe|3.0.4 cp312-cp312-win_amd64|11935df9bf455ed0c04eb87bcd720f02b1fe5e02128a9430f23aed6f93336fc7|14,303|>=3.9；明确BSD-3-Clause，完整LICENSE.txt已保存|

公开HTTPS共7GET：2当前registry discovery+2逐版本JSON+2目标wheel+1旧Jinja安全metadata；只公开独立依赖资料，URL/实际UTC/bytes/hash在network-evidence.json。没有私人资料/费用/账户/真实模型、SDK或QCC调用/第三方协议接受。

## 当前与未来组合必须区分

|机器候选|实际用途|目标包 / 实测wheel bytes|主完整notice文件 / active PEP508边|
|---|---|---|---|
|candidate.manifest.json / candidate.lock|当前正式51仅加模板库；未合并/未安装|53 / 38,230,334|94=92+2 / 77=76+1|
|prospective.manifest.json / prospective.lock|**prospective=true**，假定未来正式采用T09候选后再加模板库；当前不是实装55或实装53|55 / 42,489,320|97=95+2 / 79=78+1|

两份机器记录均actual_formal_package_count=51、actual环境68；prospective-source.json绑定T09 candidate精确SHA，不修改其冻结记录。T09新python-docx/lxml bytes只从已审缓存复用，不提前正式采用。完整95主notice/12inline/11组件的原T09许可限制继续保留，尤其iconv LGPL和未许可XSL；55组合不能消除此类生产阻断。

全部51冻结version/目标filename/bytes/hash、build setuptools84.0.0的1wheel/17许可不变。两组合METADATA与PyPI Requires-Dist经PEP508语义比较，固定点传播原argon2/crypto extra，Python3.12.14 WindowsAMD64 tag/marker/版本/完整可达一致。Jinja2仅新增MarkupSafe>=2.0一边；i18n/Babel extra未启用，无新前端框架/Node/CDN/遥测，也不重审或升级既有MCP/uvicorn依赖。

本次核验实际68环境版本、5正式文件SHA前后不变，并重算T09冻结96个owned文件hash全部匹配；formal51与T09candidate53都没有被本轮修改。候选包、安装字节、批准范围和UI功能是不同验收，不把未来合并数字写成当前环境数量。

## 原生及许可证据边界

Jinja2 wheel无PYD/DLL/安装钩子；MarkupSafe含1个 `_speedups.cp312-win_amd64.pyd`（11,776 bytes）、0独立bundled DLL、0.pth/postinstall，另有完整 `_speedups.c`（4,527 bytes）已静态保存hash。未导入Jinja2/MarkupSafe，也未加载native文件。

标准库静态读取PE import directory，machine=0x8664，仅查出python312.dll、KERNEL32.dll、VCRUNTIME140.dll、api-ms-win-crt-runtime-l1-1-0.dll名字；这不是实际DLL加载、目标wheel额外携带这些DLL、MS运行库再分发许可、源码commit或可复现native构建证明。当前原生build/平台runtime使用分发范围与完整供应链审核待后续实际决定，生产审批不自动补。`native_member_evidence`和static-api-evidence.json保留原字节、C source及该界限。

每个新包完整LICENSE与wheel逐字节匹配，其名义BSD许可不代表项目的生产使用/数据政策已批准；Jinja2无明确License-Expression仍记录unknown，不擅自用classifier替代字段。继承pywin32/PDFium/Pillow/OpenSSL/setuptools等未知/多组件许可门继续保留。

## T10真实使用约束（未实现、未测试）

实际AST读Jinja2/environment.py、utils.py、filters.py共3个wheel原文件；Environment的autoescape默认False，不能用“装了Jinja”推断XSS门已通过。后续作者须显式配置html/htm/xml和string/default autoescape、严格未定义字段、固定本项目自有模板目录；不能让合同/原文/上传数据成为template source、loader path或可调用对象。模板目录与案级授权投影来自服务器，不接受客户端approved/provider字段。

Markupsafe.Markup、`|safe`、自称`__html__`的对象可绕开escape，不能用于不可信原文/意见/文件名。HTML、属性、URL和JS JSON各要适合上下文的编码：Jinja的tojson docstring明确双引号HTML属性需另处理；CSS/事件属性/动态脚本不接受用户拼接。少量native JS使用textContent和安全JSON数据，禁止innerHTML灌原文。这些是未来明确测试边界，本轮没有生成模板、render、浏览器攻击测试或UI页。

候选只拟用于本地自有HTML模板autoescape。patched sandbox也不授权运行用户模板；TestClient/UI四案、跨案文件与列表权限、CSRF、current roles/批准、原文Unicode定位和长job锁仍由T10唯一作者实际RED→实现→回归/真实浏览器旅程验证。工程XML或本候选不代替Word/法律验收。

## 实际命令、退出与证据

审核均`.venv/Scripts/python.exe -B -S -X utf8`，跳过site/.pth并不写pyc，pure packaging/pip只取项目既有site-packages；host目录未塞sys.path。pip只dry-run/ignore-installed/no-index/no-cache-dir/only-binary/require-hashes，未执行安装、build/postinstall。

|实际操作|exit|实际数量/结果|
|---|---:|---|
|读T10detail/preflight/spec与rg缓存|1|Get-Content/规格命中成功；最后rg无Jinja/MarkupSafe缓存匹配返回1，保留无命中，不计业务RED|
|项目/已知host metadata只读发现|0|两处均无目标库，无host运行|
|prepare.py|0|上述7公开GET/149,202新wheel bytes；当前53/未来55分开，51/68/5正式SHA不变|
|resolve.py candidate|0|实际53 offline hash dry-run，全部file://，0install/network|
|resolve.py prospective|0|实际55 offline hash dry-run，明确prospective，全部file://，0install/network|
|make_verifier.py|0|只写本owned verifier，复用既有纯metadata方法，不改T09冻结代码|
|verify.py candidate / prospective 首轮各1次|0 / 0|53/55真实全bytes+94/97主notices+77/79边，旧51/build/68env/5formalSHA/T09hash不变，findings0|
|static_api.py|0|3AST来源、1PE目录/4DLL名字、C source静态，不导入目标库/不render|
|verify.py candidate / prospective 最后各1次|0 / 0|加入静态PE证据后最终manifest重新完整核验；两组findings0，T09全部96hash仍匹配|

rg exit1表示本轮缓存无匹配，不是依赖解析/功能失败；其他实际命令无已观察失败，不虚造RED/PASS。未知启动时间不编造，network/verify UTC是实际证据；最终owned freeze/readback及命令记录在缓存。

机器文件：baseline-state/baseline.manifest、candidate/prospective.lock与manifest、prospective-source、registry/metadata/wheelhouse/notices/native-metadata/static-source、security/network/static-api evidence、两组pip-report/dryrun.log/verification/wheel/notice inventory。每个完整路径/hash保存，不只保留截图或报告数量。后续solewriter正式采用时重新核范围、实际install report/inspect/check和平台license，再实现UI；本轮始终候选。

**实际执行0：** project install、T10/business tests、目标库/native import、server/browser/UI render、Word/COM/renderer、SDK/真实模型/QCC/私人数据请求、生产批准。root统一status/Obsidian；本代理完成冻结后待命，不启动新任务。
