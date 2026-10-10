# 任务实际状态

2026-10-10审计整改首批：QX01撤销待发布授权、QX02 DOCX颜色来源门与独立段落核对、QX03当前12样本备份恢复、QX04提交未知结果与返回前到期检查已实施；QX09仅去重测试和当前能力索引。1599项按清单分段执行并关闭失败：首轮1271通过后报告器中断，续跑327通过1旧来源断言失败，最终相关80通过；逐项唯一1599通过，不称单次全套成功。双轴独审3项已修复复验；浏览器新虚构库来源核对、12份逐份恢复及STDIO未知结果均实际验证。117源文件绑定通过；常驻工作台/插件未重启验收，QX05–QX08/QX09余项/QX10未完成，真实模型/QCC/真实材料产品准入/签发/生产边界不变。[本批实际证据](testing/AUDIT-QX01-04-20261010.md)；[当前能力](CURRENT_CAPABILITIES.md)。

2026-10-10独立审计回件核验：当前718c3fb未改业务；报告两项P1（待发布授权撤销失效、DOCX白字金额来源门缺口）及A03备份登记/A04未知提交语义已在本机虚构案复现。7探针7失败、0setup错误，含O01在途到期语义观察，均待修而非PASS；A05评分盲区/A06资源前置/A07重复测试亦核实。外部271现有回归仅读取与去重，不称本机重跑。原件已保全，源绑定116项未变；真实模型/QCC/材料产品准入/签发/生产仍受限。下一步优先QX01–QX04，保留现有架构和有效代码。[回件核验及整改顺序](audit/2026-10-10-audit-return.md)。

2026-10-09 OCR增量：仅在识别输入加入对比度增强，原PDF/预览/坐标/旧候选保持。48页输入逐页比对，32页字节相同未重识别，16变化页实际OCR全部字段命中，新增恢复29/32两页、退化0；综合历史观察37/48→39/48，并非全48重跑。倾斜第9页及8遮挡金额页仍缺项。有效RED2失败23通过→25通过，86关联及69入口通过；独审25+8通过，无阻断问题。原件/资产/worker五文件保全，116文件源绑定已更新。全套/浏览器/Word/峰值内存未重跑或未测，真实模型/QCC/材料产品准入/签发/生产保持关闭或阻断。[实际证据](testing/OCR-contrast-20261009.md)。

2026-10-09当前聊天接入验收：本地插件0.1.5已物化安装，当前Codex聊天4工具可调用；本轮8次原生调用为5成功、3预期拒绝，实际完成虚构选案→候选落库→相同输入重放→不同内容拒绝→撤销后读写拒绝。候选仅1条且先待律师处置；虚构测试角色处置后下载40,438字节工作稿，来源未核验标记保留。临时凭据目录已清除，服务exit0，原8766与真实材料未触碰。业务代码/依赖无变更，全套/48页OCR/Word未重跑。关闭下面历史记录的“父聊天仍旧两工具拒绝”缺口；网页ChatGPT、真实模型/QCC、真实材料产品准入及生产仍未完成或阻断。[实际证据](testing/PLUGIN-native-20261009.md)。

2026-10-09项目增量：新增单独明确授权的一轮插件候选提交，默认只读保持；来源local_plugin_unverified贯穿候选、律师处置和导出，模型身份/推理未核验，工作台真实模型/QCC为0。复用既有表与流程，无新增依赖。58目标、最终90入口/候选及浏览器1通过；大回归270通过1旧标签失败已精确复验修复；独审两P2及两个并发残余均有效RED→最终8通过，另13手工/原生红线旅程通过（重叠不相加）。源0.1.5/4工具/116文件绑定通过，父聊天仍旧2工具拒绝；网页ChatGPT、真实调用、签发、生产继续未完成或阻断，全套/48页OCR/Word未重跑。[实际记录](testing/PLUGIN-candidates-20261009.md)；[使用说明](LOCAL_WORKBENCH.md)。

2026-10-09项目增量：默认持久工作台新增明确同意后的15分钟选案只读连接，MCP源0.1.4增加无参read_selected_case；当前会话/角色/版本/原件/来源后端重验，重启/注销/撤权/恢复/到期失效，不新增数据库表。最终57目标、111较早关联、196MCP回归、71最终入口/模板均通过（重叠不相加）；独审两P2实际RED→修复14复验；真实TCP/STDIO及桌面/窄屏选择撤销已验，浏览器过早点选问题修复。116源文件绑定更新，依赖新增0。父旧聊天仍拒绝且未暴露第三工具，网页ChatGPT/候选自动写回/真实模型/QCC/签发/生产仍未完成或阻断；未重跑全套/48页OCR/Word。[使用说明](LOCAL_WORKBENCH.md)；[实际记录](testing/CASE-bridge-20261009.md)。

2026-10-09项目开发增量：修复聊天turn元数据被离线插件误拒绝，214关联通过，新增2整体容量边界及独审闭合；新加载独审会话原生两工具成功，父旧活动turn仍报原错，不能称父会话/网页ChatGPT已恢复。新增持久本机入口与双击启动：自设账户、重开保留案件/原件/会话，无公共默认密码；空库/缺表/换库先只读拒绝，OS锁覆盖实际worker寿命。最终19目标、39关联（含较早18）、独审41 assisted回归及两P2有效RED→修复复验。114文件源绑定已更新；未重跑全套/48页OCR/Word，真实材料/模型/QCC/签发/生产继续关闭或阻断。[启动说明](LOCAL_WORKBENCH.md)；[实际记录](testing/LOCAL-workbench-20261009.md)。

2026-10-09客户稿增量：读取范围的连续页号合并、已知扫描页/OCR旧状态改中文，未知诊断和原件SHA保留，内部稿原始清单及快照不变。有效RED6失败2通过→目标8通过；关联121通过（含8）、入口69通过，唯一独审0新增问题。虚构案件真实导出/下载及Word客户3页（旧4）+内部4页共7页复验通过；旧稿字节与下载不变。依赖检查通过，本轮新增安装0。全套/48页OCR未重跑，真实模型/QCC/法律验收/生产仍关闭或阻断。[实际记录](testing/CLIENT-readability-20261009.md)。

2026-10-09版式增量：上一轮实际下载的人工转录稿、OCR关联金额稿已用本机Word 16.0.20430只读渲染，各4页共8页逐页检查；无可见裁切/重叠/中文缺字/表格断裂，每页草案页眉页脚保留。两原DOCX字节未变；每份34正文段、38表格单元格在PDF完整保留。仅关闭这两份稿的Word视觉缺口，不扩大到所有模板或真实法律验收。业务代码/依赖未改，无新业务pytest或OCR批次。[实际记录](testing/OCR-word-layout-20261009.md)。

2026-10-09增量：保持原PDF与固定模型，提高预算内渲染倍率，修复清晰页漏字。规定字段命中20/48→37/48，清晰0/8→8/8，11页仍缺项/错误，第22页另有跨框多余字符；0异常不是全文质量通过。新增19渲染测试包含在61关联通过内，入口69与评分14通过；本轮未重跑全套1421。已实际完成浏览器原页→人工/实际OCR来源→事实确认→候选处置→下载DOCX→具体版本核对；旧稿后端409，新稿字节一致。Word版式/完整网络捕获未验。源绑定已更新，宿主缓存未改。详见 [本轮实际记录](testing/OCR-quality-20261009.md)。以下10月8日及更早记录保留为历史。

2026-10-08增量：本机PDF原页、真实离线CPU OCR与三类独立来源记录已实施；已完成目标/关联与实际OCR候选到工作稿路径，独审3项Important均有RED→GREEN。最终完整工程回归1421 passed，exit0，923.594秒；原生收集与JUnit逐项一致，0失败/0错误/0跳过；PDF渲染48页20对/28错/0异常、清晰0/8，质量门FAIL；独立无损首1页正确并完成API工作稿链，不能替代48页结果。浏览器新增界面受客户端限制，Word版式缺渲染器，均未验。真实远程模型/QCC/正式签发/生产仍关闭。最新证据见 [本轮记录](testing/OCR-proofreading-20261008.md)；下文2026-10-05的1346/0页为历史分母。

记录日期：2026-10-05，显示时区Asia/Shanghai；历史阶段记录保持原日期，证据时间使用UTC。原仓库为空，用户已确认继续本目录。开发分支`codex/contract-review-v2`。

|任务|工程状态|实际完成|阻断/下一步|
|---|---|---|---|
|T00|ENGINEERING_PASS；PRODUCTION_BLOCKED|现状表、附件成员哈希核对、13来源51目标文件、许可全文证据、复用记录、来源校验器及28个用例|G11许可未批准；G05npm来源链未闭合；实际纳入的G10传递依赖/浏览器许可及生产批准待定；下一任务T01|
|新增Scrapling安装|LOCAL_TOOL_VERIFIED|0.4.15+fetchers，Chromium，CSS/XPath/HTTP/动态JS4项通过；28个wheel独立重算hash|仅开发工具，未集成业务流程，未测试真实网站|
|T01|ENGINEERING_PASS；PRODUCTION_BLOCKED|83个领域/嵌套模型、精确类型与UTC、四角色、18维与四类型schema、默认hash和已安装CLI；全套158 passed，独立审阅缺陷全部修复|只是数据/工程入口；运行依赖与build使用范围/安全/源供应链未生产批准；下一任务T02|
|T02|ENGINEERING_PASS；PRODUCTION_BLOCKED|关系表/外键/事务、实际会话/角色/成员、CSRF、不可变原件/审计/快照、版本变化失效；42目标/200全套 passed|独立42目标及10组事务/缓存攻击复验通过；突然崩溃恢复/部署/正式认证与签发尚未完成|
|T03|ENGINEERING_PASS；PRODUCTION_BLOCKED|安全DOCX/PDF摄取、受限XML、部件/逐页盘点、精确版本锚点；69目标/269全套 passed；独立69目标+14攻击探针 passed|OCR/全面视觉等价/PDF解码进程沙箱未部署；G06运行采用已登记；G06/G10生产门禁仍阻断；下一任务T04|
|T04|ENGINEERING_PASS；PRODUCTION_BLOCKED|事实候选/原件信任核验、完整版本确认、Decimal AST/单位/真步长计算、主体明确选择；76目标/345全套 passed|独立76目标/31探针/181回归通过；来源污染P2闭合；模型/外部收据/正式签发仍未支持；下一任务T05|
|T05|ENGINEERING_PASS；BLOCKED_RULE_APPROVAL / PRODUCTION_BLOCKED|14草案/9pending法源索引、来源证据/负责人批准门、时际/例外/版本冲突与客户政策隔离；86目标/431全套passed|独立86目标/45探针/124核心回归通过；实际法源及律师规则批准缺失，草案不能参与法律结论；下一任务T06|
|T06|ENGINEERING_PASS；BLOCKED_RULE_APPROVAL / PRODUCTION_BLOCKED|80目标/511全套；独立77攻击探针；四份实际虚构DOCX CLI各18维、9JSON/SQLite、QCC0|规则未现实批准；mock不能正式签发；Word/PDF待T09；下一任务T07|
|T07|ENGINEERING_PASS；BLOCKED_LIVE / PRODUCTION_BLOCKED|固定SDK实际本机MCP握手/发现/调用、批准绑定/实时漂移、安全raw；46目标/557全套、独立66攻击/17授权通过|51正式包/92许可/76边实际核对；账户/官方schema/真实价格/许可缺失，真实外发0；下一任务T08|
|T08|ENGINEERING_PASS；BLOCKED_LIVE / PRODUCTION_BLOCKED|持久预留/发送标记/短事务Factory、原子预算/幂等/未知恢复/账单对账；52目标/609全套、独立58探针/78关联回归通过|真实账户/价格/许可/律师批准缺失；未知扣费不自动重试；下一任务T09|
|T09|ENGINEERING_PASS；BLOCKED_LIVE / PRODUCTION_BLOCKED|37目标/646全套、独立61探针/136关联回归；三类新报告/内部精确原生修订；Word六轮十页与接受拒绝全文实际通过|复杂及对外原件包修改人工；QCC报告消费者/全合同补丁后语义重审未实现；真实批准与许可缺失；下一T10|
|T10|ENGINEERING_PASS（已执行范围）；PRODUCTION_BLOCKED|六类中文页面/14端点/持久任务；37 API+4 API旅程+22依赖门，全套709/0警告；独立80+41+195；根普通浏览器四类/各18维、五种处置、16实际下载、四次mock拒签；55包/环境71保留旧53证据|完整浏览器网络捕获NOT_RUN，声明资源均本地/应用console0/QCC账本0另证；source发布9/runtime发布59阻断；法律gold、真实外查、正式签发正例和生产仍阻断|
|T11|ENGINEERING_PASS（评测机制）；LEGAL_BENCHMARK_BLOCKED / PRODUCTION_BLOCKED|37目标、独立64+37及316参数；根全套746/0警告；真实CLI84能力5PASS/36NOT_RUN/16NOT_IMPLEMENTED/7NOT_SUPPORTED/20BLOCKED，58guard单列；40独立虚构材料实际审查39工程PASS/1NOT_SUPPORTED，16家族/24dev16预留blind；最终644输入零漂移|发现的材料/执行证据/硬门缺陷均真实RED修复且同探针闭合；84项没有全部通过，两律师gold缺失、法律指标null；CLI真实exit1/BLOCKED；下一任务T12|
|T12|ENGINEERING_PASS（已执行范围）；PRODUCTION_BLOCKED|44正式目标、两独审68与54；根全套790/0警告；根新目录4类原件+5草案制品/2原生XML、38表/未知15剩5且0重发；623输入封证/314原始bytes不变|development发布75阻断/production实际exit1；国内host/HTTPS/OS隔离/真实key custody与数据政策NOT_RUN/未批准，当前全部法律能力/gold仍阻断；下一T13|
|T13|ENGINEERING_PASS（守卫与受限交付）；BLOCKED_LIVE / PRODUCTION_BLOCKED|25正式目标、31费用恢复关联；两独审29与43；T13根815全套/0警告；T13阶段84能力5PASS/58guard单列、40虚构材料实际审查；qcc-smoke真实CLI拒绝、开发发布75阻断/生产exit1|真实联调与影子NOT_RUN；账户/许可/现实批准信任根/完整法律硬失败登记/金标准/模型数据政策/国内环境缺失；真实供应商及真实资料外传0，没有上线批准|
|DeepSeek接续|ENGINEERING_PASS（首批纯离线）；REAL_CALLS_DISABLED|用户2026-10-03实际“确认”有限设计；请求/响应/token/币种纯codec、唯一domain三DTO；121正式目标/308关联、两独审138与25；根936全套/0警告/exit0，native collection=JUnit；四份虚构DOCX的12组人工离线示例、666输入前后零漂移/314原始bytes不变|不配置密钥、不发真实请求、不放开mock注册门；response固定OFFLINE_ONLY/protocol_only，未知费用None或显式合成估价；真实transport/费用ledger/价格/数据/批准仍缺失或阻断|
|ChatGPT插件目标|TARGET_CONFIRMED；LOCAL_HOST_DISCOVERY_VERIFIED|用户明确最终交付为ChatGPT插件；现服务复用方案保留，两工具可直接SDK调用，本机Codex适配包已安装/发现|宿主聊天实际调用/模型选择NOT_RUN；真实案件MCP/身份与文件桥/网页ChatGPT连接仍未实现或阻断；不建账户、付费托管、隧道或发布|
|首批本机离线MCP|ENGINEERING_PASS（受控两工具）；HOST_NOT_RUN / PRODUCTION_BLOCKED|用户在具体设计及状态说明后“继续”；新STDIO两工具、domain新增3DTO；80目标/348关联，两独审144与92，父SDK24成功+4拒绝、全套1016/0警告/native=JUnit；协议前置反射及目录/祖先link实际RED修复闭合|仅当前仓库固定虚构示例，不是法律审查；不打包安装插件、不连ChatGPT；帧/OS硬限未建立，真实模型/QCC/gold/许可及生产继续阻断|
|本机插件连接源包|HISTORICAL_PACKAGE_VERIFIED；PORTABLE_HOST_REJECTED / PRODUCTION_BLOCKED|历史七文件通用/兼容清单及图标/90绑定hash，ZIP10399bytes；解压两配置4状态/48示例/12拒绝；80目标回归native=JUnit，独立18结构/75边界检查及38请求自然退出0；该阶段业务源码不变|后续实际宿主拒绝portable绝对入口；原源包及ZIP保留历史，入口旧绑定hash过时；不把结构/SDK验收称宿主解析通过，当前适配见下一行|
|本机Codex安装与发现|LOCAL_HOST_INSTALLED；DISCOVERY_VERIFIED；CHAT_INVOCATION_NOT_RUN / PRODUCTION_BLOCKED|五文件Legacy适配0.1.1，项目目录/启用配置及宿主缓存；原包禁用，全局配置不变；元数据4真实RED后84目标/全套1020零警告，独审113边界/32格式；实际native恰两工具、SDK24示例2状态12拒绝、新90绑定匹配|独立host无已加载线程、活动proxy socket连接失败，聊天调用/模型选择NOT_RUN；不新建/resume线程或启动模型turn。网页连接、真实模型/QCC/案件身份与文件桥/法律gold/OS硬限/生产仍阻断|
|本机调用元数据兼容|WIRE_ENGINEERING_PASS；SOURCE_0.1.2_READY；CHAT_INVOCATION_NOT_RUN / PRODUCTION_BLOCKED|仅entry核验tools/call的惰性canonical UUID threadId，可与旧整数token共存；真实wire先4失败6通过，94目标/根1030零警告；独审246边界/242请求、24保全、7 native复核；90绑定匹配，源0.1.2/read与独立host缓存0.1.1/两工具发现分别实证|新cache0.1.2 NOT_MATERIALIZED；本聊天loaded root未验证，用户看到插件/刷新入口但完成未确认，工具inventory仍无目标两工具；原生chat call/模型选择/ChatGPT连接NOT_RUN。trace元数据仍拒绝，真实模型/QCC和生产仍阻断|

2026-10-05首轮 CR-01 律师辅助工作稿已完成有限工程验收，见 [父实际记录](testing/ASSISTED-parent.md)、[范围及逐项状态](ASSISTED_SCOPE.md)、[ADR0006](adr/0006-assisted-review-scope.md) 和 [数据流](ASSISTED_DATA_FLOW.md)。完整工程1346项通过、0失败/错误/跳过/警告，原生清单与JUnit逐项匹配；12份新虚构材料实际API旅程、客户DOCX下载/旧成果失效/模拟拒签已执行，具体工作稿确认另经目标19/独审及新目录实际浏览器。C1/B1/F13/有界progressToken/A2/源入口及发现的维度映射缺口均分别保留RED/目标/关联/独审证据。源适配0.1.3最终v2绑定100文件/57版本，实际守卫与SDK/独立STDIO通过；Git字节保留核对102对象通过。当前宿主缓存/聊天及ChatGPT案件/身份/文件桥仍NOT_RUN或未实现。OCR/viewer仅预检，48页0/48未跑；法源、完整修改再审、真实模型/QCC、法律gold与生产继续未落实或阻断。原84/40/Word/浏览器历史分母保持，不用1346工程项替代。

上一阶段记录：[调用兼容与当时接入状态](testing/PLUGIN-chat-call-compat.md)，94目标/完整1030实际通过，受限threadId仅call边界核验，当时源0.1.2与独立宿主选择的旧缓存0.1.1分别记录；本聊天已加载根未验证；聊天调用、网页连接和新缓存验收未完成，开发源门通过、release来源9和环境59阻断。完整pytest不替代原84能力/40材料/Word/浏览器的独立阶段验收。历史[本机安装与协议验收](testing/PLUGIN-local-host.md)保留84目标/完整1020及当时安装/发现通过范围；[插件源包验收](testing/PLUGIN-local-package.md)保留80目标及HOST_NOT_RUN，其18结构检查未证明portable解析。[本机离线MCP父验收](testing/MCP-offline-parent.md)、[作者初版](testing/MCP-offline-author.md)、[实际修复](testing/MCP-offline-author-repair.md)保留全套1016与独审范围；[只读预检](testing/MCP-offline-preflight.md)保留当时未实施范围。此前[DeepSeek首批离线](testing/DEEPSEEK-offline.md)、[根936回归与实际材料](testing/DEEPSEEK-parent-checks.md)、[独立协议138项](testing/DEEPSEEK-offline-review.md)及[边界25项](testing/DEEPSEEK-boundary-review.md)继续保留。T13[815/84与证据核验](testing/T13-parent-checks.md)、[调用29项](testing/T13-live-review-final.md)与[上线43项](testing/T13-readiness-actual-review.md)为历史；当前[LIVE_READINESS](LIVE_READINESS.md)、[SHADOW_RUN_REPORT](SHADOW_RUN_REPORT.md)、[GO_NO_GO](GO_NO_GO.md)未解除。T13历史84项仍5PASS/36NOT_RUN/16NOT_IMPLEMENTED/7NOT_SUPPORTED/20BLOCKED；工程回归不等于84完整能力、双律师验收或生产完成。全部初始失败与最终复验保留。

## T00实际执行

|命令|退出码|实际结果|
|---|---|---|
|`git status --short --branch` 初始|0|No commits yet on master，业务文件0|
|`rg --files` 初始|1|没有可列出业务文件，非应用测试失败|
|`python .audit-local/reference_inspect.py inventory/consistency`|0|附件两个zip共6文件哈希匹配；配置哈希匹配；84唯一规格编号|
|公开来源审计及hash重算|0|13来源、51选取目标，51 hash匹配；未取得任何production批准|
|`.venv/Scripts/python.exe -m pytest tests/unit/test_sources.py -q` RED|1|12 failed，实现缺失的明确断言|
|同目标补强RED|1|3 failed/12 passed：指纹证据与运行标记行为缺失|
|审阅修复RED|1|11 failed/15 passed：等价路径、虚假批准、类型、许可文件及改名复制等|
|`.venv/Scripts/python.exe -m pytest tests/unit/test_sources.py -q --tb=short` GREEN|0|26 passed，0 failed|
|G11畸形文件记录RED→GREEN|1→0|先2 failed/26 passed，再28 passed，非字典文件记录返回FILES_INVALID而非崩溃|
|`.venv/Scripts/python.exe -m pytest -q --tb=short` 全套最终|0|28 passed；当前只有T00用例，不代表后续任务验收|
|`python scripts/verify_sources.py --mode development`|0|checked_sources=13，errors=[]；13条NOT_PRODUCTION_APPROVED警告|
|`python scripts/verify_sources.py --mode release`|1|真实锁返回DEPENDENCY_REVIEW_PENDING:G10、PRODUCTION_APPROVAL_MISSING:G10，符合预期门禁|
|`.venv/Scripts/python.exe -m pip check`|0|No broken requirements found|
|`python scripts/scrapling_smoke.py --output .audit-local/scrapling-smoke-parent.json`|0|父独立复跑4/4通过，2次本地/sample请求，QCC0|
|28个实际wheel独立SHA-256重算|0|28/28与审计hash一致|
|`pip install --dry-run --ignore-installed --require-hashes --no-index --find-links .audit-local/scrapling-wheelhouse -r requirements-scrapling-windows-py312.lock`|0|本地wheel解析28项安装计划；哈希锁可被pip接受；非完整重装或生产恢复演练|
|Git索引blob独立hash检查|0|51个来源目标+指纹文件，共52/52匹配；`.gitattributes`禁止证据换行转换，保持原始字节|

完整T00失败过程与范围见`docs/testing/T00.md`。安装原始日志、本地HTML运行证据和wheel缓存在被Git忽略的`.audit-local`，可提交的版本与hash记录在`requirements-scrapling-windows-py312.lock`及`sources/scrapling-wheel-hashes.json`。未上传真实材料、注册付费账户或调用企查查。

## 决策与未支持项

- 用户明确确认空仓库；采用新仓库默认架构，原地分支工作；无现有可用代码可替换。没有重建Git历史。
- 用户新增Scrapling安装要求覆盖规格对G10暂缓安装的默认建议；只安装为开发工具，未自动启用法源批量抓取、QCC或真实资料处理。
- source锁的read_verified表示选取文件与许可证据可读，不能替代依赖、实际效果或律师批准。G11根CC许可不能替代目标AGPL，GNU通用许可全文也不能替代授权。
- 许可指纹只能防已知完整副本和已登记片段进入常见运行目录；不能认定任意改写、短片段或未知来源已获许可。未来新增运行目录必须纳入扫描。
- T01的Pydantic类型校验不能替代实际权限、来源批准、费用或签发；标准JSON往返保持事实Decimal/日期类型。全部默认参数来自同一JSON，并生成实测配置hash。
- 未实现：真实模型与获批法律规则审查、OCR、QCC收据报告消费者与真实联调、补丁后全合同法律/数值语义重审、法律样本测评和生产部署。T06四类虚构/mock闭环、T07固定SDK本机模拟、T08模拟预算网关、T09受限草案/原生修订及T10 API/本机中文UI已实现；工程通过不等于真实能力或法律验收。

## T01实际执行

|命令/验证|退出码|实际结果|
|---|---:|---|
|领域/配置/CLI首次RED|1|领域56 failed；配置/CLI14 failed，功能缺失断言|
|独立审阅修正RED→GREEN|1→0|修复--file被忽略、非规范角色、事实JSON丢类型/单位、ModelRequest别名往返；逐轮失败与通过记录在T01-domain/config/review|
|`python -m pytest -q --tb=short --junitxml=docs/testing/T01-results.xml`|0|158 passed；111领域、19配置/CLI、28来源门|
|`python -m cn_contract.cli schema`及`schema --check`|0/0|保存schema来自唯一ReviewRun模型，实际核对一致|
|`scripts/verify_defaults.py --file config/defaults.json`|0|hash与v2.0完全一致|
|可编辑安装、控制台help/config、pip check|0|实际安装qx-contract-workbench0.1.0，console及模块入口可用|
|两个锁本地wheelhouse dry-run hash验证|0/0|应用/测试11包与build1包分别可解析；没有称完整重装|
|独立定向审阅|0|50 passed/61 deselected；4规范角色、7类值/Decision16次往返、Decimal单位、alias、schema修正均核对|

运行依赖的12个wheel、32份许可/NOTICE已保留证据，全部development/read_verified；这不构成生产批准。83个模型能生成schema不等于83项业务功能已实现。详细记录见`docs/testing/T01-domain.md`、`T01-config.md`、`T01-review.md`及`docs/reuse/RUNTIME-dependencies.md`。

## T02实际执行

已按本地hash锁安装SQLAlchemy2.0.54、FastAPI0.142.2、pwdlib0.3.1/Argon2及完整28包闭包；安装退出0，pip check退出0，重新editable安装退出0。测试工具升级pytest9.0.3后，T00/T01的原158项独立复跑退出0；记录旧8.4.2公开告警，保留原阶段历史分母。父节点本地wheelhouse ignore-installed hash dry-run实际28包退出0，详见`docs/reuse/T02-dependencies.md`。

T02最终父节点实际`pytest -q --tb=short --junitxml=docs/testing/T02-results.xml`退出0：200 passed、1条Starlette对httpx TestClient的弃用警告；未隐藏该警告。独立审阅42目标测试/10组攻击探针退出0，发现的Session.close/保存点清理与缓存归档状态缺陷已真实RED→GREEN并独立复验关闭。细节见`docs/testing/T02.md`、`T02-review.md`。DB技术权限与测试中的虚构审批不能替代正式签发；进入approved仍明确NOT_IMPLEMENTED。

本阶段已本地提交：`ef8b5ac`（T00与Scrapling工具），`a0d7ec4`（Windows检出保留证据字节）；提交作者为Codex，不改全局Git身份，不推送或对外发布。第三方原始证据中的尾随空格保持原样，不清理而破坏来源hash。

后续本地阶段提交：`ca230d6`（T01）、`f30ea73`（T02）、`15c7a6a`（T03）、`2c980b3`（T04）、`8ffa6b1`（T05）、`032d5d7`（T06）、`fe7c988`（固定虚构provenance提交字节）、`687c571`（T07）与`e48e83c`（T08）。各阶段保留自己的实际测试分母；未推送。T09验收通过，沿同一分支继续T10。

## T03 实际执行

先实际 56 failed/0 errors（功能缺失断言），补最小解析后通过；随后为资源限制和独立审阅的漏读缺口补真实失败测试。父节点最终 `.venv/Scripts/python.exe -m pytest -q --tb=short --junitxml=docs/testing/T03-results.xml` 退出 0：269 passed，1 条既有 Starlette/httpx 弃用警告，21.06 秒。独立审阅 69 目标和 14 攻击探针退出 0；四组 P2 的表格容器、PDF 注释、DOCX 缩略图和不可见文字已修复并关闭。全部使用独立虚构材料。失败过程、收集错误及具体边界分别见 `docs/testing/T03.md`、`T03-review.md`、`T03-parent-checks.md`，不把辅助或收集错误计作有效功能 RED。

35 包应用/测试完整闭包已正式合并并实际安装核验，旧 T02 28 版本及构建证据保留；35 wheel/60 许可/40 依赖边与安装元数据一致，新增 7 安装 hash 一致，离线 hash-lock dry-run 与 pip check 退出 0。G06 两份已读源文件与实际 wheel 字节一致；这不证明整个源构建。来源开发门 13 项退出 0，发布门退出 1，实际阻断 G06/G10 的依赖审查与生产批准。默认 hash、schema 均核对通过。

PDF read 仅指已提取文字层；扫描页、图片、交互注释、不可见渲染和其他未读对象有明确 manual/unsupported。原件不可覆盖，parse 另存快照；baseline、错案及锚点由实际会话和后端原件核验。没有 OCR、全面视觉语义、独立 PDF 解码沙箱、真实试点或生产完成。继续 T04–T06 构建事实确认与四类 QCC-off/mock 审查流程。

## T04 实际执行

最终76目标中的首批56先真实RED（56 failed/0 errors），实现后逐项补来源、事务、百分比换算、期间证据和Decimal环境边界RED→GREEN。独立审阅实际助手会话追加伪quote解析仍被信任，两个攻击测试先失败；现复用T03 pure adapter从T02授权只读原件重算完整ParseResult，quote、全部anchor和未读/质量标记均核对，两个入口实际阻断。不重写T02/T03或修改原件。

父节点最终 `.venv/Scripts/python.exe -X utf8 -m pytest -q --tb=short --junitxml=docs/testing/T04-results.xml` 退出0：345 passed、1条既有Starlette/httpx弃用警告、32.59秒。独立76目标/31攻击探针/181受影响回归退出0，原文信任根P2关闭。defaults、schema、pipcheck及13项来源开发门退出0；来源release仍因G06/G10审批/依赖使用范围待审退出1。实际失败历史和边界在 `docs/testing/T04.md`、`T04-review.md`、`T04-parent-checks.md`。

确认快照以expected current→new+1完整追加，保序hash和历史确认人不变，决定reason仅受保护记录；服务保存点在caller捕获错误继续提交时也无半写。主体候选不会根据排序确认或作为企业entity ID，变化使批准/制品失效。计算白名单AST/Decimal，前月实付及期间需确认，不用年费/12猜测；数学和历史回放明确限制。

用户新增本地Obsidian工作流已更新AGENTS。检索没有本项目已有状态；结构化memory_record当前未提供，实际obsidian_local新增本地摘要/索引/链接并成功读回，不冒称API成功或索引缓存同步。没有私人笔记进入Git或运行prompt。法律规则、业务审查闭环、真实外查、律师验收和生产批准继续分别登记。

## T05 实际执行

正式首批50项实际功能RED（50 failed/0 errors），逐项实施并补充来源/版本/政策边界。独立审阅实证并关闭三组P2：草案/摘要/不可信URL被认证为完整来源、非law规则夹带未核验引用、同规则多获批版本条件重叠。来源证据改为服务端UUID绑定受保护exact UTF-8 bytes和登记hash；所有basis的非空法源引用逐源核验；时际/条件过滤后仍重叠则missing_facts并要求复核，保留历史、不按latest取代。

父节点最终 `.venv/Scripts/python.exe -X utf8 -m pytest -q --tb=short --junitxml=docs/testing/T05-results.xml` 退出0：431 passed、1条既有Starlette/httpx弃用警告、46.16秒。独立86目标/45攻击探针/124核心回归退出0；作者受影响152回归退出0。17个冻结文件父节点及独立SHA均匹配。defaults、schema、pipcheck、13项来源开发门及diff检查退出0；来源release实际仍G06/G10依赖审查/生产批准退出1。失败历史和范围见 `docs/testing/T05.md`、`T05-review.md`、`T05-parent-checks.md`，不把辅助构造/收集错误计功能RED。

真实规则批准仍BLOCKED_RULE_APPROVAL。默认14卡全draft、LAW/无authority，科技关闭；9条官方法源索引pending，无伪正文/hash/日期。来源候选门和虚构测试身份只证明技术授权/算法，不证明现实法源真实性、法律效力或执业许可。政策按具体案件隔离，内容hash与运行批准依赖hash分开；T06从完整真实snapshot选规则，模型只接收实际applied。原件事实重算继续复用T04，没有重写T00–T04或安装新依赖。

T07/T08细化和T08/T09只读预检仅PLANNING_ONLY。Word安装/COM注册已读，render_docx→soffice路径实测缺工具；Word离线候选尚未运行。T07候选51包尚未安装/SDK运行。下一步先T06四类独立虚构DOCX实际审查、18维/manifest、QCC调用0，再外查及修订，不跳阶段。

## T06 实际执行

正式首批15项先实际failed/0 errors，包括六个指定场景及严格raw JSON；后增修复、权限、原件/来源、逐块/跨条款、失败留证、约束/方向和数学精度边界。独立六组P2已真实RED→GREEN关闭：深层JSON异常、重复意见、候选/收尾失败丢usage、无谈判目标、义务方向与双通知遗漏、Decimal高精度及全局trap。实际原始返回最多一次修复，不是调用特殊dict替代JSON。

父节点最终`.venv/Scripts/python.exe -X utf8 -m pytest --junitxml=docs/testing/T06-results.xml -q`退出0：511 passed、1条既有Starlette/httpx弃用警告、75.18秒。独立80目标/77攻击探针/42权限CLI+22计算回归退出0，作者80目标/161受影响回归退出0；23冻结文件SHA/bytes全匹配。defaults/schema/pipcheck/来源开发门退出0，release实际G06/G10阻断退出1，详细命令/分母/辅助错误保存在T06.md、T06-review.md及T06-parent-checks.md。

四类实际文件路径demo均退出0：sales/service/lease/nda各完整18维和validation ok，分别3/6/5/4意见、3/1/2/1候选事实，明确确认版本2；每份审查3次和确认前候选1次mock，全部16次raw hash核对，QCC合计0。9JSON、受保护SQLite和原件实际存在并核对，未生成Word/PDF，未上传真实材料。未批准法律维度保持材料不足，mock不能正式签发。

接下来T07固定SDK与独立本地MCP模拟，随后T08预算和T09原生修订。T10–T13细化/只读预检只是PLANNING_ONLY；法律验收、真实账户/价格/数据政策、许可与部署继续阻断，不把规划或工程demo算生产完成。

## T07 实际执行

先审计并实际离线安装正式51包完整闭包，固定mcp/mcp-types2.2.0、httpx2/httpcore2 2.13.1。92许可、76依赖边和3120安装文件hash核对通过，环境68、旧53版本不变；所有production approval为空，build单独保留。15新安装真实执行，旧click已有；辅助35包no-op及候选dry-run未计51安装通过。

首批11真实功能失败后增量实现，不重写T00–T06/唯一DTO。实际SDK调用独立本机127.0.0.1 MCPServer，完整schema/价格/绑定批准由后端核验，管理与本案使用权限分离。独立实证P2包括普通律师权限、partial/error状态与raw保留、外部dynamic schema引用、首次lazy logger秘密反射；全部真实失败/实现/复验关闭，没有已知未闭合P1/P2。

父节点最终pytest/JUnit退出0：557 passed、零警告、94.57秒。独立46目标/66攻击探针/17授权回归均退出0、零警告，81冻结文件bytes/SHA匹配。defaults/schema/pipcheck/13来源development/diff检查退出0；release实际G06/G10/G13的6阻断退出1。详细实际命令、辅助错误和边界见T07.md、T07-review.md、T07-parent-checks.md及T07-dependency-review.md。

真实QCC/费用/模型/批准未启用。安全raw与未知状态不宣称全量核查/无风险；本机协议JSON/stateless子集不代表官方QCC兼容。caller rollback模拟收据仍可撤销，付费预留及发送标记持久性将在T08以显式Database短事务解决。此为T07当时记录：未来T09/T10候选未安装、Word未启动、UI未实现；沿顺序继续T08。

## T09 实际执行

37目标、646全套（173.18秒）、独立37目标/61探针/136关联回归、作者192关联回归全部exit0、0警告。75冻结源/测试/证据hash初终一致；53正式包/95主许可/78边、3423安装RECORD及36依赖冻结实际核验，环境69仅新增python-docx，lxml已原安装。

三类新中文报告、内部精确跨run修订、不可变批准/制品/current读取、savepoint与文件清理、hash-only审计完成；双当前文件的anchor/version归属真实RED修复。Word实际六轮/十页检查，原生Accept/Reject各完整五段exact，重复段与原件不变。详情见T09作者/独审/Word/父节点记录。

复杂与对外原件包自动修订保留人工表；QCC收据报告消费者/完整补丁后法律与数值语义重审未实现。mock正式签发实际BLOCKED_LIVE；发布门exit1/9实际阻断。法律金标准、真实试点和生产仍独立阻断。沿同分支继续T10，Jinja/MarkupSafe候选仅静态核查，不能整份覆盖当前正式53记录。

## T10 实际执行

保留T00–T09服务，薄接入14个指定HTTP端点、实际cookie/CSRF/成员权限、版本/批准/费用与幂等核验。后台任务持久保存输入/状态/事件，实际本机SDK网络期间释放请求事务；failed review不被记completed，旧规则证据和被撤销patch不能复用缓存成功。真实P2均先功能失败再修复复验，收集、fixture、定位和封证辅助错误单独保留。

父节点全套命令`.venv/Scripts/python.exe -X utf8 -m pytest -q --tb=short --junitxml=docs/testing/T10-results.xml`实际exit0：709 passed、0警告、203.00秒。作者最终332目标/关联；独审80独立+41正式+195关联，均exit0/0失败错误跳过。作者190封证文件在父七项检查前后全部同hash；schema仅既有CRLF/LF差异、JSON/LF规范化等于HEAD，默认与四原DOCX/provenance原bytes不变。

父普通CUA浏览器从新demo目录`.local/t10-browser-final/20261003T082500Z`实际建四案/chooser上传/逐项确认版本2/mock18维/五种处置/精确patch三范围/三audience预览，16份实际下载逐一比数据库hash、ZIP CRC、报告文字和内部w:ins/w:del原新全文；原件逐一等于固定fixture。四次虚构复核者正式按钮均BLOCKED_LIVE，正式approvals0，QCC ledger0，一条query_record仅Q0 plan_approval不是供应商调用。额外一个无上传DOM文字canary，实际img节点0/执行标记null；不能冒充全面XSS或法律评测。

55固定wheel/97主许可/79边/3467 RECORD、环境71、旧69版本/53完整对象/build1/17/T09安装证据保留。仅新增Jinja2/MarkupSafe两包，依赖门22正式/42独立实际通过；最后模板9项静态补证与作者4输入一致。defaults/schema/pip/source13开发/runtime55+build1开发均exit0；source release exit1/9、runtime release exit1/59为实际预期阻断，非生产PASS。完整浏览器网络捕获因CUA不可用明确NOT_RUN；仅声明资源/本地链接、应用console0和后端0厂商调用分别实证。六类页面可运行不代表真实律师金标准、OCR/国产渲染部署、完整补丁后重审或生产完成。详情T10作者/独审/依赖/父/browser记录，继续T11–T13。
