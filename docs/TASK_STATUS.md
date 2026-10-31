# 任务实际状态

2026-10-31 已原地升级并打开0.5.6：修复已上传Word辅助配置误报未读、完整来源wire上限、微信item字符串元数据拒收，以及已受理材料结果首次回读失败后停止追踪。保留同伴前端、原件/历史和未知回执；独审及最终可见冻结包注入GET失败后自动恢复/单次虚构模型/Word导出通过。91资料文件安装前后相同，656程序文件一致，首次启动保留81表197旧行及6受保护文件。当前停在本人登录页；原会话重读版本、重启后自动分析恢复、手机扫码/回复待收尾，真实合同未外发。[实测与边界](testing/material-weixin-repair/20261031/README.md)。

2026-10-30 已原地安装并打开 0.5.5：修复空白聊天本人微信连接，增加事项记录对话删除，取消逐次发送弹窗和附件勾选/用途，选择文件后回车上传；上传期间新写文字不会误发。复用同伴前端、现有归档和后台权限。三项改造独立 Spec/Quality 通过，实际冻结包虚构合同生成/Word 导出、当前与其他聊天删除/历史保留、二维码显示/断开补验通过；首轮删除等待不足未伪称整体通过。安装前后90资料文件保留，656程序文件一致，启动后旧81表159行及5受保护文件保留。原用户合同无效响应的具体原因未证实，不自动重发；升级后本人扫码/收件及法律质量仍待。[实测与边界](testing/interaction-repair/20261030/README.md)。

2026-10-30 已原地升级并打开 0.5.4：修复冻结包漏带 SSL 策略文件导致的微信暂停/模型未知结果，以及微信普通消息新增字段被拒绝的问题。沿用同伴前端；513 项关联回归及最终 63 项重叠定向检查通过，独立 Spec/Quality 双通过。实际冻结包 5 项连接/格式检查及真实模型历史成果回读通过（回读 0 新请求）；此前仅新增 1 次虚构 DeepSeek 请求并成功保存。89 份资料文件安装前后未改，656 程序文件匹配，首次启动保留旧 81 表105行及4份受保护文件。原未知请求不重发。当前已打开登录页，升级后本人扫码和真实测试口令收件仍待；真实附件业务、法律质量未由本轮验收。[本轮实测](testing/personal-weixin-m6/20261030/desktop-054.md)。

2026-10-30 0.5.2已原地安装：采用同伴前端及最终M6修复，打包提交e8284cf，独立Spec/Quality通过。409桌面、四开发门、冻结包15新建/10升级/7成果回读/7界面检查通过；安装后另15新建与7回读通过，0新模型请求。655程序文件与验收包相同，原85资料文件安装前后一致，首次启动保留79表73行和4份受保护文件。完整备份、旧安装器和非本项WIP保留。验证版未签名；产品内本人扫码、真实微信业务及法律质量仍待。[本轮实测](testing/personal-weixin-m6/20261030/desktop-052.md)。

2026-10-30 本人微信 M6 四项最终发现已修复并独立复核通过（e8e317f）：明确等待附件、主合同选择/待分配归属、暂停后同任务继续，以及排队发送前撤权核验。保留用户指定的同伴前端。最终源码17项 Python、106项前端原始日志已核对；另159项为较早源码的关联回归，控制器28项仅为实现代理报告。历史7381全仓结果本轮未找到最终原始日志，不作为本提交已独立核验的全仓证据。安装0.5.2、产品内本人微信及法律质量仍待。[修复实测与边界](testing/personal-weixin-m6/20261030/README.md)。

2026-10-30 已将同事前端 `4cef9e9` 合入当前集成分支：采用温情工作台与同节点双视图，保留本人微信 M6 入口、二维码资源与退出清理。合并源码新跑前端/底稿503、桌面409、两文件页面/资源36项及四开发门均退出0；前人测试不计入本轮。用户指定采用同事前端，旧本机界面WIP保存在独立字节备份和命名stash中，不覆盖新界面。安装版、真实模型/微信及法律质量未由本轮验收。

2026-10-29 最新前端已提交并推送 `dhb_law`：`4d2da4a`，远端完整SHA与本地一致；温情工作台/对话切换、资源和测试截图已纳入。推送前482前端/21页面资源通过。主分支另有微信桌面新提交，合并预览确认assistant.mjs清理行及两状态文档需合并，具体保留项已交接。未合并主分支/部署/更新安装版。[推送回执与合并说明](testing/dual-view/20261029/github-sync.md)。

2026-10-29 工作台/对话双视图已本地实现：右上角切换、同一输入与材料/底稿、消息独立滚动、底部输入和事项工具菜单/侧窗完成；多材料、窄屏菜单与关闭焦点已修正。482前端、21页面/资源及独立13组浏览器检查通过；生成中/只读/扩展长记录明确为回放。8张实际截图来自Mac Chrome共用前端/虚构数据。未提交/推送/更新安装版，待用户视觉评审。[本轮证据](testing/dual-view/20261029/README.md)。

2026-10-29 “法理之外的温情”前端已实施并完成本地工程验证：内置ImageGen生成首页设计稿及独立案头照片，落实浅石色导航、暖白/柔靛蓝、温和空状态与准确的保存反馈。固定PNG资源/MIME/包登记已接，新增用例有效RED→GREEN；461前端、21页面/资源及合成保存/历史/Word、独立9底稿/12技能/15抽屉通过。图像模型版本未暴露，不称image-2.1已核验。实际截图为Mac Chrome共用前端/虚构数据；用户视觉认可仍待。未提交/推送/更新安装版。[本轮证据](testing/frontend-warmth/20261029/README.md)。

2026-10-29 案卷桌面前端工程候选已验证：双区首页、事实记录册、成组接待字段和文稿优先抽屉完成；461前端/20页面、合成保存/历史/Word及独立9底稿/12技能/15抽屉检查通过。用户随后补充“法理之外的温情”设计方向，尚待按该方向修订，不称视觉验收。代码与截图保留本地，未提交/推送/更新安装版。[候选证据](testing/frontend-redesign/20261029/README.md)。

2026-10-29 前端风格改造完成本地验证：实际参考微信 CRM 设计文章，采用灰白/深绿与圆角面板，输入回到首屏，清单先于编辑，补齐面板定位、保存焦点和窄屏布局。461 项前端、20 项页面/静态资源检查通过；实际合成浏览器保存、只读历史与 Word 导出通过，六张主要截图及宽/窄屏补图已生成。截图为 Mac Chrome 运行 Windows 共用前端，非原生 Windows；本片未提交/推送/更新安装版，未做全仓及真实模型/微信验收。[本轮证据](testing/frontend-refresh/20261029/README.md)。

2026-10-28 本人微信 M6 桌面源码已接续收尾：复用现有收件/附件/TaskDraft/业务与模型账本，真实来源隔离、进程内凭据、原件先落库、发送预占且未知不重发均保留；桌面聊天已接本机二维码、验证码、固定当前会话、断开及安全刷新。主合同选择两轮独审问题已关闭，接续修复验证码文案、二维码手动恢复和旧测试数量断言。完整桌面409/409、前端416/416、Python全仓7381通过/3跳过/1警告、四开发门及三档窗口组件验收通过。当前0.5.1未包含 M6，原生构建、安装升级、产品内真实微信业务和律师法律质量仍未完成；独立通道扫码/固定回复不替代产品业务验收。[本轮证据](testing/personal-weixin-m6/20261028/README.md)、[白话交接](plans/2026-10-28-personal-weixin-m6-handoff.md)。

2026-10-28 本人微信真实通道已完成独立测试：用户确认微信助手入口并扫码，实际收到本轮文字和37,169字节虚构DOCX，下载解密SHA与原件一致；固定回复仅发送一次，网络回执保留unknown，用户另确认「已收到完整回复」。修复真实响应省略成功ret与附件encrypt_type默认值两处兼容问题，分别有效RED后最终75项通过；未放宽身份、域名、密钥、摘要或未知发送重试约束。测试进程已关闭，凭据只驻内存。尚未接安装版持久绑定、业务任务或法律模型，0.5.1未重打包；其他WIP保留。[实测与边界](testing/personal-weixin-live/20261028/README.md)。

2026-10-28 统一聊天直接模型闭环：读取当前更新与用户新版整理稿后，保留现有业务/执行账本，接通原生首次范围设置、自动材料分析、同任务追问、连续接待建档、来源显示与 Word 草稿。四能力以独立虚构数据在源码 Electron 完成真实 DeepSeek；全轮 10 个请求为 6 个可用成果、1 个收到但无效、3 个未知，旧回执及未知费用保留。独审确认的取消、追问归属、案件更正、档案连续更新及导出完整性分别修复回归。最终本机原地升级 0.5.1，651 安装文件一致，安装前后 83 个资料文件未改，首次启动保留旧 79 表/73 行；实际安装程序 7 项成果回读和 15 项新建虚构流程通过。WorkBuddy 完成两次只读工程辅助；微信官方 MIT 探针离线通过，但真实扫码/送达/业务接入及律师法律质量仍未验收。全仓未完成一次通过，环境失败及补跑按[本轮实测](testing/direct-model-mvp/20261028/README.md)记录，不继承旧 PASS。其他任务 WIP 保留，WIN-PATH-02/原生 AV 不关闭。

2026-10-27 提交前完整回归收尾：修复原生控制对旧 Main 组件的兼容及普通/材料控制帧分级上限，并用精确历史模型结构修复升级测试夹具；没有放宽生产安全校验。第一次有效全仓结果为51失败/6895通过/4跳过/24错误，修复后复跑为1失败/6969通过/4跳过/1警告。唯一失败已定位为宿主把删除的硬链接保留到回收站，产品继续正确拒绝多链接文件；测试仅对该环境跳过最后单链接恢复断言。最终未排除用例的完整复跑退出0：6969通过/5跳过/1警告（含上述1项环境跳过及原有4项跳过）。NSIS安装/升级/卸载、真实DeepSeek、真实微信、真实案件及律师法律质量仍未验收。[实测与边界](testing/unified-mvp/20261026/README.md)。

2026-10-26 Windows 0.5.0 修复版安装器与统一聊天合同闭环完成：最终 NSIS 146,012,159 bytes，SHA-256 911f00c0db1fb22f8086b2b535830869e4a35fe12ded72ffe8a77e07216858f0，早期 eb00fa10… 包已淘汰。实际打包版暴露建案500，根因是冻结后端漏带固定验收登记资源；backend.spec 已显式补入 tests/fixtures/acceptance 和 tests/acceptance/cases.json，未放宽路径/来源/摘要策略。桌面374项全绿；统一合同实际Electron/冻结后端完成合成账号、建任务、显式合成材料、建案、事实确认、模拟审查及真实重启，零页面错误/外部请求/模型提交。临时诊断日志已完全移除。NSIS首次安装/升级/卸载因本机已有正式安装且注册表备份工具被安全策略禁止而未执行，需干净Windows/沙盒；真实模型/微信/法律质量仍未验收。[实测与边界](testing/unified-mvp/20261026/README.md)。

2026-10-26 统一聊天材料 AI 源码接入完成：复用现有 DeepSeek/账本/后台执行，逐次原生确认绑定材料、模型和预算；修复静态模块与桌面打包漏项、授权到期及配置变化竞态，并在传输最后边界重核数据库材料版本和原件。实际并发只发一次，unknown 只查原请求，真实材料成果 qxbak 恢复一致且恢复 POST 禁写。最终153项目标Python、385前端、373桌面全绿，Chromium四场景和四开发门通过；独立Spec三项发现复审闭环。[实测与边界](testing/unified-mvp/20261026/README.md)。真实DeepSeek远端、真实微信、安装版和法律质量未验收，未进行真实材料外发；WIN-PATH-02/原生AV不关闭。

2026-10-26 合同候选计算/证据校验完成离线接线：独立从虚构原文整理4案8断言9比较，复用Decimal计算器；回放12份历史真实模型响应共60检查，18有计划项中9一致/9触发复核，42未覆盖仍待审。90目标测试（含38新增）、四开发门通过，独审未发现需修问题；根核对原响应复制链、72调用封印/预算及3正式prompt未变。本片0新模型请求/费用，C4仍仅实验候选第一，未接正式审查或安装版，非盲测提升。[实测与边界](testing/contract-calculation-gate/20261026/README.md)。

2026-10-26 合同智能体选优完成：5候选72新增真实DeepSeek调用、20个独立虚构场景；原留出C3 43/48对C2 42/48，但歧义敏感性分析均40/42，未证明优势。新4例C3/C4均23/24判断、22/24完整证据，C4以0对1协议失败列实验第一；两版仍各有结论/理由矛盾，正式prompt保留基线、不晋升。42离线工具测试及30项目评分测试通过，独立匿名内容/预算/封印审计完成；累计成功峰值估价0.481598元、未知1元保留、保护额19.103326/20元。C4仅单轮验证，完整法律/生产验收未做。[实测与决策](testing/contract-selection/20261026/README.md)。

2026-10-26 合同提示词评测v2离线纠错完成：必需/补充引用分离、额外观察全部验真、人工反证绑定输入/输出摘要与原文，结构通过不代表理由正确。首轮16已见虚构输出重放保留旧12通过，新16引用工程通过、1明确反证、15理由待审、3额外观察待核；这是事后诊断，不是模型提升。新增30项在97目标回归内全部通过，四开发门exit0，独审无重要遗留。[实测与边界](testing/contract-scoring-v2/20261026/README.md)。本轮0模型请求，正式prompts/默认mock/安装版不变；新候选只在实验目录，未盲测或生产晋升。

2026-10-26 已按用户要求将本机桌面 0.4.1 原地升级为 0.5.0并打开登录页：64资料文件先备份且安装未改，启动后63旧表全部旧行、原件/设置/凭据保留；586安装文件与验收包一致。370桌面、67升级Python及四开发门通过；旧版升级/新建/已安装备份恢复合成验收通过。补打包缺模块、中文路径shim及两处旧schema测试夹具；继续WPR校准发现进程过滤不生效，已停止并删除无关原始ETL。WIN-PATH-02/原生AV仍OPEN，真实微信模型及生产未验收。[本轮安装与后续证据](testing/desktop-upgrade/20261026/README.md)。

2026-10-26 WIN-PATH-02诊断推进：固定498c0c9，复用合成归档捕获6次首次发布rename自然WinError5，其中5次原样失败、1次仅在隔离实验立即再次调用成功。失败后自身句柄/RM/文件PID未捕获占用者，不等于无占用或已定位根因。76不同pytest通过不关闭间歇故障；产品644输入SHA未变，未加重试/GC/放宽权限。WIN-PATH-02及原生AV仍OPEN，0.4.1未更新；[新证据与低扰动反例](testing/restore-publication/20261026/README.md)。下一步捕获实际拒绝时间窗的I/O事件来源。

2026-10-26 D2g5h待收件UI完成：明确原目标、元数据20条分页、首批首条分发、严格九字段回执、未知只GET、跨微信/任务及离开保护。85项不同Python、444项Node（前端443+几何脚本1）、7项独立探针、四开发门、本机合成Chromium及1280/360px视觉检查通过；2项P2实际RED→GREEN，双轴独审0遗留。[实测](testing/weixin-pending-ui/20261026/README.md)保留首次浏览器5秒超时，第二轮完整通过。未更新0.4.1，全仓Python/安装包/真实qxbak/真实微信模型NOT_RUN；WIN-PATH-02和原生AV仍OPEN。后续可信身份、下载解密及E许可待；[同步回执](testing/weixin-pending-ui/20261026/github-sync.md)。下方为历史快照。

2026-10-26 D2g5g待收件列表完成服务与HTTP接线，复用已合并主线schema21：当前权限及历史归属重核、UUID分页/1..20上限、被分发锚点续页、五字段元数据、恢复模式阻断。最终3短组198不同Python（新增服务48+HTTP38）、独立4探针、四开发门通过；Spec发现目标无历史归属仍空页的P2已实际RED→GREEN并原探针复验，Standards/Spec均0遗留。[实际证据](testing/weixin-pending-list/20261026/README.md)。本片无UI、真实qxbak往返/全仓/Node/浏览器/安装与真实微信模型NOT_RUN；WIN-PATH-02和原生AV仍OPEN，0.4.1未更新。远端状态见[同步回执](testing/weixin-pending-list/20261026/github-sync.md)。

`dhb_law`已快进合入`codex/contract-review-v2`并正常推送源码`042b9d3`；Git fetch/ls-remote及递归树一致，原六份WIP恢复且未暂存，主目录57项补验通过。[实际合并回执](testing/dhb-law-integration/20261026/github-sync.md)。未完成的D2g5g HTTP保持待办。

2026-10-26 `dhb_law` 集成验证完成：接收`4325711`之后三提交至`afb6ab6`；四测试文件12+/2-修复13项新增历史升级异常、1项Windows编码失败及1项共同基线旧delta断言，未改变产品守卫。RED258项243通过/9失败/6错误；GREEN258、业务97、兼容217共572不同Python通过，388前端/369桌面逻辑/四门通过，独立Standards与Spec0确认问题。[证据](testing/dhb-law-integration/20261026/README.md)。依赖清单存在，缺的是隔离副本本机缓存，复用原缓存55+1包已验。原待收件WIP保全保持未提交；全仓/浏览器/安装/真实模型微信NOT_RUN，0.4.1、WIN-PATH-02及原生崩溃不变。主分支合并及GitHub同步见随后回执。

2026-10-26 待补材料与跟进清单首片在 `dhb_law` 本地实现：每项关联固定事实/材料版本，记录原因/影响/下一步/期限/状态/结果；来源变化显示重核、已处理回待办而明确取消不复活，重开干净清单读新提醒；旧记录/未知回执/跨绑定草稿保护保留。23后端专项、70schema专项、444关联/342兼容Python、40前端专项/388关联、369桌面通过（重叠）；独立HTTP8/Node6及真实合成浏览器/qxbak通过，旧40结构不变。扩展历史526通过/8失败/6错误，与基线相同14项异常已复现仍OPEN；运行依赖门仍缺清单。本片源码与提交前记录随当前提交交接，服务器/安装版未更新。[实测](testing/followup-worksheet/20261026/README.md)。

2026-10-26 材料目录与事实证据底稿首片已在 `dhb_law` 本地实现：顶部“事实与材料”按原话/解析锚点/人工摘录登记事实，日期/核对/相反说法分别保存，更正与移出保留历史，来源变动提示重核，未知只查回执。新增独立不可变表与assistant-evidence-v1，旧38份结构指纹保留；59专项/349关联Python、250兼容、348前端、369桌面通过（组间重叠），真实合成浏览器、原位升级/qxbak及独立复核通过。运行依赖清单仍缺失；本片源码和提交前验证记录随当前提交交接，安装版或服务器未更新，待补任务/争点/对练仍后续。[实测](testing/evidence-worksheet/20261026/README.md)。

2026-10-26 “接待追问与事项底稿”首片在 `dhb_law` 实现：对话页“接待底稿”保存原始陈述、五项内部提纲、追问/材料和独立客户回复；本地候选带理由/原话，准备AI任务沿原发送入口且不自动调用。连续保存人工值保留、完整意图晚结果隔离、断ACK查回执及恢复只读已验。专项17/关联235 Python、专项15/关联336前端、369桌面通过；实际Chromium、客户Word包/渲染、真实qxbak及独立复核通过。运行依赖门仍因清单缺失退出1，未提交/推送/更新服务器或0.4.1，真实外部模型、Windows及法律验收未覆盖。[本轮实测](testing/reception-worksheet/20261026/README.md)。

2026-10-25 CH-08 首片在 `dhb_law` 实现：顶部“成果与导出”可选保存回答/历史档案版本，核对客户或内部投影后复制/下载 Word；客户仅白名单客户回复，固定版本/摘要及当前权限重核。后端22、关联121（备份另1）、前端321、桌面真实临时目录369通过；实际 Chromium/Word渲染和包检查、qxbak往返及独立复核通过。运行依赖门因清单文件缺失仍退出1；未提交/推送/更新服务器或0.4.1，Windows与法律验收仍开放。[本片实测](testing/chat-output-export/20261025/README.md)。

2026-10-25 D2g5f已接待收件附件明确选择本对话已上传DOCX/PDF，沿原resolution保存、原收件不覆盖，丢ACK只GET；材料旧通知回退缺陷经独立RED→GREEN修复。根4短组237不同Python：236PASS/1既有WIN-PATH-02 FAIL（含22新），293Node（60新）/四门/真实本机合成浏览器通过，交叉独审0遗留，[实际证据](testing/weixin-media-selection/20261025/README.md)。可信微信/下载解密/pending列表/E许可待，0.4.1未更新，全仓长进程/安装版/真实账号模型等NOT_RUN，WIN-PATH-02和原生AV仍OPEN。产品`958b8e6`已正常推送，远端SHA/tree及5,761条目一致，[同步回执](testing/weixin-media-selection/20261025/github-sync.md)。

2026-10-25 D2g5e已接根CID固定descriptor明确分发/精确找回HTTP：最终事务核root归属，固定目标当前ACL、9字段脱敏回执、精确恢复GET与丢ACK只查；旧guard/schema19保留。7短组23模块701不同Python（含64新）/四门通过，整体独审0确认及5独立HTTP探针通过；[实际证据](testing/weixin-dispatch-http/20261025/README.md)保留首次不稳定61/3、夹具修正及64整组重跑、未用HTTP测试模块的摘要差异。无新UI/列表/真实微信；可信绑定、下载解密、pending附件选择/E许可仍待。0.4.1未更新，全仓/Node/浏览器/安装版等NOT_RUN，WIN-PATH-02/原生AV仍OPEN。产品`dd46b6a`已正常推送，远端SHA/tree及5,688条目一致，[同步回执](testing/weixin-dispatch-http/20261025/github-sync.md)。

2026-10-25 D2g5d已实施v19固定历史代际合成分发：复用receipt/TaskInbox/TaskDraft、逐固定binding顺序/当前ACL及完整父链，旧pending不阻新代，恢复只查。13关联短组1329不同Python（含100新）/四门通过，交叉独审0遗留，额外精确v18拒绝升级探针PASS；[实际证据](testing/weixin-generation-dispatch/20261025/README.md)明确5项旧fixture/oracle失败及受影响组完整重跑、两文件test-body快照例外。36前驱指纹不变，真实可信微信/下载解密/外发/E许可待；0.4.1未更新，全仓/Node/浏览器/安装版等NOT_RUN，WIN-PATH-02/原生AV开放。产品`2a4cca8`已正常推送，远端SHA/tree及5,630条目一致，[同步回执](testing/weixin-generation-dispatch/20261025/github-sync.md)。

2026-10-25 已补齐原生升级前历史语义校验：只读复用现有完整来源校验，在升级写入前和DDL写锁内按原版本核验，pending恢复同时核旧备份与current；真实v17→v18非法poll洗白反例已RED→GREEN。15模块427不同Python（含9新）/四开发门通过，两名独立审查0遗留及2独立快照/释放探针通过，[实际证据](testing/upgrade-preflight/20261025/README.md)。schema18/旧guard保留，v19代际分发为下一片；真实微信/模型关闭，0.4.1未更新，全仓/Node/浏览器/安装版等NOT_RUN，WIN-PATH-02/原生AV开放。产品`619c898`已正常推送，SHA/tree及5,538条目一致，[同步回执](testing/upgrade-preflight/20261025/github-sync.md)。

D2g5c产品`71802a6`已正常同步GitHub，远端SHA/tree及5,496条目一致；[同步回执](testing/weixin-generation-ingress/20261025/github-sync.md)。

2026-10-25 D2g5c专用schema18合成代际收件已实施：原逐条去重/回执/游标CAS与固定目标sidecar原子提交，正反跨代reply整批回滚，丢ACK按固定目标权限只查；恢复继续只读。34模块886不同关联Python全部PASS（含52新增，非历史累计），233Node/四开发门通过，两名独立代理分别Spec/Standards0遗留，[实际证据](testing/weixin-generation-ingress/20261025/README.md)。旧收件/绑定刷新/实际分发guard保持；下一片按代际分发及版本化来源校验，可信微信/E许可仍待。无新HTTP/UI/真实微信模型；0.4.1未更新，全仓/浏览器/安装版等NOT_RUN，WIN-PATH-02/原生AV开放。

SQLite路径修复产品`7f27f4b`已正常同步GitHub，远端SHA/tree及5,444条目一致；[同步回执](testing/long-sqlite/20261025/github-sync.md)。

2026-10-25 已修复SQLite精确只读路径与长路径恢复后再次备份：共享8处URI入口、局部快照DBAPI文件名，保留原件/引用/权限/结构守卫。新25已含于20模块289不同Python全部PASS，233 Node/四开发门通过；旧升级夹具漏表先基线复现再单处修正，58独立/88根回归通过。同一独立审查者双轴0遗留，[实际证据](testing/long-sqlite/20261025/README.md)。原A—C和D离线底座保留；按代际实际收件分发/可信微信/E许可仍待。0.4.1未更新，全仓/浏览器/安装版/真实微信模型等NOT_RUN，原生崩溃及WIN-PATH-02保持OPEN。GitHub按后附实际回执核对。

D2g5b 产品 `0738989` 已正常同步GitHub，远端SHA/tree及5,385条目一致；[同步回执](testing/weixin-provenance/20261025/github-sync.md)。

2026-10-25 D2g5b 已完成消息代际来源存档：schema18追加7字段不可变来源，按完整poll前缀和UTC固定历史目标；34前驱冻结、公共完整父链及两代真实qxbak/原件/恢复隔离已验。根33模块1094不同Python：1093PASS/1基线长路径FAIL（142新增全PASS），233 Node和四开发门通过，独审同人双轴本片0遗留、范围外故障OPEN；[实测](testing/weixin-provenance/20261025/README.md)。旧收件/分发guard仍暂停，下一片实际按代际接收/分发及可信微信/E许可；0.4.1未更新，全仓/浏览器/安装版/真实微信模型等NOT_RUN，原生崩溃/WIN-PATH-02保持OPEN。

D2g5a 产品 `6c0b26a` 已正常同步GitHub，远端SHA/tree及5,297条目一致；[同步回执](testing/weixin-generation-preview/20261025/github-sync.md)。

2026-10-25 D2g5a 已完成按持久代际的合成离线预览：同一事务核当前身份/root/latest权限、完整head/scope及当前两类cursor，预览不推进游标或写业务；安全拒绝保留原审计。根14模块361不同Python（50新＋135协议＋100服务＋76head/guard）、233 Node及四门通过，独立7例含真实锁竞争和权限审计；真实qxbak核旧session401/重新登录409，[实测](testing/weixin-generation-preview/20261025/README.md)。旧收件/分发guard仍暂停；下一片持久消息代际来源/完整性与实际合成接收分发，可信微信/E许可仍待。0.4.1未更新，浏览器/全仓/安装版/真实微信模型等NOT_RUN，原生崩溃/WIN-PATH-02保持OPEN。

D2g4 产品 `b3f204d` 已正常同步GitHub，远端SHA/tree及5,244条目一致；[同步回执](testing/weixin-generation-ui/20261025/github-sync.md)。

2026-10-25 D2g4 已将明确目标历史登记接入原对话页：预览零写、缺绑定才在明确保存时创建、两阶段丢回执只查、版本变化/迟到响应/撤权及导航守卫已验；真实qxbak恢复继续只读。根12模块229不同Python、15脚本233 Node、两组本机浏览器、四开发门均通过；同一独立审查者Spec/Standards两轴0遗留（非两名代理），[实测](testing/weixin-generation-ui/20261025/README.md)。D2g3欠缺的独立Standards已在本轮补完0确认违规，旧阶段记录保留。当前账号仍暂停，按代际接收/分发、可信微信及E许可待接；安装版0.4.1未更新，全仓/安装版/真实微信模型等NOT_RUN，原生崩溃和WIN-PATH-02保持OPEN。

D2g3 产品 `d6627de` 已正常同步GitHub，远端SHA/tree及5,197条目一致；[同步回执](testing/weixin-generation-head/20261025/github-sync.md)。

2026-10-25 D2g3 已实现最新代际七字段只读head：根与最新目标当前权限、完整历史及checkpoint同一个BEGIN IMMEDIATE快照，零代取持久grant/mapping而非当前scope，未绑定null；精确恢复GET不解锁写或收件。根14模块298不同Python、192 Node、四开发门通过，独立Spec无确认阻断；[实际证据](testing/weixin-generation-head/20261025/README.md)。最初同名测试收集错误及两项403/409预期错误均保留和分类；无产品guard妥协。独立Standards代理因宿主限额/WorkBuddy Bash拒绝未完成，root核查不冒充第二独立审阅。页面/按代际运行、可信微信、E许可未做，浏览器/全仓/安装版/真实账户等NOT_RUN，原生崩溃及WIN-PATH-02保持OPEN。

D2g2 产品 `00f17bb` 已正常同步GitHub，远端SHA/tree及5,152条目一致；[同步回执](testing/weixin-generation-http/20261025/github-sync.md)。

2026-10-25 D2g2 已完成代际历史的根CID HTTP接线：集中11字段脱敏回执、受保护POST及固定request GET，恢复精确读白名单；最终事务复用D2g1，不更改schema17或暂停guard。根10模块241不同Python、192 Node与四门通过，Standards/Spec独立审阅无确认遗留项，[实测](testing/weixin-generation-http/20261025/README.md)。WorkBuddy虽核实Kimi-K3，本次Bash权限拒绝后取消、未完成审查，由本机独立Spec代理替代。最新CAS head/UI、按代际运行、可信微信及E许可未完成；浏览器/安装版/真实账号模型等NOT_RUN，0.4.1、原生崩溃、WIN-PATH-02不关闭。

恢复诊断工具提交 `9c2acd2` 已正常同步GitHub，远端SHA/tree与5,117条目一致；[同步回执](testing/restore-publication/20261025/github-sync.md)。

2026-10-25 恢复发布诊断切片：仅开发脚本新增显式阶段/本进程句柄观察和25永久测试；root共4模块70不同Python、默认及诊断浏览器、四开发门通过，[实测](testing/restore-publication/20261025/README.md)。工具parent过滤与non-file handle误报经实际RED→GREEN修正；原WIN-PATH-02本轮未自然复现、无产品修补，仍OPEN，独立原生崩溃和0.4.1安装版状态不变。D2g按代际运行与HTTP/桌面接线、可信微信身份/资格及E有限期授权仍待。

D2g1 产品 `40be816` 已同步 GitHub，远端SHA/tree及5,082条目一致；[同步回执](testing/weixin-generation-service/20261025/github-sync.md)。

2026-10-25 D2g1 已完成显式代际追加/固定查询后端：当前principal/fence/schema17先核，root/前代/新目标当前ACL、完整scope与gen/hash/checkpoint CAS、因果时间及pre/post历史验证，旧来源和游标不改；恢复/撤权后查询仅metadata且当前权限仍核。根12模块310不同Python、192 Node与四开发门通过、独立冻结复核完成，[实测](testing/weixin-generation-service/20261025/README.md)。schema/暂停guard未改，尚无运行时切换、HTTP/UI或新账号/模型能力；浏览器/安装版等NOT_RUN，0.4.1、原生崩溃及上轮WIN-PATH-02失败继续开放。

D2f 产品 `6e36cb5` 已同步 GitHub，远端 SHA、tree 及5,073个受控条目一致；[同步回执](testing/weixin-generations/20261024/github-sync.md)。

2026-10-24 UTC D2f 已完成跨对话目标代际底座：schema17只追加generation表/集中DTO，32前驱native/non-native指纹保留；完整新旧历史、scope来源时间、账号暂停及永久撤权、普通TaskDraft继续人工处理、真实两代qxbak和篡改拒绝均有证据。最终24模块814不同Python、192 Node和四开发门通过；未来版本缺口经独审实际复现并RED→GREEN，[本轮实测](testing/weixin-generations/20261024/README.md)。旧workspace夹具58 setup errors已修并整组68通过；额外浏览器恢复在发布目录rename遇WinError5，该组FAIL，不以独立备份通过覆盖。无显式追加/切换服务、无新微信/模型能力；下一片D2g接当前权限/CAS/查询恢复。0.4.1、原生崩溃、WIN-PATH-02仍开放；全仓/安装版等NOT_RUN。

D2e 产品 `a42c415` 已同步 GitHub，远端 SHA、tree 及 5,061 个受控条目一致；[同步回执](testing/weixin-desktop/20261024/github-sync.md)。

2026-10-24 D2e 已完成对话页本机合成收件授权入口：新增集中View DTO、CID只读投影/显式POST及固定request GET查找，真实恢复middleware精确读白名单接续；页面仅同目标版本变化可明确更新，未知结果不重发，迟到CID/撤权/恢复隔离守卫通过。9模块255不同Python、14模块192 Node及三组浏览器通过，四门exit0；真实丢ACK后grant2/POST2、qxbak恢复GET200/POST409、DOCX/PDF旧Mock闭环均有证据。[实测](testing/weixin-desktop/20261024/README.md)。未改schema16；跨目标generation、真实微信/模型/E许可仍未实施；安装版0.4.1、原生崩溃、WIN-PATH-02开放。

D2d 产品 `ba03b02` 已同步 GitHub，远端 SHA、tree 及 5,051 个受控条目一致；[同步回执](testing/weixin-reauthorization/20261024/github-sync.md)。

2026-10-24 D2d 已完成同目标显式重新授权：追加第16版12字段不可变grant和集中DTO，完整当前scope/ACL/CAS及旧pending继续、blocked不复活、撤权/恢复隔离已验证。实际故障/丢ACK/并发/新进程、本地合成DOCX上传后重新授权与人工关联、两代qxbak及损坏归档拒绝均通过；26模块925不同Python用例最终有通过证据，四开发门exit0，30前驱指纹不变。独立发现UTC格式排序缺陷已RED→GREEN，18源码/8XML冻结复核无剩余确认缺陷。[证据](testing/weixin-reauthorization/20261024/README.md)。跨目标generation/可信入口和E许可未完成；真实微信/模型/安装包NOT_RUN，0.4.1、原生崩溃和WIN-PATH-02开放。

D2c 产品 `64a435e` 已同步 GitHub，远端 SHA、tree 及 5,040 个受控条目一致；[同步回执](testing/weixin-dispatch/20261024/github-sync.md)。

2026-10-24 D2c 已完成合成收件至共享TaskInbox/TaskDraft的受控分发：新增第15版不可变回执表及集中DTO、完整来源历史校验；复用既有聚合，不自动冻结或审查。实际当前权限/顺序/碰撞、事务故障与丢ACK找回、并发/新进程/两代qxbak、歧义与冻结补充通过；固定UTC刻度反例引出的账号因果时间修复已RED→GREEN，并核对撤后poll及其他peer接续。19模块679不同Python用例最终有通过证据，四开发门退出0；保留中间159项中5个历史测试断言失败及后续整文件91项替代，不称单次全仓全绿。独立冻结18源码/7XML复核无遗留发现。[D2c证据](testing/weixin-dispatch/20261024/README.md)。过期映射显式重新授权待做；真实微信/模型/安装包NOT_RUN，安装版0.4.1、原生崩溃和WIN-PATH-02开放。

D2b 产品 `f161660` 已同步 GitHub，远端 SHA、tree 及 5,029 个受控条目一致；[同步回执](testing/weixin-ingress/20261024/github-sync.md)。

2026-10-24 D2b 已完成本机合成账号/精确 peer 映射和原子完整收件服务：数据库真实 principal/owner/workspace、当前 ACL/完整scope/案件归档守卫、一次撤权、逐条 blocked/duplicate/conflict、空poll、完整 receipt 与 checkpoint CAS 同 commit、未知结果查询均有实际证据。9 文件 444 个不同关联 Python 用例通过、0失败/错误/跳过、1条有意伪造输入的序列化warning，四开发门退出0；SQL/commit故障、实际提交后回执丢失、双Session竞争、新进程找回及真实qxbak均已验证。独立冻结复核无遗留可证实发现。[D2b 实测](testing/weixin-ingress/20261024/README.md)。尚无真实账号认证/transport或TaskDraft分发；D2c待接，过期映射刷新当前阻断，真实微信/模型/安装包NOT_RUN，原生崩溃与WIN-PATH-02保持开放。

D2a 产品 `41874db` 已同步 GitHub，远端 SHA、tree 及 5,020 个受控条目一致；[同步回执](testing/weixin-inbox/20261024/github-sync.md)。

2026-10-24 D2a 已完成合成微信收件存储底座：追加第 14 个版本 weixin-inbox-v1 的 4 表和 4 DTO，账号/精确 peer scope、不可变完整回执、连续游标链、重复/冲突/撤权及引用归属均有完整性校验；前驱 26 组 native/non-native 指纹不改，旧六类来源校验在后继版本仍生效。16 文件 587 个不同关联 Python 用例最终通过、四开发门退出 0；C 盘资源 guard 造成的首轮 23 setup errors 在 D 盘独立合成目录复验通过，未改 guard。独立发现的跨 peer 引用缺陷已 RED→GREEN 并复验；两代 qxbak 精确保留历史且无任务执行。[D2a 实测](testing/weixin-inbox/20261024/README.md)。直接 SQL 夹具不代表运行收件，D2b 原子收件/checkpoint API、D2c 共享任务分发仍未实现；真实微信/模型和安装包 NOT_RUN。运行 SQLite 未加密；原生崩溃和 WIN-PATH-02 继续开放。

D1 产品 `8c7db52` 已同步 GitHub，本地/远端 SHA、tree 及 5,009 个受控条目一致；[D1 同步回执](testing/weixin-offline/20261024/github-sync.md)。

2026-10-24 D1 离线协议适配已实施：从精确 bot/peer 与当前桌面律师作用域生成只读预览；账号 opaque cursor 与任务整数 cursor 分离，uint64 ID 无损归一，DOCX/PDF 仅 pending，不具备附件读取/执行权限。当前身份、scope/材料/绑定/游标及案件撤权、归档、恢复隔离均有合成集成证据；权限拒绝可复用既有审计。5文件290个不同 Python 用例通过、四开发检查退出0，独立复核无遗留项。[D1 实测](testing/weixin-offline/20261024/README.md)、[官方协议核验](research/2026-10-24-weixin-protocol-d.md)。真实身份绑定持久化、complete Inbox/checkpoint、登录/轮询/下载解密/发送及真实模型仍未实现或 NOT_RUN；D1没有新增HTTP/IPC、数据库结构或依赖。

C 产品提交 `4b62f06` 已同步 GitHub，本地/远端 SHA、tree 及 5,002 个受控条目一致；[C 同步回执](testing/task-pdf/20261024/github-sync.md)。

2026-10-24 持久合同任务 A＋B 已实施：多条消息/附件先收集后冻结，超量/歧义消息不丢弃，明确材料版本后复用案件、事实确认与 Mock 结果；新增 task-drafts-v1 与备份恢复来源校验。正常 assisted 桌面通过持久合成任务准入完成 Mock，不改变全局模式；普通审查和真实材料仍受原保护。WorkBuddy 已核实 Kimi-K3 并参与独立复核。实际验证和未验项见 [本片证据](testing/task-drafts/20261024/README.md)。C 合成 PDF 桥接现已完成：PDF 只接受 original、完整可读才冻结，沿用现有案件/事实/Mock，不放宽普通合同上传政策；130 项关联 Python、170 项 Node、PDF 两种顺序及 DOCX 浏览器回归、已完成 PDF 的 qxbak 恢复与四开发门均通过。[C 实测](testing/task-pdf/20261024/README.md)。安装版 0.4.1、D—E 及 WIN-PATH-02 未标完成。 功能关联382项以独立模块/短组方式通过；单进程原生访问冲突仍待专项复现，未更新安装版。

A＋B 产品提交 `0178859b19457ff67543af66bb20c1863148b404` 已同步 GitHub，远端 SHA 与 tree 一致，递归 4,992 个受控条目相同；59 文件扫描禁止路径及已知密钥模式均 0，33 产品摘要匹配验证快照。[同步回执](testing/task-drafts/20261024/github-sync.md)。匹配 Windows 事件/转储确认 `python312.dll+0x8c2c0` 读访问冲突；两种各 200 次解析探针均退出 0，未定位根因或关闭长进程问题，转储未复制上传。[诊断记录](testing/task-drafts/20261024/native-crash.md)。

2026-10-24：连续文字对话与档案人工维护已完成本次源码范围。默认桌面profile发送最多带入当前绑定最近8轮/32KiB已完成文字问答，原生确认展示实际历史；档案12字段可编辑、明确清空并保护人工值，保留旧版本与只读限制。932项关联Python、10项前端HTTP/包装、桌面369项、前端165项通过；真实DeepSeek一次独立虚构请求成功（548 tokens，配置单价估算USD 0.0001797），临时密钥已删除。旧/新对话备份恢复及独立篡改、竞争测试通过。开发检查3项通过；运行依赖检查因本机缺少历史.audit-local证据阻断。Windows WIN-PATH-02仍开放；未更新服务器或安装版0.4.1。 [本次结果与边界](testing/conversation-maintenance/20261024/README.md)。

2026-10-22 RECEPTION-01：按用户确认的法律服务接待方向，已将 plugin.zip 的9份Word原件去重为8份私有可检索资料，并在接待页接入来源核对、三种模板工作稿、显式追加及绑定接待的对话草稿。105项相关回归通过；浏览器实际保存和重开核对。当前为SSH私有服务器试运行，模板未调用模型，真实模型仍未配置；安装版0.4.1未变。[证据](testing/reception-plugin/20261022/README.md)。

CH-07C3a源码与合成证据 `1a03d89` 已同步GitHub，远端SHA及4,949项文件树一致；[同步回执](testing/GITHUB-PROFILE-UI-20261023.md)。

2026-10-23 CH-07C3a已贯通桌面普通文字的统一发送、同次待核档案/接待保存及只读档案侧栏；既有请求和丢失回执只查询找回，不重复调用。保存状态依据真实回执，来源、版本、冲突及律师保护值可回查。相关Python去重265、桌面366、前端141及四门通过；Windows合成6组通过，恰好一次回环调用、档案与接待各保存一次，627份输入稳定。人工修改/联系方式、附件自动建档与导出仍待，安装版0.4.1和WIN-PATH-02状态未变。 [本片实测](testing/profile-ui/20261023/README.md)。GitHub产品同步已核验，见上方回执。

CH-07C2d源码及合成证据 `2dd5392` 已同步GitHub，远端SHA与4,832项文件树一致；[同步回执](testing/GITHUB-PROFILE-DESKTOP-20261023.md)。

2026-10-23 CH-07C2d完成可信桌面档案用途确认入口：复用原生窗口和私有管道，展示完整文字、本机保存目标及接待同步意图；保留authorized/existing区别，不把确认当成已保存。实机发现并修复既有聊天模块静态白名单遗漏。桌面366、前端68、相关Python19通过，四门通过；Windows原生5组、621份输入稳定，模型调用与业务记录均0。统一对话自动归档及档案侧栏仍待CH-07C3，安装版0.4.1和WIN-PATH-02开放状态不变。 [本片实测](testing/profile-desktop/20261023/README.md)。GitHub产品同步已核验，见上方回执。

2026-10-23 CH-07C2c已完成档案用途的后端应用入口：预览重建当前草稿及保存计划，私有管道许可固定一次调用，HTTP登记与原任务队列复用；已登记请求只找回，许可失效后用GET读取，不重发。完整Python回归4,393项通过、0失败/错误/跳过，四开发门通过，558份输入稳定；独立Spec9项、Standards10项通过。实际本机子进程/管道/HTTP合成链验证恰好一次回环调用。桌面用途确认与档案侧栏待接，安装版0.4.1及WIN-PATH-02开放状态不变。 [本片实测](testing/profile-application/20261023/README.md)。GitHub产品同步已核验，见下方回执。

2026-10-23 CH-07C2b2b-B完成内部档案执行与历史恢复闭合：复用单次调用账本和预算，同次回答、费用、待核档案/接待及固定保存回执原子提交；撤权弃候选保费用，恢复不重发。23文件首轮667/668通过，1项旧断言更正后原文件53项通过；产品源码未变，四开发门通过。原生许可窗口、HTTP/任务调度和档案面板仍待接入；安装版0.4.1及WIN-PATH-02开放状态不变。 [本片实测](testing/profile-execution/20261023/README.md)。GitHub产品同步已核验，见下方回执。

2026-10-23 CH-07C2b2b-A完成档案用途许可内核：完整保存计划绑定许可，普通聊天/资料回答/档案用途互相隔离，发送前后检查到期、撤权及配置变化，晚到候选丢弃而保留已收到用量。一次13文件379项关联通过（新增文件58项已包含），四开发门通过，546份工作区输入稳定。只修改现有registry，应用自动归档仍关闭；持久调用消费、费用和原子保存/历史恢复继续接线。 [本片实测](testing/profile-authorization/20261023/README.md)。GitHub产品同步已核验，见下方回执。

2026-10-23 CH-07C2b2a已完成可信数据库装配：读取实际消息、原请求摘要及档案/接待基线，拒绝跨会话、旧绑定和版本变化，同时隔离发送后新草稿；共用附件选择校验拒绝损坏快照。单次13文件源码回归393项通过（可信装配49项、附件解码22项已包含），四开发门通过、545份输入稳定，独立复核见证据。发送、费用与原子保存仍由C2b2b闭合，自动归档入口继续关闭；安装版0.4.1及WIN-PATH-02状态未变。 [实测](testing/profile-trusted-preparation/20261023/README.md)。GitHub产品同步已核验，见下方回执。

CH-07C2c源码与合成证据 `63f48c6` 已同步，远端SHA及4,758文件树一致；[同步回执](testing/GITHUB-PROFILE-APPLICATION-20261023.md)。

2026-10-23 CH-07C2b1：自动建档的存储前置切片完成。新命名schema及固定保存回执保留旧11版44摘要，三迁移通道与五族旧完整性校验接续；新格式/新回执仍fail-closed，未启用自动归档。20文件初轮630/632通过，2项旧测试预期修正后两个文件54通过；四开发门通过，542份输入稳定、产品源码未变，Spec6/Standards30独立通过。修复新摘要CHECK的NUL尾缀漏洞。安装版0.4.1和WIN-PATH-02开放项不变；未碰真实资料/模型/云。[实测](testing/profile-model-schema/20261023/README.md)、[执行合同](plans/2026-10-23-profile-model-schema.md)。GitHub以随后同步回执为准。

2026-10-23 CH-07C2a产品与合成证据提交a84a156227be7ad9cead1fd1ea237773defee3c4已正常同步GitHub；远端SHA及4,370文件树一致。35新增不同blob扫描0命中，538输入未变化、34暂存源码/测试/证据字节一致。发布回执仅追加文档，不改变380关联与独审结果；自动保存接线及WIN-PATH-02仍待办。[同步回执](testing/GITHUB-PROFILE-BASIS-20261023.md)。

2026-10-23 CH-07C2a离线发送准备完成：复用C1私有wire构建，basis绑定固定整理用途/handler、完整UTF-8请求/配置/模板摘要和本地档案基线/接待目标/修订/投影选择；prepare从实际saved run/message视图核对身份与保存前后版本。最终12文件380关联通过（54新增），0失败/错误/跳过，538输入稳定，四开发门exit0；Spec12、Standards9独立通过、0待修，旧DTO及C1字节保持兼容。合成service保存→prepare→合成响应解析实测通过，无模型/档案/接待写入。初始RED、测试同名收集冲突、两处开发夹具和独审长参数错误保留，不冒充产品失败或最终通过。本片没有新schema/native/registry/HTTP/自动保存；C2b须整体闭合用途许可、账本、固定钩子及迁移恢复，C3接档案侧栏。WorkBuddy本轮native_unavailable未派发，运行桌面、真实资料、安装版0.4.1不动；WIN-PATH-02仍开放，不重跑旧49分钟全套。GitHub同步以单独回执为准。[本片证据](testing/profile-basis/20261023/README.md)、[执行合同](plans/2026-10-23-profile-send-basis.md)。

2026-10-23 CH-07C1产品与证据提交bcc5013e0b7ce66be7827d37a5b41da1f7802cbd已正常同步GitHub；远端SHA及4,331文件树一致，52新增不同blob扫描0命中。577关联通过、535固定输入、旧协议兼容与独立复核事实不变；本回执阶段只追加发布证据与导航修正，C2/C3及WIN-PATH-02仍未关闭。[同步回执](testing/GITHUB-PROFILE-OUTPUT-20261023.md)。

2026-10-23 CH-07C1已实现独立的同次回答/当前文字档案提案协议，服务器填充出处并保持待核；默认关闭、有效回复后撤权保留用量。最终577关联Python通过，535输入稳定、四开发门通过；独审发现的数字日期隐式epoch及金额wire类型偏差已修复，Spec13和Standards8+4复验通过。旧324类DTO/既有方法、4组发送字节及20组响应保持兼容。此为协议/适配层，不代表自动建档已启用；C2仍须闭合用途授权、账本、固定原子保存钩子与恢复，C3接面板及本地联系方式。WIN-PATH-02仍开放，安装版0.4.1不变，本轮WorkBuddy无活动端点未派发。GitHub同步以单独回执为准。[本片证据](testing/profile-output/20261023/README.md)、[执行合同](plans/2026-10-23-profile-output.md)。
2026-10-23 CH-07B源码与证据提交34a153e3c9c698d43b136978e9a5ae66187b8b9e已正常同步GitHub；远端SHA和4,266文件树一致。上传145不同blob禁止路径0，两处已知合成拒绝URL逐字复核，未解释命中0；151变动文件、145源码/测试/证据暂存字节一致。发布文档独审19文件稳定、0必须修复。原全套3816/3和WIN-PATH-02开放状态保留，不能称全套全绿或Windows恢复已修复；CH-07C仍待接线。仓库仍public未改可见性。[同步回执](testing/GITHUB-PROFILE-PERSISTENCE-20261023.md)。

2026-10-23 CH-07B 后端实现与审阅已落盘，Windows 恢复可靠性仍有开放项：档案/接待/首次关联/内部回执在同一 savepoint 保存，提供版本回查、当前鉴权和来源标签；assistant-profiles-v1 两张不可变表、十种旧结构升级及 qxbak 历史重放已实现。完整 Python 回归实际为 3,816 passed / 3 failed（共3,819，0错误/跳过，2948.97秒），532份输入在运行前后不变，四开发门均exit0。两项失败已确认并修正旧测试夹具：外部资料路径测试没有隔离安装根、Jev替身缺少主模型上下文接口；定向分别9/36通过，另有两项错误路由负控制均按预期失败，产品权限控制未改。第三项在首次长路径恢复的最终目录rename报WinError5；既有孤立复跑通过，但根因未定，保留为WIN-PATH-02开放验收项，未加猜测性重试或放宽原文守卫。不能称单次全套通过或Windows恢复问题已修复。档案保存32、新schema71、原生升级53、完整性31、HTTP15、旧接待32、Chromium1等定向运行与完整回归有重叠，不累计。独立读取绑定、接待派生键碰撞、标签继承及回执时序问题均已修复并交叉复核。WorkBuddy本轮native_unavailable未派发；自动模型钩子/档案侧栏仍属CH-07C，安装版0.4.1、真实材料/法库/模型/云均未动。测试进程已经结束，接续先读本片最终证据和开放项，勿重复启动完整套件。GitHub同步以随后独立回执为准。[证据](testing/profile-persistence/20261023/README.md)、[执行合同](plans/2026-10-23-profile-persistence.md)。

2026-10-23 CH-07B1产品提交2ac3bb2d03b5f70bb6fd4e045a72567029ed2eeb已正常同步GitHub；远端SHA与4,141文件递归树一致，42个新增不同blob/429,143字节禁止路径与已知敏感模式0命中。524输入、38原始证据摘要、290本地链接检查通过；两份产品/测试暂存字节与实测一致。仓库仍public，未改变可见性。[同步回执](testing/GITHUB-PROFILE-SOURCES-20261023.md)。

2026-10-23 CH-07B1档案来源重建完成：基线0eb341a与远端一致、无开放PR或活动测试；新assistant/profile_sources.py按提案实际引用ID复用当前授权、附件records/files，从数据库及受保护原件构造ProfileSourceSnapshot。最多200用户消息/20文档，唯一引用去重；只接受本会话用户原话和当前选中解析版本，支持明确选择历史解析，部分读取保留未读项，损坏数据错误不暴露正文。事务外读取原件，返回前新事务重核权限/工作区/归档/恢复/作用域；仅composer变化兼容，投影转案后撤权也被阻断。Spec发现重复附件ID被字典静默取末项，已用RED反例修复拒绝。最终6文件186通过（40新增），0失败/错误/跳过，4开发门exit0、524输入稳定；Spec7/Standards8固定摘要通过。三处开发夹具失败已修，Standards初次非稳定字节结果不作为最终证据。成功读取不写业务记录，保留既有权限拒绝审计；无新DTO/schema/依赖/HTTP/UI/模型。WorkBuddy本轮native_unavailable无端点未派发；真实材料/法库/运行桌面/云未动，安装版0.4.1不变。下一步CH-07B完整原子保存/接待投影/回执/事件与迁移备份恢复；自动建档尚未接通。[证据](testing/profile-sources/20261023/README.md)、[执行合同](plans/2026-10-23-profile-sources.md)。GitHub同步以随后独立回执为准。

2026-10-23 CH-07A产品提交3e0b5d296df75d489d8553203f26cf6b068524d9已正常同步GitHub；远端SHA及4,094文件递归树一致，新增可达60个不同blob/838,197字节禁止路径与已知敏感模式0命中。仓库仍public，本轮未改变可见性；522输入、59原始证据摘要和文档链接检查通过。[同步回执](testing/GITHUB-PROFILE-MERGE-20261023.md)。

2026-10-23 CH-07A纯合并内核完成：基线a6d20ed与远端一致、无活动测试/开放PR；新assistant/profiles.py复用IntakeDraft/Anchor/ParseResult，DTO统一在domain.py。精确消息/选中附件来源、unknown不擦除、同值合源/异值并列、金额按角色、人工清空和旧接待整字段保护、显式接待投影与受众分离；无数据库/网络/模型/客户身份创建。独立复核发现并修复联系方式补造、旧核验状态不一致、环境Decimal精度绕过、旧引用跨对话4项。最终12文件400通过（含45新测试），0失败/错误/跳过，四开发门exit0，522输入稳定；Spec6/Standards9探针全部通过、剩余0。修复前393关联通过不包含新增反例，保留原证据不冒充最终。模型contact只允许unknown，受信人工值可保护；本地自动识别待做。版本过期拒绝，按当前base语义重放不增修订；请求级幂等与事务保存留CH-07B。WorkBuddy本轮native_unavailable无活动端点未派发；活动桌面、安装版0.4.1、真实材料/法库/模型/云未操作，无包体/启动资源新结论。下一片CH-07B原子档案/接待/回执/事件与迁移恢复，再CH-07C模型结构化输出和固定钩子。[实测](testing/profile-merge/20261023/README.md)、[计划](plans/2026-10-23-profile-merge-core.md)。GitHub同步以随后独立回执为准。

2026-10-23 CH-00A3产品提交03f46428d445306fd7c3a8a7094d0921b83f1cf1已正常同步GitHub；远端SHA及4,025文件递归树一致，上传前46个新增不同blob禁止路径/已知敏感模式0命中。仓库现为public，旧脚本private断言失败后独立核对元数据与完整树；本轮未改变可见性。520输入稳定、35证据摘要、292本地链接核对通过。[同步回执](testing/GITHUB-INTAKE-DECOUPLING-20261023.md)。

2026-10-23 CH-00A3接待依赖解耦完成：基线1a73e36与远端一致，先核对协作者已完成发送/轮次/选片/模型UX，修正README顶部的过时关闭状态。现有create_matter原行为下移matters.py，web.services保留同函数别名；now/encode/sha原语义下移record_codec.py，web.storage保留别名；intake不导入Web层，Word仅导出时加载。实际调用点失败注入保留完整转案回滚。有效RED1项后首批14通过；最终13文件147关联全部通过、0失败/错误/跳过，四开发门exit0、520输入稳定；Spec4/Standards4独立探针通过、0待修。新进程同探针未跟踪7次/跟踪3次前后：模块584→438，导入耗时中位数0.6157912→0.5709488秒，Python跟踪峰值41,330,852→35,343,162字节（约-14.49%）；不代表整机启动/RSS/包体。无DTO/schema/依赖/路由或新档案功能。WorkBuddy本轮native_unavailable无活动端点，未派发重试；双轴用子智能体。WIN-PATH-02旧两失败在未改产品前两个独立目录分别2/2通过，最终关联亦通过；根因未定、未修复，不能据旧日志认定扩展路径或nlink为因，文件守卫未改。活动桌面、真实材料/F盘/真实模型/云及安装版0.4.1不动。[实测](testing/intake-decoupling/20261023/README.md)、[执行计划](plans/2026-10-23-intake-decoupling.md)、[CH-07设计复核](plans/2026-10-23-profile-draft-readiness.md)。GitHub同步以随后独立回执为准。

2026-10-22 UX-01对话页模型UX小片完成（所有者宋萌律师当日直接指令三项）：①排查"API已配置但发送按钮灰色"——诊断链：后台无日志（桌面刻意丢stderr）→后端回环端口存活→密钥文件已存→DeepSeek直连可达→库内当日runs/attempts/conversations全0（发送从未到达后端）；根因为模型启用是后端进程内存态（registry/configure不持久化，重启即回"本次运行未配置"）叠加capability需已保存草稿触发；本片补窗口焦点回来自动refreshGeneration覆盖剩余路径。②取消每次手动「配置本次运行」（所有者明确要求的安全姿态变更）：desktop-settings.json新增严格校验的model键（仅deepseek-flash/deepseek-v4-pro），设置页配置成功持久化、显式停用清除、替换/移除密钥不清除（下次启动用新密钥恢复）；startBackend就绪后await autoConfigureModel用本机已存密钥自动恢复，失败安静回退设置页兜底；恢复副本工作区永不自动配置；Jev不参与。不变闸门：每次发送仍走桌面原生确认窗逐次核对全文/接收方/预算上限，lease单次语义/会话绑定/120秒有效期不变，密钥只在OS保护存储不落任何文件。③对话页「保存草稿」左侧新增「切换模型」按钮：新desktop/model-bridge.cjs导出registerAssistantModelBridge（desktop:assistant-model-status/model-switch两IPC，仅对话页主frame+state.mode==='ready'+非恢复副本可调，切换成功才持久化，未配置报UNCONFIGURED引导去设置页）与autoConfigureModel；preload desktopAssistant加modelStatus/modelSwitch；#switch-model无桥隐藏、文案显示当前模型名、切换成功自动refreshGeneration重算capability（两模型价格不同）。验证：桌面全套件270/270（新model-bridge 5项：状态校验/互切持久化/陌生调用/未配置/失败与撒谎configure矩阵；model-settings-navigation更新2项旧语义为"备份/崩溃后返回恢复持久化配置"+新增2项：启动自动配置与停用清除、对话页桥收发与login/子frame/恢复副本拒绝；judge-settings-ui桥键断言同步4键）；前端全套件68/68（新增渲染2项：按钮可见性/文案/忙碌/只读矩阵与模板位置断言）；四开发门exit 0；Python后端零改动（git diff可证）。开发修正保留记录：beforeCredentialChange曾误清持久化选择导致换密钥后不再自动配置（改为仅显式停用清除）、autoConfigure改await消除竞态。无schema/依赖变更；安装版0.4.1、真实材料/云未动。[证据](testing/model-ux/20261022/README.md)、[执行合同](plans/2026-10-22-model-ux.md)。GitHub同步以随后独立回执为准。

2026-10-21 CH-06B3律师选片GUI切片完成：律师在对话页勾选本会话已保存引用1–8条→服务器确定性预览→桌面原生确认窗→发送一次资料辅助回答（v1单轮锁定）。预览扩展：MainContextSelection新增request_id（可选，旧字节不动）、MainContextPreview新增send_basis——basis的source_bindings.citation_sha256为持久记录规范编码哈希，JS桌面端无法自算，须服务器在ready且给request_id时用assemble_context返回records调build_basis/build_basis_rounds组装；DTO校验send_basis非空⟹state=='ready'且scope/revision/三sha逐字段一致、source_bindings与manifest.sources同序；sending_enabled恒False不变。桌面授权链新通道：preload authorizeContext桥→IPC desktop:approve-context（validContextInput校验→桌面自行GET草稿/材料+CSRF POST context-preview→state/scope/revision/question/sources顺序/send_basis全量比对→确认窗library_context变体六键校验渲染问题全文+片段清单、窗口高700、决策仍走boolean通道→lease.authorizeContext单次语义）；model-control.cjs新validContextBasis十键严格形状校验（v1字面量锁、max_rounds锁1）；desktop_control.py _OPERATIONS新增authorize_context分发到既有NativeModelControl.authorize_context（服务端重建basis比对不变）。前端新assistant-context.mjs控制器：savedCitations从research receipts按位配对汇集去重（≤8/receipt）、保序勾选≤8、request_id惰性铸造（仅preview时mint，不消耗既有测试确定性uuid序列）、点选/撤选/编辑/换对话即预览作废、与generation/research三向互斥、send走saveDraft→原生确认→POST context-generations→NETWORK_UNKNOWN只经by-request找回不重发→host.accept→tracking；渲染层#context-panel列表/计数/预览摘要/状态行，context输出引用渲染可点「核对已保存片段」走既有引用侧栏。验证：前端全套件66/66（含新增选片11项）、桌面全套件264/264（含新增model-control-context 16项/context-approval 4项/确认窗context变体4项，judge-settings-ui桥键断言同步）、Python关联回归10文件125通过2失败——2失败逐一核验为基线同等复现的预存在环境家族（FILE_LIMIT_OR_LINK `\\?\`前缀nlink假阳性家族及其同机制变体，WIN-PATH-01起潜伏），基线51b2875独立worktree同机同参数复现2/2，本片未改workspace_backup.py；四开发门exit 0。端到端合成走通2项：HTTP预览携带send_basis→原生授权（session绑定HTTP会话、portal.call同环与生产桌面同进程语义一致）→HTTP发送202→回环实收1次且线上字节与不可变登记wire逐字节相等→引用一致→历史含所发问题、by-request找回completed→重复授权existing不重授、重放提交同attempt不重发→Jev零预留零调用；篡改basis授权前拒绝零外发。开发过程修正全部保留记录（build_basis_rounds导入来源、前端夹具三处缺陷、惰性requestId、_owned取行、order变体条件、两处测试笔误、e2e工作区根目录与同环两处真实环境适配）。无schema/依赖变更；安装版0.4.1、真实材料/模型/云未动，真实DeepSeek供应商接入与v2多轮界面不在本片，Jev真实预算仍未配置。[证据](testing/selection-gui/20261021/README.md)、[执行合同](plans/2026-10-21-selection-gui.md)。GitHub同步以随后独立回执为准。

2026-10-21 CH-06B2c2同run受限串行循环切片完成：新输入格式`library-context-v2`（template_version saved-library-context-system-v2）允许模型从round 1起输出工具计划，v1字节与语义完全不变。工具计划响应协议：MainContextToolCall{tool,query|saved_citation_id}互斥、tool仅限两个固定字面量且陌生tool在DTO层拒绝；MainContextToolPlan{calls:1..8}；MainContextReply.tool_plan与output恰好其一。plan不落outputs表、写internal事件model.tool_plan，attempt照写received receipt、run保持generating。轮间授权显式形状：NativeContextAuthorization/MainContextSelection新增max_rounds（int 1..4默认1），v2⟺max_rounds>1否则BLOCKED_LIVE，policy.max_calls=max_rounds，registry grant键不变、lease新增generate_rounds分支（basis全等+require_policy+preflight）。结构版本`assistant-rounds-v2`：rounds-v1表input_format CHECK不含v2且SQLite不能ALTER CHECK，复用12步重建序列加宽CHECK（其余对象字节不动、v1冻结摘要固化入测试），三条迁移通道同片闭合、新建==升级==schema_rows字节一致。runner主循环execute_context_run：round→settle→plan→固定handler（服务端call_id+to_thread）→dispatch_round下轮；末轮仍plan先停后执行（rounds_exhausted），预算不足budget_exhausted，工具拒绝tool_rejected/tool_limit，bounded_stop写事件+run failed。撤权不做dispatch预检：先占轮次，claim拒绝走既有abandon通道立即闭合（attempt failed_before_send+run failed）；恢复封存（run generating且无在途attempt且存在plan事件→interrupted）与取消后重入STATE_CONFLICT安静返回不重发。完整性开放rounds='v2'模式：v1恒单轮，v2 run 1..4轮连续，非末轮恰一plan事件，_events_rounds全序列比对，_validate_rounds_replay绑定plan↔tool.before↔receipt↔下轮exchanges（末轮plan允许工具前缀语义），篡改矩阵全拒。claim签名变更为(token,prepared,config)三元组，runner与关联测试同步适配。本片目标10文件240项全部通过（rounds_runner 19项：双轮happy path含wire逐字节与事件序列断言、replay幂等、task_manager端到端、伪造/跨run引用、四种停止、8工具上限、轮间撤权、恢复封存、三种非法plan形状、v1收plan拒绝、5变体篡改矩阵；rounds_schema 34项：v2 currentness、v1冻结摘要固化、最小差集、v1→v2带数据行保留重建、双目标×8位置中途失败原子回滚、损坏拒修、约束矩阵、fresh==migrated==schema_rows）；四开发门exit 0。广域关联回归10文件214通过13失败，13失败逐一核验全部为基线同等复现的预存在环境家族：12项FILE_LIMIT_OR_LINK（`\\?\`前缀basetemp路径nlink假阳性，WIN-PATH-01起潜伏）+1项同机制变体（文件守卫先于ASSISTANT_MODEL校验触发）；本片未改workspace_backup.py，基线c81e1c3独立worktree同机同参数复现13/13同等失败。开发过程修正全部保留记录（wire断言对齐DTO dump、恢复封存STATE_CONFLICT安静返回、task_manager测试拆grant()、dispatch撤权顺序、_plan_events SQL优先级、末轮plan走查、授权条件表达式、CHECK约束倒逼新增结构版本并修正合同原表述）。无新依赖；安装版0.4.1、真实材料/模型/云未动，真实DeepSeek供应商接入与律师选片GUI不在本片，Jev真实预算仍未配置。[证据](testing/bounded-rounds/20261021/README.md)、[执行合同](plans/2026-10-21-bounded-rounds.md)。GitHub同步以随后独立回执为准。

2026-10-21 CH-06B2c1有界轮次账本底座切片完成：新schema `assistant-rounds-v1`重建`assistant_model_attempts`表（破除UNIQUE(run_id)，新增不可变round_no INTEGER 1–4与UNIQUE(run_id,round_no)，immutable input trigger纳入round_no，claim/delete触发器保持V1冻结字节），为同一run的有界多轮提供账本底座。SQLite不能用ALTER删约束，按固定12步重建序列执行（DROP三触发器→临时名建表→INSERT SELECT补round_no=1→DROP旧表→RENAME→重建三触发器），新建库与逐步升级跑同一语句序列保证sqlite_master字节一致。FK事实：FK ON下DROP有子行的父表被拒（sqlite 3.53.1实测IntegrityError），三条迁移通道（schema_migrations.upgrade_database归档恢复、web/workspace_upgrade工作区打开、rounds_schema.initialize_storage初始化）均显式开FK OFF窗口、提交前foreign_key_check、finally恢复ON。完整性校验fail-closed：round_no类型/范围校验，同一run轮次必须从1连续，本片不定义中间轮语义，多轮（n>1）归档一律ASSISTANT_MODEL_INTEGRITY拒绝；attachment/judge/library integrity白名单同步加新版本。行为不变：两处INSERT显式round_no=1、_previous JOIN与authorize_context查询限定round_no=1，claim/settle/read/recover语义不动。本片目标11文件220项全部通过（新增rounds schema 21项：当前版本/旧版本冻结/最小差集/带数据行重建保留/8位置中途失败原子回滚且FK恢复ON/4项损坏拒修/约束与不可变矩阵/新建==升级==schema_rows三入口相等；context备份损坏矩阵新增second_round fail-closed变体）；四开发门exit 0。测试修正记录：seed合成run的state从'received'改为'completed'（run与attempt状态机不同）、旧test_one_attempt_and_output_per_run语义更新为同run同round唯一、ledger fixture走完整初始化链。无新依赖；安装版0.4.1、真实材料/模型/云未动，循环runner/工具计划协议/轮间授权/选片GUI均不在本片，Jev真实预算仍未配置。[证据](testing/bounded-rounds/20261021/README.md)、[执行合同](plans/2026-10-21-bounded-rounds.md)。GitHub同步以随后独立回执为准。

2026-10-21 CH-06B2b2资料辅助发送闭合切片完成：新schema `assistant-context-v1`（attempts加不可变input_format并迁移旧行为plain、新有序关联表assistant_model_input_citations、immutable trigger纳入新列），新建库与逐步升级结构相等、冻结library-v1摘要不变、旧0d53fdf代码实际拒绝新结构。登记同事务闭合message/run/attempt/有序关联/预算/reserved event，同request_id幂等重放逐项比对内容/范围/格式/引用顺序；claim/settle/read/history按持久化格式分派，未知格式即损坏。原生authorize_context服务端重建manifest核对basis（max_calls=1、allowed=(manifest_sha256,)），registry租约区分两种basis且互斥；context分支零Jev预留。归档经context_integrity/model_integrity按版本+格式校验，恢复走既有quarantine/fence/recover不重建许可不重发。应用入口POST context-generations（202）接通submit_context，网页不能自选格式。一次资料辅助回答经原生授权+回环HTTP，线上字节与不可变登记wire逐字节相等。本片目标8文件120通过（新增75项：schema36/send14/native7/backup16/routes2）、四开发门exit0；完整全套3450通过2跳过，51失败全部为qxbak恢复家族环境类：本机`\\?\`前缀路径link/unlink后stat陈旧nlink=2（WIN-PATH-01起潜伏）叠加WorkBuddy回收站shim深路径Errno53，基线09db5f6 stash复验16代表项同等失败；本片备份测试以字节相同副本恢复跑通完整信任边界，不削弱产品检查。开发过程6项真实缺陷修复均保留记录（完整性白名单、重放引用比对、授权顺序、方法名统一、两处测试反模式）。疑似WIN-PATH后续问题另列待查。无新依赖；安装版0.4.1、真实材料/模型/云未动，选片GUI与真实供应商不在本片，Jev真实预算仍未配置。[证据](testing/context-send/20261021/README.md)、[执行计划](plans/2026-10-21-context-send.md)。GitHub同步以随后独立回执为准。

2026-10-21 CH-06B2b2a产品提交a26fb1d0af7e0e88cb7bbea2c811e891ddd3072c已由WorkBuddy正常同步GitHub：推送前fetch无分叉，推送后ls-remote远端SHA与本地HEAD一致，fast-forward、63文件、全仓3,909受控文件/108提交；暂存内容已知敏感模式0命中，无强推、未改可见性。提交身份为本仓本地配置WorkBuddy。[同步回执](testing/GITHUB-CONTEXTPROVIDER-20261021.md)。本片适配基础完成，继续CH-06B2b2。

2026-10-21 CH-06B2b2a适配基础切片完成：新增明确上下文输入/模板、完整引用摘要及确定版本后继，复用既有预览重建精确wire；候选只接受选定UUID/hash，合法usage在拒绝候选时保留。公共DeepSeek HTTP/响应封套拆出共用，main.py 242→53行，旧V1 DTO/字节保持；默认预检拒绝且密钥前后各核验，无应用入口接线。最终542关联Python全部通过（含75新增）、四开发门exit0、500输入稳定；Spec6独立与Standards6（含4复用）通过，无待修项；旧4组wire/25响应逐字一致。WorkBuddy本轮wb-c11f6dc1285f实际completed，只读3文件，条件疑问已核对。有效RED、测试receipt字段误用6失败及旧Jev报告设置setup error保留并已修正复验；不冒称产品失败全消失。无新依赖/schema/队列；安装版0.4.1、真实材料/模型/云未动，未测GUI/冻结/安装器及总体资源收益。下一片B2b2仍须输入格式列/来源关系/原生许可/同attempt与升级恢复闭合后启用资料发送。[证据](testing/context-provider/20261021/README.md)、[执行计划](plans/2026-10-21-context-provider.md)。GitHub同步以随后独立回执为准。

2026-10-21 WIN-PATH-01产品提交e387d8cac67cfc9e093747094b8d3454c953109f已正常同步GitHub；远端SHA与3,850文件树一致、历史106提交、仓库仍private。53个新增可达blob禁止路径及已知敏感模式0命中；3产品/测试和56证据暂存字节一致，493验证输入稳定，243本地链接存在；发布文档独立复核无必须修复项。[同步回执](testing/GITHUB-WINPATH01-20261020.md)。本片源码可靠性修复完成，安装版仍0.4.1，继续CH-06B2b2。

2026-10-20 WIN-PATH-01合同原件长路径源码切片完成：唯一产品改动在persistence.py，复用现有filesystem/application路径工具，创建、读取、根初始化及事务清理一起适配；普通逻辑根、相对引用、授权/SHA/独占及事务所有权不变，无依赖/schema变更。最终424关联Python全部通过（含20新增单元及3集成）、四开发门exit0、493输入稳定；独立Spec4/Standards4通过、0待修发现。Windows实际TCP16请求通过合同上传解析/原件下载/qxbak/两次只读恢复，原件父目录279→282→282字符，数据库208/211字符，模型/Jev0，3服务器已退出。WorkBuddy本轮wb-b9aff7ba1c57实际completed，3文件只读计划复核，mkdir所有权意见已核对。有效RED及TCP首轮WinError10054保留；20次定向拒写与原探针重跑通过，但连接复位根因未定。旧cnbak普通路径回归不等于任意长目标支持；UNC/超长SQLite/GUI/冻结/新安装包未验，0.4.1与真实资料不变。下一片回到CH-06B2b2新输入/许可/来源/原生确认/升级恢复；[证据](testing/contract-long-path/20261020/README.md)、[计划与执行](plans/2026-10-20-contract-long-path.md)。GitHub同步以随后独立回执为准。

2026-10-20 CH-06B2b1产品提交d878ec19fe176447dc0244350fe596415a1911a5已正常同步GitHub；远端SHA与3,788文件树一致，仓库仍private、无分叉/开放PR。100个新增可达blob禁止路径0命中，1处既有合成拒绝URL已逐字核对，未解释敏感模式0；10个产品/测试、95证据暂存字节一致，235本地链接通过。首次只读核验TLS失败后重试成功，未关闭校验。[同步回执](testing/GITHUB-CH06B2B1-20261020.md)。

2026-10-20 CH-06B2b1本机完整上下文预览接口完成：独立DTO/纯投影/来源服务/薄HTTP，1—8条有序历史引用由服务器重建；保留问题、原文版本位置和待核状态，完整UTF-8预算超限不截断，全部sending_enabled=false。无新DDL/依赖/许可/模型账本或选片UI，旧V1固定973字节保持。最终644关联Python（含57新增）、四开发门exit0，491输入稳定；Spec6独立/Standards4定向通过、无本片待修项；Windows源码实际TCP9组27请求，模型/Jev/密钥读取0，服务器已退出。WorkBuddy本轮connected后wb-93002fc64088完成2文件只读计划复核，缺失第三路径跳过，错误推断已核对纠正。广泛回归先有测试重名收集错误，改名后因深目录中止；独立重现旧合同WinError206，未把其他F一概归因，旧长路径另列WIN-PATH-01待修。目标runner一次导入配置错误已修，失败/中止/无效陈旧XML计数说明均保留；不称完整全套、GUI/Electron/冻结安装器或真实模型验收。安装版0.4.1不变。下一片B2b2新许可/不可变输入格式/账本/原生确认/升级恢复一起贯通；[证据](testing/context-preview/20261020/README.md)、[本片合同](plans/2026-10-20-context-preview-execution.md)、[后续设计](plans/2026-10-20-context-send-storage.md)。GitHub同步以随后独立回执为准。

2026-10-20 CH-06B2a产品提交db24134024e11b4cf4c66c8e6b0d4feb900db69c已正常同步GitHub，远端SHA及3,681文件树一致，仓库仍private，无分叉/开放PR。上传前123个新增可达blob禁止路径与未解释敏感模式0命中；29个产品/测试和104个证据文件暂存字节一致，231本地链接通过。源码回归分两批3233+38覆盖3271不同用例，非单次全绿；[同步回执](testing/GITHUB-CH06B2A-20261020.md)。

2026-10-20 CH-06B2a本机检索与聊天引用面板完成源码工程验证：明确选择、200字关键词、固定5候选，复用同一任务/取消/关闭和B1持久回执；无模型/Jev调用，历史原文片段可在当前法库离线和只读恢复后回查。薄路由、研究服务/纯记录校验及两个前端模块解耦，无新DDL/依赖。Python首轮3233通过/38失败/0错误跳过，后38项在D盘全新临时目录补验全部通过；同一484输入分两批覆盖3271不同用例，不称单次全套通过。首轮C盘可用低于40GiB保护，产品阈值未改；独立环境复核完成，四开发门exit0；55顶层Node及真实源码浏览器8组通过，3工具回执/2引用、模型/Jev0、浏览器外部请求0。此前试跑在补充独审发现归档P2后主动中止，修复共享校验及其旧B1子串误判后79相关通过，Spec4独立通过/Standards两批各2通过，0待修；失败和中止证据保留。WorkBuddy本轮connected后wb-4cc5182886cd完成3文件只读计划复核，不冒称产品实测。前端窄窗/20px/键盘实测，非物理IME/系统缩放/冻结安装器；已安装0.4.1、真实资料/模型/云不变。下一片完整上下文许可与一次回答，后续有界多轮；本地验证闭合，GitHub同步以随后独立回执为准。[证据](testing/library-chat/20261020/README.md)；[执行合同](plans/2026-10-20-library-chat-execution.md)；[接续准备](plans/2026-10-20-library-context-readiness.md)。

2026-10-20 CH-06B1产品提交7d2506315eff0a619e665d299a6c8f637a028c1b已正常同步GitHub；远端SHA与3,563文件递归树一致，仓库仍private，无分叉/开放PR。79个新增可达blob禁止路径和未解释敏感模式0命中；24个产品/测试及52个证据暂存字节核对通过。[同步回执](testing/GITHUB-CH06B1-20261020.md)。

2026-10-20 CH-06B1内部持久引用切片完成：沿641a6e8，新assistant-library-v1两张不可变表，固定tool.before→受限本机法库→同事务回执/引用；服务器UUID、同请求重放、最多8个逻辑工具事件、当前权限/取消/版本/fence重核。历史快照与当前源复验分开，qxbak保留历史并撤销会话/隔离运行，旧cnbak拒绝新助手记录；完整链/未完成事件/来源依赖/规范JSON与内容摘要均核对。最终完整Python回归3222项通过、0跳过，0失败/错误，exit0；473份输入前后稳定，四开发门exit0；早期参数ID环境错误及有效RED均保留。Spec发现1项P2内容ID遗漏，修复后独立2项通过并关闭；Standards补审0待修。WorkBuddy初检无端点，用户提示后本轮连接成功，wb-1513e39d57a0只读4文件completed；其条件疑点经统筹源码/合成SQLite核实，未据猜测改产品。没有新依赖、真实法库/模型/云访问、GUI/冻结/安装器验证，已安装0.4.1不变。下一片显式本机检索与引用面板，之后完整上下文许可及4轮模型编排；不把旧一次文字许可默默扩权。[实测](testing/library-ledger/20261020/README.md)；[执行合同](plans/2026-10-20-library-ledger-execution.md)；[接线准备](plans/2026-10-20-library-b2-readiness.md)。

2026-10-20 CH-00B2产品提交ebeedd18785337d4948e9912167950bb736fe30e已正常同步GitHub；远端SHA与3,497文件递归树一致，仓库private，无分叉/开放PR。32个新增可达blob已知模式和禁止路径均0命中；[同步回执](testing/GITHUB-CH00B2-20261020.md)。

2026-10-20 CH-00B2检索内存切片完成：既有法库检索和对话adapter共用original_span，保留逐字符规范化及旧with_map契约，去掉为单个命中构建整篇坐标表。固定4c303c5基线、同一250,009字符合成CSV及索引代际，完整返回摘要相同；两条Python跟踪峰值中位数27,134,250→3,330,636、27,135,867→3,332,261字节（约-87.7%），未跟踪耗时81.49→88.14ms、171.48→181.69ms（约+8.15%/+5.95%），不代表RSS/整体提速/冷启动/安装包结论。最终关联首批183通过2项跳过，随后明确指定已有独立DuckDB1.5.6补跑原2项全通过，228输入与前批相同；分两批覆盖185不同用例，非单次185全过。项目pip check通过，新增安装0；四开发门exit0、228输入稳定；Spec9,880区间+两路径与Standards585字符串/60,113区间独立等价，无待修发现。WorkBuddy本轮状态无活动端点，未重复派发；无新依赖/schema/GUI/冻结/安装器/真实资料调用，0.4.1不变。CH-06B1持久引用/唯一回执/完整schema升级与备份已作设计复核但未实施，完整runner预算和聊天引用面板属于后续B2。[实测](testing/library-memory/20261020/README.md)；[本片计划](plans/2026-10-20-library-memory.md)；[下片预案](plans/2026-10-20-library-ledger.md)。

2026-10-20 CH-06A内部法库底座完成：独立adapter复用既有检索/原文/清洗/分段，最多8候选和1200字符，记录版本/索引代际/片段/精确字符映射重核；source_match仅record_quote_matched，registered_source_sha256是入库整源摘要，支持/适用仍unverified。固定两工具前后重核当前会话/角色/案件接待/工作区/草稿，文件I/O不占业务事务，不建新助手消息/运行/事件/模型任务。最终Windows合成关联341通过2旧DuckDB前提不足跳过、四开发门exit0、230输入稳定；双轴发现已修复/明确范围，剩余0。首轮336通过2跳过但输入变动使脚本exit1已保留，不能冒充最终稳定证据。WorkBuddy本轮status连通后wb-7d80d300ab52超时可能受理，未重派，无复核答案。无新依赖/schema/主程序接线；未GUI/冻结/安装器/真实法库/真实模型/云验证，0.4.1不变。产品提交bb5b42b已正常同步GitHub，远端SHA与3,467文件树一致，仓库仍private；[同步回执](testing/GITHUB-CH06A-20261020.md)。下一片CH-06B持久引用、固定事件回执/幂等/轮数与聊天原文面板、备份恢复。[实测](testing/library-adapter/20261020/README.md)；[实施记录](plans/2026-10-20-library-adapter.md)。

2026-10-20 CH-05D2同窗独立确认完成：主模型与TypeSafe独立接收方、用途、完整文字及预算；辅助默认未选/不可用，未选仍可继续Main。主先辅后、末异步身份检查保留双租约，外层末检查失败等待清理原后台的已闭合辅助许可。240桌面测试、四开发检查、Windows源码默认关闭6组（Main1/Jev0）、双选8组（Main2/Jev1）、冻结授权停用5组（generations0）均exit0；Spec/Standards无待修发现，WorkBuddy本轮指定4文件只读完成。7张实际截图核对中文长文、100/150/200%应用缩放及操作可达；不等同系统DPI/第二机。220后端相关仓库输入未变，复用D1exe，不重建安装器/不重跑历史Python全套。生产judgeBudget仍null，真实账户/费用/预算未落实，真实辅助仍关闭；安装版0.4.1及真实资料不变。产品提交ec695b1已正常同步GitHub，远端SHA及3,425文件树一致、仓库仍private；[同步回执](testing/GITHUB-CH05D2-20261020.md)。下一片CH-06固定钩子与可回查检索，持续解耦与资源测量。[证据](testing/jev-confirmation/20261020/README.md)。

2026-10-20 CH-05D1产品提交b2a4e31已正常同步GitHub；远端SHA及3,363文件递归树一致，仓库仍private。新增可达76个blob路径/已知敏感模式检查均0命中。README/TODO/执行记录与合成证据已同步；D2确认界面仍待，安装版0.4.1不变。[同步回执](testing/GITHUB-CH05D1-20261020.md)。

2026-10-20 CH-05D1后端接线完成：实际草稿→保存后完整请求许可、单槽未收尾保护、固定私有授权/撤权能力声明，以及同一Main任务的可选Jev预留/执行/取消；沿用原运行时、账本与队列，无新依赖/schema。201桌面测试、157/83/32三组后端目标及四开发门通过，分组不冒充单次全套；独立Spec/Standards关闭1项发布后到期墓碑缺口P2。Windows源码10组（Jev→Main各1合成回环POST、同run待核回执、重放重启不重发）与新冻结控制7组通过，构建/进程285仓库输入一致；冻结仅双授权/撤权并停用/拒发/重启，不称冻结供应商执行或全进程网络审计。新后端547文件96,267,372字节，较CH-05C增9,426字节，未测总体内存或冷启动。D2日常确认界面、真实账户/价目/预算、自动档案与整体交付仍待；0.4.1安装版、真实法库、未下载年份及阿里云不变。WorkBuddy两次busy/unknown，未派发。[实际证据](testing/jev-request/20261020/README.md)；[执行记录](plans/2026-10-20-jev-request-backend.md)。

2026-10-20 CH-05C产品提交38e185d已正常同步GitHub；远端SHA及3,299文件递归树一致，仓库仍private。上传前92个新增blob的禁止路径/已知敏感模式为0。见[本片同步回执](testing/GITHUB-CH05C-20261020.md)；此前各阶段历史“未推送”表述为当时记录，不代表当前仍未同步。

2026-10-20 CH-05C Jev原生配置生命周期完成工程验证：复用凭据/配置工厂和同一父子管道，固定TypeSafe密文身份、两个配置操作及独立能力声明；普通停用互不干扰，EOF/故障双清理，配置不授予policy、不联网。190桌面测试、119关联Python、四开发门均exit0；独立Spec/Standards无未关闭发现。实际Windows源码和新冻结后台各9组、各3次Electron启动通过，同一191输入前后稳定；配置ACK、PID/会话/草稿、原生/HTTP权限、100/150/200应用缩放、重启/崩溃、恢复副本禁配置均实测。原与恢复七表为0；源码httpx/httpx2 send计数0，冻结无全进程网络观测。恢复由host API制备，不冒称冻结维护过程。三个实机夹具失败轮保留：缩放0.5625像素取整及恢复页等待目标，产品权限未放宽。新后端较CH-05B增加2626字节、仍547文件；无新依赖/schema/队列，不称整体包体/RSS改善。所有本片测试进程已退出；WorkBuddy本轮busy/unknown未派发，独审由子智能体完成。安装版0.4.1、真实材料/法库/模型与云未动。TODO/README已更新，按授权正常提交并核对GitHub；下一片CH-05D独立具体许可与同一主任务内辅助阶段，不重复配置/账本。见[本片证据](testing/jev-native/20261020/README.md)、[实施交接](plans/2026-10-20-jev-native-implementation.md)。

2026-10-20 GitHub协作同步已完成首批远端核验：用户明确要求持续同步，新增根目录[TODO](../TODO.md)和[协作约定](../CONTRIBUTING.md)，更新README当前能力/限制及desktop设置说明，保存CH-05C/D架构交接（方案，尚未实现）。积累21提交及协作文档提交正常推送到792ba6036113e714cc5b9a6c3fb59bc846c1387f；远端私有状态、SHA和3,227文件递归树逐项一致。新增可达历史1,206 blobs及文档7 blobs检查禁止路径0，命中均为逐项核实的固定拒绝URL或其文档引用；独立文档/清单复核无必须修复项，46处链接存在。这里只完成同步与文档核对，未重跑产品测试、未实施Jev日常入口、未更新0.4.1。持衡fetch后仍8a0d640、0/0，旧5运行锁未加入。WorkBuddy本轮connected，但只读任务wb-e85628b2688a因不支持Grep取消，无审查答案、不算通过。原自动任务已加入每阶段更新TODO/README、获取协作者更新、正常push和远端核验的持续规则。最终收据随本文另行同步，见[本次记录](testing/GITHUB-UPLOAD-20261020.md)；下一工作为TODO中的CH-05C，保留原法库/真实账户/云端边界。

2026-10-20 CH-05B Jev独立调用账本后端切片完成工程验证：独立政策/预留/一次claim/回执/待核建议复用同一assistant_runs，新增三表和assistant-judge-v1，不建第二队列、不改主任务状态/供应商/预算。固定旧Main DDL，五历史版本升级、失败回滚和qxbak只读恢复保留；当前仅完整普通文字primary_intent，显式技能跳过，其他用途/附件尚未映射。独审发现已收回执在超时/取消时丢失P2，两分支已修，usage和请求ID保留、答案不采用、取消继续传播。最终703个不同关联Python全部通过、四开发门exit0，500输入稳定；Spec10及Standards3+1独立探针通过，无未关闭发现。实际Windows源码/新冻结后端各5组通过，221构建输入与EXE摘要一致；回环由host合成seed执行，子后端实际验证启动/恢复/备份，未冒称原生Jev已接。1条pytest报告格式警告和4条可选冻结导入警告保留。后端目录较CH-04I（含CH-05A+B）增加44,382字节、仍547文件；无新依赖，完整安装包/RSS/冷启动优化未完成。所有本片进程已结束，WorkBuddy本轮busy/unknown未派发；安装版0.4.1、真实材料/法库/模型账户、云及GitHub未动。下一片日常Jev配置、独立外发批准和现有主流程辅助阶段；跨重启供应商对账未实现，不重复账本/升级或历史测试。见[本片证据](testing/jev-ledger/20261020/README.md)、[执行及接线契约](plans/2026-10-20-jev-ledger.md)。

2026-10-20 CH-05A Jev薄提供器与纯路由完成工程验证：固定三用途问题、严格回执DTO/codec、延迟HTTP和显式技能优先独立成模块；复用已有httpx2，无新SDK/数据表/队列。默认关闭且无可信preflight时不读密钥/不载HTTP；preflight仍是下一片接现有权限、预算和持久claim的入口。修复固定选项/截止与路由一致性、响应media type、交替日志递归；main.py仅两行wraps兼容。最终367关联Python通过（新增154含其中）、489验证输入稳定、四开发门exit0；独立Spec36项与Standards4组通过，无未关闭发现。实际Windows源码/独立冻结协议探针各4组通过，各1回环POST、外部0，11明确构建输入与EXE相符；不是桌面后端/安装器。单模块3+3进程观察有少量新增开销，未测总体包体/RSS/启动，不冒称轻量化完成。初始codec夹具及Spec过严日志断言问题与真实产品RED分别保留。所有本片验证/构建结束，WorkBuddy本轮busy/unknown未派发。日常Jev设置、专门授权、费用队列接线/真实调用仍未完成，安装版0.4.1、真实材料/法库/云/GitHub未动。下一片CH-05B复用既有边界接线，保留完整诉求、作用域和待核状态，不重复本片测试或建第二队列。见[本片实测](testing/jev-adapter/20261020/README.md)、[实施记录](plans/2026-10-20-jev-provider.md)。

2026-10-20 CH-04I旧授权引用生命周期完成开发验证：历史意图只保留指纹和配置/授权代次，不再持有旧provider、密钥resolver和完整policy；有效重试不续期、撤权/替换/过期/重配置后不复活，已登记existing及在途回执保持。两个产品文件20增4删，无新依赖/数据表/队列/HTTP授权入口。先取得旧provider未释放的RED，最终168关联Python、50关联Node及四开发门均exit0，482验证输入稳定；32轮替换后只保留当前对象、停用后全部回收。独立Standards14及Spec14探针通过，无未关闭产品问题；独审最初网络钩子误拦Windows asyncio本机self-pipe的harness失败已保留并修复，仅改独立探针。实际Windows源码5组（1回环模型POST、四类记录各1、外部请求0）及新冻结后端5组（原生授权后停用、生成/模型记录均0）通过，212构建输入与实际EXE摘要相符。轻量墓碑仍保留，未测RSS/包体/启动总体，不冒称全部资源目标完成。Jev当前官方端点及SDK v0.7.5固定点已核对，保持jev-1.13.0并复用现有httpx2；仅CH-05准备，未实现提供器/队列接线或真实调用。WorkBuddy本轮仍busy/unknown，未派发；安装版0.4.1、真实材料/法库/云与GitHub未动。下一片按新协议笔记完成Jev独立薄提供器/纯路由，再接既有权限、费用和队列。见[实测及独立复核](testing/model-intent-lifetime/20261020/README.md)、[实施记录](plans/2026-10-20-model-intent-lifetime.md)和[Jev协议](plans/2026-10-20-jev-protocol-notes.md)。

2026-10-19 CH-04H 原生发送确认完成开发验证：当前已保存普通文字可经独立窗口核对完整内容、接收方、模型和单次预算，再沿原私有授权与生成队列登记；取消保留草稿，确认期间草稿/材料/登录或窗口变化拒绝旧请求，未知提交只查原ID。确认协调层与窗口独立于主入口，没有新队列/schema/依赖。最终152 Node、163关联Python/前端包装测试全通过、exit0，481输入稳定；独立15个原生探针、11个前端探针和3组驱动审计通过，无未关闭阻断。真实Windows Electron源后端5组：仅1回环POST、消息/attempt/receipt/output各1、历史刷新不重发、外部请求0；新冻结后端5组：实际批准后停用，生成POST及模型记录均0。212构建输入稳定，15冻结静态资源与最终源码匹配；四开发门通过。初始取消焦点滚动及提示不一致已修正；CDP关闭应答、httpx2网络计数遗漏和旧文案断言的失败均保留并复验。WorkBuddy仍busy/unknown，未派发。实际确认只涵盖普通文字，不代表Jev/自动档案/真实模型或生产完成；安装版0.4.1、真实材料/法库、云及GitHub未动。下一步沿既定CH计划接Jev与档案，保留固定权限与来源边界。见[本片实测](testing/native-send-confirmation/20261019/README.md)和[实施记录](plans/2026-10-19-native-send-confirmation.md)。

2026-10-19 CH-04G 日常主模型设置完成开发验证：原生设置新增固定模型选择、配置/切换/停用；可信凭据只经已有私有管道装配，保存不配置、配置不授权或联网。设置与返回保留同一后台、登录和对话草稿；备份/恢复仍停服，恢复副本禁配置，重启回到未配置。模型页面逻辑独立到 setup-model.js，setup.js 从98行缩至54行；main增加生命周期接线，新增独立 model-session，无新增依赖/schema，不声称本片包体/RSS下降。最终106项Node通过，0失败/跳过、exit0，470验证输入稳定；独立12探针+8导航回归通过（8项已含106，不相加）。真实Windows Electron源后端8组及复用CH-04F冻结后端8组均通过，各175输入稳定；212冻结构建输入及EXE摘要匹配，未重新构建安装器。系统保护合成密钥、100/150/200%缩放、PID/会话/草稿保持、后台停止、实际renderer崩溃、重启/备份后默认未配置均已测；0消息/attempt/receipt/output，源后端网络tripwire为0。独立发现renderer故障未停止旧配置P2已修复并实机复验；一次CDP测试驱动在故意崩溃后继续使用旧Page而失败，修正驱动并完整重测，未放松产品。四开发门通过，来源非生产批准提示保留。WorkBuddy本轮仍busy/unknown未派发。所有本片验证进程已结束，安装版0.4.1、真实材料/法库/模型/云/推送未动。下一片CH-04H具体发送的原生确认，沿既有完整basis和费用上限授权，再接Jev/自动档案；本片不能冒称日常发送已贯通。见[本片证据](testing/native-model-settings/20261019/README.md)与[实施记录](plans/2026-10-19-native-model-settings.md)。

2026-10-19 CH-04F 原生私有控制与单次文本授权完成开发验证：独立Node/Python控制模块复用自有父子管道，可信凭据消费、配置版本、当前会话/对话/草稿完整basis及单次预算已接线；主页面/IPC未新增配置或授权入口。生产桌面现在启动空注册表，不自动读取密钥或授权。最终406不同关联用例通过，0失败/错误/跳过，exit0，JUnit223.387秒，483输入稳定；Node73项通过（新增38含其中）。独立11 Python＋2实际Node/Python探针通过，维护修复另复核2正式用例，无残余阻断。实际Electron6组通过，系统保护合成凭据经管道及回环只发1POST、仅1attempt/receipt/output；新冻结后端4组＋既有维护适配器到EXE备份/恢复2组通过，212构建输入稳定，四开发门通过。关闭UTF8无换行限额、能力basis误显、Windows CRLF及维护退出锁问题；修复前405与旧冻结结果保留为中间轮，最终回归38363/构建22846均结束，无活动任务待等待。WorkBuddy本轮busy/unknown未派发。无新依赖/schema变化，不声称包体或RSS下降；未改安装版0.4.1、真实材料/法库/模型联网/云/推送。下一片日常原生设置与明确发送确认，沿本接口继续Jev和自动档案；旧意图引用释放作为后续小项，不得清空使撤销ID复活。见[本片证据](testing/native-model-control/20261019/README.md)与[接续契约](plans/2026-10-19-native-model-control.md)。

2026-10-19 CH-04E会话授权运行接口完成开发验证：新增独立注册表，以工作区/用户/登录会话绑定授权；每attempt只解析一次固定供应商/配置/授权，配置或撤权后不复活旧任务。复用原队列及费用账本，未claim失效记not_sent，已claim保留实际或未知回执并阻止过期候选；生产runtime仍为空，原生凭据管道及日常授权入口尚未接。最终331不同关联用例通过，0失败/错误/跳过、exit0、JUnit164.468秒，新增53项包含其中；472输入摘要稳定。独立8项复核通过、无阻断；新Windows冻结后端3组通过，210构建输入稳定，四开发门通过，4可选导入警告保留。首轮构建因registry补强期间输入变化被作废，不计通过；最终回归77559/构建84801均结束，无活动任务待等待。WorkBuddy本轮busy/unknown，未派发；未重测未改桌面、安装器或全套，无新增依赖/schema变更，不宣称包体/RSS下降。真实模型/安装版/法库/云/推送未动。下一片原生可信控制管道与明确发送授权，再接Jev及自动档案。见[本片证据](testing/session-model-runtime/20261019/README.md)和[接口契约](plans/2026-10-19-session-model-runtime.md)。

2026-10-19 CH-04D原生模型凭据入口完成开发版验证：新增独立存储/IPC模块，Windows系统保护下保存、替换、移除、重新检查和重启读取；只返回状态，保存不启用模型/授权/收费，生产runtime仍为空。35项Node桌面回归、1项实际备份排除凭据测试通过，均exit0；18份回归输入摘要稳定。实际开发Electron9组通过、11份产品输入一致，真实第二窗口及业务页面IPC拒绝、默认模型关闭、0消息/attempt/receipt/output；中文路径及100%/150%缩放截图核对。独立复核检查正常路径及同用户恶意文件竞态限制；默认/来源/依赖开发检查通过，不等于生产批准。WorkBuddy本轮重新连接并5Read，因未开放Glob取消，无审查结论、不自动重试。无新增运行依赖/应用数据库变更，不声称包体或启动占用下降；未改安装版0.4.1、真实法库、模型联网/云部署/推送。原生实测及回归全部结束，无本片活动任务待等待。下一片沿既有队列接主模型配置版本和每请求授权，不直接替换全局policy，再推进Jev/自动档案。见[本片证据](testing/native-model-credentials/20261019/README.md)和[实施边界](plans/2026-10-19-native-model-credentials.md)。

2026-10-19 CH-04C首页受控发送与历史回复切片完成工程验证：保存后的明确发送、未知结果只查原请求、等待中继续输入、按消息读取内部待核候选与原文定位已接线；生成状态/历史服务独立，app仅增加静态白名单，无新运行依赖。默认生产runtime仍为空，技能、附件模型处理、设置、Jev与自动档案不冒称接通。最终223不同关联用例通过，0失败/错误/跳过、exit0、JUnit132.292秒，348输入摘要一致；7前端包装与新增25历史项含其中，未重跑全套。最终真实浏览器11组、独立读取恢复3项、键盘/长文4组通过；独立复核关闭2个P2及修复中的额外读取回归。四开发门、新冻结EXE4组、实际开发Electron默认4组/合成5组通过，205构建输入一致；保留4条可选导入警告。WorkBuddy本轮任务wb-fd133d592937完成3Read源码复核，意见经主代理核对。session17537及所有本片构建/验证已结束，勿重复等待。未改安装版/真实材料/法库，无真实模型调用/推送/云部署。下一步主模型可信配置与授权入口，再沿CH-05—07接Jev、工具与档案。[本片证据](testing/chat-generation-home/20261019/README.md)、[汇总](testing/chat-generation-home/20261019/summary.json)、[接续安排](plans/2026-10-19-post-home-readiness.md)。

2026-10-19 CH-04B受控生成HTTP与生命周期切片完成工程验证：新任务管理器只调度本进程新提交的attempt，复用既有授权/预算/回执；能力查询、快速登记、当前权限读取及请求ID找回独立成模块，默认仍关闭。关停先收尾再释放数据库/目录锁，历史queued、重复请求与重启不补发。最终145个不同关联用例通过，0失败/错误/跳过、exit0、JUnit86.360秒，新增53项包含其中；351份输入摘要一致。本轮未重跑全套，不复用上轮2,350作为本轮数量。独立Spec初始7项及修后原反例1项、Standards6项通过，Unicode字节上限P2已关闭；开发四门、最终冻结后端3组及独立冻结合成HTTP5组通过，203构建输入一致。最终session29924已结束。WorkBuddy先busy且旧任务wait返回unknown，未重试/清状态；随后实际连接恢复，新任务wb-151ff422094a完成限定3文件只读复核，3次Read回执、0发现，主代理已核对启动恢复/事务/唯一约束。产品已本地提交eccea9a。安装版、真实资料和法库未动，真实模型调用0；首页发送/设置/Jev/自动档案仍待接。下一步首页消费，不重做已完成导入与本片回归。见[本片证据](testing/chat-generation-http/20261019/README.md)、[数值汇总](testing/chat-generation-http/20261019/summary.json)、[执行记录](plans/2026-10-19-generation-http-execution.md)。

2026-10-17 CH-04A主模型执行底座完成工程验收：明确消息授权、完整请求快照、单次claim、事务外传输、费用回执及内部待核候选已独立成模块，普通重启和qxbak恢复不补发。最终全套2,348通过／2独立DuckDB环境跳过，exit0、JUnit1,924.975秒；原两项补跑通过，逐项覆盖2,350个不同用例、未解决项0。451输入摘要全程一致，388个不同目标包含其中，不重复相加。四开发门、最终冻结Windows后端及独立冻结合成模型链通过，201构建输入一致，重放仅1次loopback POST；独立实证四项缺陷均修复闭合。原中止6904及补丁前冻结结果保留历史，最终3206已结束，不要等待或重跑。WorkBuddy当前无活动端点，未派发复核。页面发送／模型设置／Jev／自动档案仍未接通；安装版、真实资料与法库未动，没有真实模型调用。下一步按已复核的HTTP与首页消费准备接线，见[实测证据](testing/chat-model/20261017/README.md)、[数值汇总](testing/chat-model/20261017/summary.json)、[接线准备](plans/2026-10-17-main-model-http-readiness.md)。

2026-10-17 CH-03A 建案前 DOCX 收件切片完成工程验证：对话独立收件、不可变原件／解析／材料快照、原文面板和原生 qxbak 恢复贯通，无需暗建合同案件。最终单次完整回归 2,171 通过、0失败／错误／跳过、exit0、1,814.65秒；收集与JUnit逐项一致，426份源码／测试／配置摘要全程未变。159个不同定向用例均包含在全套内，不重复相加；真实浏览器11组、最终冻结Windows后端7组、实际开发Electron9组和四开发门通过。独立复核关闭迟到预览及备份路径别名问题，Standards／Spec无残余；旧中止回归94872单独留档，不计通过，最终session31938已结束，不要继续等待或重跑。原件、版本、权限和恢复只读保持；安装版／真实材料／法库未改，发送和主模型/Jev仍未接通。WorkBuddy本轮任务丢失，无复核回执。下一步依[已复核的主模型接线准备](plans/2026-10-17-main-model-readiness.md)推进CH-04首片；其余CH-03和CH-05至CH-11仍后续。见[本片实测](testing/chat-attachments/20261017/README.md)及[数值与摘要](testing/chat-attachments/20261017/summary.json)。

2026-10-17 CH-02A 首页草稿切片完成工程验证：独立页面模块及五个前端 ES 模块接通本机草稿、技能选择、历史分页、冲突核对和撤权清屏；无新增运行依赖。最终单次完整回归 2,094 通过、0 失败／错误／跳过、exit0、1,743.82秒，收集清单与 JUnit 逐项一致。18 页面＋40 关联＋2 前端包装包含在全套内，Node 28＋4 不另加；真实浏览器11组、修复探针4组、新冻结后端5组通过。实际 Electron 开发壳首页6组、原合同14项、新建接待10项、备份恢复10项及恢复草稿补充1组通过；独立复核4个不同缺陷已关闭，开发四门通过。初始397文件中393份未变，4份手工CJS入口兼容修改及新增1份CJS单独验证，产品／Python运行输入未变；session84247已结束，不再等待或重跑。已安装0.4.1及真实资料未动；发送、附件、主模型/Jev、自动档案和新安装器未接通。下一步按[经复核的 CH-03 准备](plans/2026-10-17-conversation-materials-readiness.md)做 DOCX 建案前收件、原文回查及原生 qxbak 完整恢复，不暗建合同案件。见[本片证据](testing/chat-home/20261017/README.md)。

2026-10-17 首页读取前提完成：对话HTTP默认50条、同对话UUID向前游标、最近任务摘要与原请求ID找回；创建重放／草稿保存采用有界响应，旧服务默认兼容。最终218个不同关联用例通过（新增32含其中），0失败／错误／跳过；新Windows冻结后端51条合成消息、重启同键去重、加密备份及恢复读禁写4组通过，四开发门与独立双轴复核通过。WorkBuddy本轮3文件只读复核实际完成，rowid未来逻辑重建边界已记录；当前文件备份实测不等于阿里云迁移。未重跑全套，上轮2042不计为本轮；未改安装版／真实数据，未增加模型／首页／附件。下一步CH-02页面接线，见[本轮证据](testing/chat-history/20261017/README.md)。

2026-10-17 CH-01接口切片完成工程验证：在e7618bb之上新增独立HTTP、列表／取消／事件续读，app仅增加两行装配；短事务认证、当前归属、草稿版本、幂等和恢复只读保持。97服务目标及补强8项、最终10HTTP、新冻结EXE6组及四开发门通过；独立复核1项轮询期限问题已有效RED→修复→关闭，最终0未关闭问题。最终单次全量2,042通过、0失败／错误／跳过、exit0、1,694.84秒；JUnit逐项去重一致，387份运行期源码／测试／配置摘要未变，目标复验不重复相加。此前主动中止批次单列不计通过；最终回归已结束，不要继续等待或重跑。WorkBuddy本轮限定3文件只读复核实际完成，不替代运行验证。当前仍不执行主模型或Jev，没有首页、聊天附件、自动档案或新安装器，真实资料和安装版未动。Deep Chat实验保留原生输入路线；Markdown固定制品13组合成检查通过，未纳入产品，表格可读性及桌面链接仍需接线验证。下一步补消息分页／重开任务定位，再做CH-02首页。见[接口证据](testing/chat-api/20261017/README.md)、[下一切片检查](plans/2026-10-17-chat-home-readiness.md)。

2026-10-17 CH-01首个存储切片完成目标验收：新增独立assistant四表及五服务，保留原话、作用域和版本，当前权限／幂等／并发／恢复写禁有实测；发送仅登记queued，尚不执行模型。固定pre-intake→intake-v1→assistant-v1升级，分步备份回执及中断恢复；旧qxbak/cnbak先验证原档再升级隔离副本，未完成对话任务阻断。最终293目标通过／0失败错误跳过，新Windows冻结后端8组实测、四开发门及双轴复核通过；WorkBuddy本轮限定只读复核实际完成，意见经核对取舍。未重跑全套、制作安装器或改动现有安装／真实数据；首页、HTTP／执行器、附件和Jev仍待后续。见[本轮证据](testing/chat-storage/20261017/README.md)、[复核意见](testing/chat-storage/20261017/review.md)。下一步先接薄HTTP和任务边界，再贯通首页与建案前附件，不重复导入法库。

2026-10-17 CH-00A公共模块抽离完成目标验收：存储初始化移至storage_bootstrap，请求认证/同源/CSRF/严格JSON移至request_context，旧app导入别名保留；app净减少65行，原schema两种摘要一致。存储69项与请求99项实际通过，去重167项，无失败/错误/跳过；新冻结EXE完成合成初始化登录、重启、备份、隔离恢复与只读拒写5组检查，双轴复核0问题、开发检查通过。本轮未重跑全套或制作新安装器；前一轻量化提交为7b58b92。CH-01仍未实现，已查明直接增加聊天表会破坏旧qxbak结构识别，下一阶段先做固定版本参考和有序迁移，再接对话存储；实际安装及真实数据不变。见[本轮证据](testing/chat-first/20261017/README.md)、[迁移复核](plans/chat-first-schema-migration-notes.md)。

2026-10-17 CH-00B首批轻量化已完成验证：PDF依赖按需加载，关联144项、Node4项、合成桌面14项及四种语言启动通过；完整回归1,903通过/2跳过，既有独立DuckDB环境补跑2项通过，1,905个不同用例逐项覆盖、无未解决失败。schema/default/来源/依赖开发检查退出0，独立双轴复核0问题。目录包减少48,880,941字节（46.62 MiB），仅移除52份不使用语言资源，538份后端文件一致；此数字不是压缩安装器减量。原安装版未替换，未生成新安装器。下一步先解耦升级/备份公共边界，再接CH-01对话持久化；聊天/Jev/自动档案仍未完成。见[阶段证据](testing/chat-first/20261016/README.md)及[逐项回归汇总](testing/chat-first/20261016/regression-summary.json)。

2026-10-16 对话式前端与解耦轻量化阶段已由用户明确恢复无人值守推进。基于用户v2.0材料完成v2.1规格修订及两项独立文档复核，用户确认代码职责与安装/启动占用都优先，Enter发送、Shift+Enter换行并保护中文选字。现先实施CH-00A/00B的边界记录、PDF按需加载与Electron语言资源减量；新聊天、Jev、自动档案、迁移与持衡接口仍按后续CH任务推进，不能称已经完成。原有小时接续已恢复ACTIVE；应用持续目标卡片工具仍读为paused，未伪称已修改该卡片。保留现有分支和安装程序，开发只用合成材料，不启用真实材料外发。见[执行记录](plans/2026-10-16-chat-first-execution.md)和[修订规格](plans/chat-first-architecture-v2.1.md)。

2026-10-16 GitHub同步及持衡安装接续：主工作台0.4.1源码、资料库、备份、接待和Word修复已同步至既有私有仓库；持衡修复已同步至私有仓库`codex/windows-native-continuation`，保留其`main`。持衡新候选基于`ccadffa`，455外层载荷及590公共资料载荷核对通过，新中文目录核心安装成功；安装内完整632项为625通过/7明确跳过，JS12通过，3个独立进程模拟演练保留11回合。新包SHA256为`7ef614242853903f6130516eafcdd6c53defaf69d03658de56a39db7b3703b88`，根代理独立复核一致。仅核心安装，未激活宿主、自动启动、商业网站登录或在线检索，非系统重启验收；原失败包及安装目录保留。真实材料、数据库和安装包不进入GitHub源码提交。见[上传记录](testing/GITHUB-UPLOAD-20261016.md)；下方持衡“继续推进”为较早阶段状态。

2026-10-16 Word样式读取及旧记录衔接已完成：完整1,901项通过、0失败/错误/跳过，新增75项目标、Node4及独立双轴复核通过。0.4.1已实装，旧数据升级8项、常规合同14项通过，两份Word共7页本机核对；22份安装界面资源与源码字节一致。复用既有解析库、任务、权限和追加式存储；未知可见性继续待核，重读需明确操作，原件和历史保留、事实回待确认、旧成果失效。真实案件未自动重读，真实模型仍关闭；新版已打开登录页。WorkBuddy本轮实际连通并完成仅公开GitHub/微软资料研究，报告经独立纠正。持衡Windows离线与深路径传输修复已本地提交0f9c259/ccadffa，最终625通过/7明确跳过，公开590载荷深路径往返保持，新的源码一致候选及隔离安装继续推进。安装包仍未签名；Word有一处非阻断表头分页瑕疵，账号设备/在线更新/阿里云等尚未完成。见[本轮证据](testing/DOCX-COMPATIBILITY-20261016.md)、[数值汇总](testing/docx-compat-20261016/summary.json)及[使用说明](../desktop/README.md)。

2026-10-16 本机完整备份与恢复核对完成：0.4.0已实装，原生菜单暂停自有服务、锁定工作区并创建经复验的口令加密归档；原件、历史导出、接待版本及审计保留。恢复到独立目录，旧会话撤销、任务及当前批准隔离，支持重新登录核对原件/历史Word/接待并返回原工作区。明文临时文件留在源工作区，NTFS跨卷密文发布与失败不覆盖实测通过。安装版合同14项、备份恢复10项、法库生命周期8项通过；完整回归1823通过/2跳过，加试点补跑2及最终引擎15后，1826个不同用例逐项覆盖当前清单，0未解决失败；Node4与开发门通过。独立双轴3个问题修复闭合。恢复当前仅只读核对，未做可写灾备切换；归档限2GiB，安装包未签名。跨模块材料、其余业务、账号设备/更新和阿里云仍后续。见[本批实测](testing/WORKSPACE-BACKUP-20261016.md)、[数值证据](testing/workspace-backup-20261016/summary.json)和[使用说明](../desktop/README.md)。

2026-10-16 统一工作区及获案接待首版完成：0.3.0 已在本机安装，复用既有合同引擎。咨询、追问、材料状态、跟进、不可改历史、分受众复制/Word与原子转案贯通；0.2.0合成工作区升级前自动保存数据库快照，升级/中断恢复保持结构校验，原账户/案件及2份protected文件保留。安装版升级接待11项、新建接待10项、合同链14项、法律库及异常生命周期8项均通过（共同项不重复相加）；369个不同Python关联测试、4个Node测试及开发检查通过，未重跑全套。两类Word各1页本机Word/PDFium核对，独立双轴复核2个不同缺陷均关闭。完整本机材料备份/恢复、跨模块附件、其余业务、账户/更新及云端仍为后续；WorkBuddy当前未连通。见[使用说明](../desktop/README.md)、[本批实测](testing/WORKSPACE-INTAKE-20261016.md)和[数值证据](testing/workspace-intake-20261016/summary.json)。

2026-10-16 WIN02 Windows 本机验证版完成：复用当前合同工程，Electron 44.8.0 承载既有页面并封装 Python 3.12.14。NSIS 0.2.0 安装包已在本机中文带空格目录安装，登录、合成 DOCX 导入、原文、候选处置、Word 下载及重启保留资料 14 项通过；资料库故障恢复 3 项、全量库连接及吉林原文/案例检索与异常进程恢复 8 项通过。同版本重装后合成账户、案件仍可读取；用户数据独立于安装目录。225 个不重复 Python 关联测试、3 个 Node 单测及开发检查通过；未重跑全仓库完整测试。独立复核 4 个 P2 已修复并复验关闭。安装包未签名，PDF.js/OCR 完整资产、邀请/验证码/设备管理、在线升级、统一业务界面与阿里云仍属后续阶段；本次不等于完整应用或生产完成。见[安装使用与重建](../desktop/README.md)、[实际验收](testing/WINDOWS-DESKTOP-20261016.md)和[产物与数值汇总](testing/windows-desktop-20261016/summary.json)。本日 WorkBuddy 专用会话无活动端点，未将历史成功冒称当前连通。

本地资料库本阶段工程与本机数据验收已完成，见[逐项清单](testing/LOCAL-LIBRARY-COMPLETION-AUDIT.md)和[汇总证据](testing/local-library-20261015/full-completion-summary.json)。保留17,184法规文件的来源别名，形成17,182内容记录、686,718片段；2025的3,837,307案例来源记录全部可检索。3,854,489资料及686,718片段逐条ID/版本/位置映射无缺失、错配；40份已知身份及正文位置、另26份跨13CSV中末段原文对照均通过。全量112HTTP请求全部ready，十账户50请求P95约0.270秒；48,265,475,051字节核心资料备份至独立中文目录并完成摘要、数据库完整性、原文及版本恢复验证，exit0。首轮失败报告保留，诊断修复后验收通过。当前62资料库目标、69入口目标及开发检查通过；1776完整回归属于较早版本，未重复冒称。`启动法律资料库.cmd`是源码环境入口，尚非独立安装包；法律来源/效力仍待人工核验，阿里云和1985—2024数据为后续阶段。下方较早记录按其当时状态保留。

2026-10-15无人值守接续（仍在推进）：17,184份法规已导入，保留17,182个唯一内容记录和686,718个原文片段，失败0；旧试点10,000条全部比对接续、映射失败0。2025全量13文件、3,837,307条已续导完成，失败0，耗时1111.344秒；全量新索引仍在构建，页面覆盖仍为已验收的十万案例加法规，共117,182份资料。十万40份实际资料身份及正文位置核对通过，含17份吉林资料；十客户端HTTP复测50请求P95为0.375秒，首轮单次超时保留，未证明物理冷缓存性能。新全量索引实际强制中断后旧索引正常可查，同一新代际已从检查点继续。当前源码完整工程回归1776通过、0失败/错误/跳过；51资料库目标和schema/default/来源及依赖开发检查也通过。补强后的全量质量验收已完成，13案例文件及17184法规原件摘要、来源集合、目录首尾指纹一致，失败0；全量检索性能及异目录恢复尚未完成。详见[实际验收](testing/LOCAL-LIBRARY-ACCEPTANCE-20261014.md)、[工程证据](testing/LOCAL-LIBRARY-ENGINEERING-20261014.md)、[操作说明](LOCAL_LEGAL_LIBRARY.md)。以下较早记录保留为历史。

2026-10-14最新优先级：按用户要求先建设本地案例与法规资料库的清洗、索引和可核对检索，桌面封装后移，后续以认证接口迁移阿里云。1985—2024年数据在百度网盘尚未下载。本轮只读完整扫描13个2025 CSV：3,837,307条、16,452,507,459字节，解析完成、列数错误0、空正文0，60,826条文书类型为字面缺失标记；不是去重后案件数或正文完整性验收。法规17,184份、290,566,898字节，逐文件SHA256清单已保存在忽略目录；16,751份未附URL、1,641份零宽/BOM、2组完全相同内容、49组同名候选。WorkBuddy研究任务实际完成，统筹复核修正过强技术判断。已写[资料库设计草案](superpowers/specs/2026-10-14-local-legal-library-design.md)和[盘点证据](testing/LOCAL-LIBRARY-PREFLIGHT-20261014.md)；清洗、正式索引、全量导入、检索服务和云端迁移尚未实施，待书面设计确认。原件及既有一万条试点未改动，未上传资料、未下载其他年份。下条Windows预检为本日较早记录，执行顺序以本条及更新后的统一口径为准。

2026-10-14统一Windows应用接续：当前Win10 x64、原目录及分支/HEAD27fd2bb已核对；本机WorkBuddy既有桥完成聊天合成探针1轮和注册入口integration_test.py --registered三轮，Read/Write/Edit/WebSearch/WebFetch事件及落盘内容独立复核通过，脚本退出0。商业法律连接器、安装包、取消和第二台机器未验。F盘13CSV共16,452,507,459字节，既有DuckDB只读复核10,000来源记录、吉林86条，无重导；用户明确首批地方法规吉林省，两官方样例入口本机取得HTTP200，仍未核验全文/效力。整合方向为Harness交互参考、Impeccable工作界面主导、Taste辅助，Electron先验证；不合并重写三个工程。现有8767登录请求本轮未成功，未改真实工作区。仅记录与研究，未改业务/全局桥配置、未制作安装包、未重跑产品回归。见[统一执行口径](plans/2026-10-14-windows-unification.md)、[本机实测](testing/WINDOWS-WORKBUDDY-20261014.md)。

2026-10-13 本机材料增量：用户已选择优先完成本机真实合同工作稿。持久本机入口现可新建“本机材料工作稿”，逐份确认有权处理后导入 DOCX，人工登记事实、核对意见并导出 Word；来源标为本机人工。真实模型、QCC、插件选案和正式签发继续关闭。本机案件不进入测试备份；真实材料的备份恢复仍未实现。详见[操作说明](LOCAL_WORKBENCH.md)及[本轮验证](testing/LOCAL-MATERIALS-20261013.md)。完整回归1723项通过；其后启动提示文案和源绑定复验159项通过，Word共10页已验。持久工作台8767已启动，登录页HTTP200。下列较早日期记录保留为历史。

2026-10-13项目交接：已接手原“合同审查”聊天对应目录，私有 GitHub 仓库 `Qiu-Shu/qx-contract-workbench` 的业务历史由 `293f133` 续传至 `6c4a1ad`，43 提交完整上传，原分支及历史保留。新增[项目说明](PROJECT_OVERVIEW.md)、[交接文档](HANDOVER.md)与[上传核验](testing/GITHUB-HANDOVER-20261013.md)，纳入已有[真实使用差距](plans/2026-10-12-real-use-gap.md)。本轮159项目标与来源检查通过（15.40秒、退出0），源绑定通过，13来源开发门通过且生产批准警告保留；历史1758 blob路径/秘密模式检查无未解释命中。未改业务，未重跑全套/OCR/Word/浏览器，未开放真实材料、模型、QCC或生产。

2026-10-12本机使用修复：按用户要求首次设置及添加账户密码改为6–12位，已有账户密码继续有效；密码不一致/长度输入错误改为固定可操作提示，未知异常不回显。有效RED4失败4通过后最终115目标及安全/源绑定关联通过（14.91秒，退出0），121文件绑定通过。全套/OCR/Word未重跑。用户已创建本机工作区，服务被控制台中断后需重启，网页就绪须另测，未声称生产完成。[验证记录](testing/LOCAL-password-range-20261012.md)。

2026-10-11 QX08第二工程增量：新制式任务临时目录正常/异常结束后受控清理，先确认隔离进程归零及权限撤销；路径/软硬链接/目录联接拒绝，清理失败或残留先阻断后续OCR。256项/128MiB为轮询软预算，运行前256MiB磁盘检查不是硬配额。原件/候选/审计和历史目录保留。初始/残留/独审均保留RED，独审共同发现1个授予异常漏撤销P2已修复复核，最终91目标通过；21新增场景纳入完整1695 passed、退出0、1344.219秒、0失败/错误/跳过，清单/JUnit一致且源摘要未变。真实本机虚构OCR本轮2次返回，其中最终源码1次20.783秒，复制22,138,943字节模型后目录已移除，历史入口名称清单一致；不算冷/热或质量验收。121文件绑定通过，旧常驻服务未重启。PDF全过程隔离、系统性性能/峰值、硬磁盘配额及历史目录治理仍待；真实模型/QCC/材料产品准入/签发/生产边界不变。[本批证据](testing/QX08-OCR-CLEANUP-20261011.md)。

2026-10-11 QX08第一工程增量：位图和PDF两入口统一先取得线程/Windows跨进程准入，再完整核验、渲染与隔离推理；繁忙直接返回OCR_BUSY，失败后释放。初始RED1失败、目标70通过（9个新增准入场景）；单次完整1674 passed、退出0、1327.703秒，0失败/错误/跳过，清单/JUnit一致且执行期源码摘要未变。双轴独审均0问题，120文件源绑定通过。1页独立虚构PDF实际OCR返回、AppContainer有效，总24.769秒，其中完整核验13.706秒、隔离运行10.989秒；忙碌竞争零核验/渲染。单次观察不等于冷/热基准或峰值验证；22,138,943字节模型副本仍保留。副本治理、系统性性能及PDF全过程隔离仍待完成，旧常驻工作台/插件未重启，真实模型/QCC/材料产品准入/签发/生产边界不变。[本批证据](testing/QX08-OCR-ADMISSION-20261011.md)。

2026-10-11 QX07工程增量：保留历史v1字段39/48，新增金额数值/符号/单位、冲突重复与分框检查及原始/去空白全文字符错误。旧48输出重评分v2严格字段31/48、去空白全文31/48（79/1527字符错误），本轮无开发集模型调用；新6页虚构留出实际6返回、5/6严格字段及全文一致（3/247字符错误），遮挡页失败保留。8审计输入期望已验证，34新增测试纳入单次全套1665 passed、退出0、1337.047秒，0失败/错误/跳过；清单与JUnit一致，源码/脚本/配置执行前后摘要一致。双轴独审金额精度与证据计数问题均修复复查，120文件入口绑定通过。QX08繁忙前资产核验已另存待修RED（无模型调用），未混入本批通过。旧常驻工作台/插件未重启；QX05多引用/法律批准、QX06通用推理与法律质量、QX08–QX10余项及真实模型/QCC/材料产品准入/签发/生产边界仍未完成或受限。[本批证据](testing/QX07-OCR-SCORING-20261011.md)。

2026-10-10 QX06工程增量：内部导出保存制品hash绑定的有效全文，逐位置对照源基线与实际导出接受全部修订的文字，保留表格、多文件、历史修订和未读部件限制；新增数值/期限/引用及旧值线索、五维律师复审与工作稿确认门。法律已核对需QX05可消费核验链，待核不会包装完成，旧复审/确认不能继承新状态。新增14项纳入单次全套1631 passed、退出0、1306.468秒，0失败/错误/跳过；清单与JUnit一致，src/tests/plugins/schemas执行期间未变。双轴独审两项兼容/水印问题已修复复查，最终桌面/手机浏览器通过，119文件源绑定通过。旧常驻工作台/插件未重启。QX05多引用与法律批准、QX06通用推理及律师质量验收、QX07–QX10余项仍待完成，真实模型/QCC/材料产品准入/签发/生产边界不变。[本批证据](testing/QX06-EFFECTIVE-TEXT-20261010.md)。

2026-10-10 QX05工程增量：本案法源原文登记、游标分页、逐条支持/适用核对及本案谈判标准已接入律师处置与草案导出；真实性由后端当前核验链生成，与支持/适用分别展示。复用既有表、历史和失效机制，无新依赖。最终18目标通过、两种模式浏览器登记到客户稿通过；双轴审阅发现的历史状态误显/100条截断已修复复验。单次全套1617 passed、退出0、1189.719秒，0失败/错误/跳过；清单与JUnit一致、执行期间源码未变。118文件源绑定通过，旧常驻工作台/插件未重启。完整QX05的多引用覆盖、规则/客户政策批准与律师法律核验，以及QX06–QX10余项仍待完成；真实模型/QCC/材料产品准入/签发/生产边界不变。[本批证据](testing/QX05-BASIS-20261010.md)。

2026-10-10审计整改首批：QX01撤销待发布授权、QX02 DOCX颜色来源门与独立段落核对、QX03当前12样本备份恢复、QX04提交未知结果与返回前到期检查已实施；QX09仅去重测试和当前能力索引。1599项按清单分段执行并关闭失败：首轮1271通过后报告器中断，续跑327通过1旧来源断言失败，最终相关80通过；逐项唯一1599通过，不称单次全套成功。双轴独审3项已修复复验；浏览器新虚构库来源核对、12份逐份恢复及STDIO未知结果均实际验证。117源文件绑定通过；常驻工作台/插件未重启验收，QX05–QX08/QX09余项/QX10未完成，真实模型/QCC/真实材料产品准入/签发/生产边界不变。[本批实际证据](testing/AUDIT-QX01-04-20261010.md)；[当前能力](CURRENT_CAPABILITIES.md)。

2026-10-10独立审计回件核验：当前718c3fb未改业务；报告两项P1（待发布授权撤销失效、DOCX白字金额来源门缺口）及A03备份登记/A04未知提交语义已在本机虚构案复现。7探针7失败、0setup错误，含O01在途到期语义观察，均待修而非PASS；A05评分盲区/A06资源前置/A07重复测试亦核实。外部271现有回归仅读取与去重，不称本机重跑。原件已保全，源绑定116项未变；真实模型/QCC/材料产品准入/签发/生产仍受限。下一步优先QX01–QX04，保留现有架构和有效代码。[回件核验及整改顺序](audit/2026-10-10-audit-return.md)。

2026-10-09 OCR增量：仅在识别输入加入对比度增强，原PDF/预览/坐标/旧候选保持。48页输入逐页比对，32页字节相同未重识别，16变化页实际OCR全部字段命中，新增恢复29/32两页、退化0；综合历史观察37/48→39/48，并非全48重跑。倾斜第9页及8遮挡金额页仍缺项。有效RED2失败23通过→25通过，86关联及69入口通过；独审25+8通过，无阻断问题。原件/资产/worker五文件保全，116文件源绑定已更新。全套/浏览器/Word/峰值内存未重跑或未测，真实模型/QCC/材料产品准入/签发/生产保持关闭或阻断。[实际证据](testing/OCR-contrast-20261009.md)。

2026-10-09当前聊天接入验收：本地插件0.1.5已物化安装，当前Codex聊天4工具可调用；本轮8次原生调用为5成功、3预期拒绝，实际完成虚构选案→候选落库→相同输入重放→不同内容拒绝→撤销后读写拒绝。候选仅1条且先待律师处置；虚构测试角色处置后下载40,438字节工作稿，来源未核验标记保留。临时凭据目录已清除，服务exit0，原8766与真实材料未触碰。业务代码/依赖无变更，全套/48页OCR/Word未重跑。关闭下面历史记录的“父聊天仍旧两工具拒绝”缺口；网页ChatGPT、真实模型/QCC、真实材料产品准入及生产仍未完成或阻断。[实际证据](testing/PLUGIN-native-20261009.md)。

2026-10-09项目增量：新增单独明确授权的一轮插件候选提交，默认只读保持；来源local_plugin_unverified贯穿候选、律师处置和导出，模型身份/推理未核验，工作台真实模型/QCC为0。复用既有表与流程，无新增依赖。58目标、最终90入口/候选及浏览器1通过；大回归270通过1旧标签失败已精确复验修复；独审两P2及两个并发残余均有效RED→最终8通过，另13手工/原生红线旅程通过（重叠不相加）。源0.1.5/4工具/116文件绑定通过，父聊天仍旧2工具拒绝；网页ChatGPT、真实调用、签发、生产继续未完成或阻断，全套/48页OCR/Word未重跑。[实际记录](testing/PLUGIN-candidates-20261009.md)；[使用说明](LOCAL_WORKBENCH.md)。

2026-10-09项目增量：默认持久工作台新增明确同意后的15分钟选案只读连接，MCP源0.1.4增加无参read_selected_case；当前会话/角色/版本/原件/来源后端重验，重启/注销/撤权/恢复/到期失效，不新增数据库表。最终57目标、111较早关联、196MCP回归、71最终入口/模板均通过（重叠不相加）；独审两P2实际RED→修复14复验；真实TCP/STDIO及桌面/窄屏选择撤销已验，浏览器过早点选问题修复。116源文件绑定更新，依赖新增0。父旧聊天仍拒绝且未暴露第三工具，网页ChatGPT/候选自动写回/真实模型/QCC/签发/生产仍未完成或阻断；未重跑全套/48页OCR/Word。[使用说明](LOCAL_WORKBENCH.md)；[实际记录](testing/CASE-bridge-20261009.md)。

2026-10-09项目开发增量：修复聊天turn元数据被离线插件误拒绝，214关联通过，新增2整体容量边界及独审闭合；新加载独审会话原生两工具成功，父旧活动turn仍报原错，不能称父会话/网页ChatGPT已恢复。新增持久本机入口与双击启动：自设账户、重开保留案件/原件/会话，无公共默认密码；空库/缺表/换库先只读拒绝，OS锁覆盖实际worker寿命。最终19目标、39关联（含较早18）、独审41 assisted回归及两P2有效RED→修复复验。114文件源绑定已更新；未重跑全套/48页OCR/Word，真实材料/模型/QCC/签发/生产继续关闭或阻断。[启动说明](LOCAL_WORKBENCH.md)；[实际记录](testing/LOCAL-workbench-20261009.md)。

2026-10-09客户稿增量：读取范围的连续页号合并、已知扫描页/OCR旧状态改中文，未知诊断和原件SHA保留，内部稿原始清单及快照不变。有效RED6失败2通过→目标8通过；关联121通过（含8）、入口69通过，唯一独审0新增问题。虚构案件真实导出/下载及Word客户3页（旧4）+内部4页共7页复验通过；旧稿字节与下载不变。依赖检查通过，本轮新增安装0。全套/48页OCR未重跑，真实模型/QCC/法律验收/生产仍关闭或阻断。[实际记录](testing/CLIENT-readability-20261009.md)。

2026-10-09 CodeGraph增量：固定1.6.2官方Windows包摘要核对后独立安装，全局STDIO配置和按任务自动使用规则已写入；遥测及更新检查关闭。当前仓库170代码文件（src90/tests72/scripts8）、3622节点/11881边，排除资料及缓存，索引不入Git。合成跨文件查询、排除项通过；变更首查图短暂过期，稍后无手工sync即出现新函数图节点、pending0。独立MCP发现1个codegraph_explore并跨项目查询成功；本轮宿主已自动加载，当前聊天原生查询validate_cases成功，无需再重启。业务源码/依赖和生产状态不变。见[CodeGraph实际记录](tools/CODEGRAPH-20261009.md)。

2026-10-09版式增量：上一轮实际下载的人工转录稿、OCR关联金额稿已用本机Word 16.0.20430只读渲染，各4页共8页逐页检查；无可见裁切/重叠/中文缺字/表格断裂，每页草案页眉页脚保留。两原DOCX字节未变；每份34正文段、38表格单元格在PDF完整保留。仅关闭这两份稿的Word视觉缺口，不扩大到所有模板或真实法律验收。业务代码/依赖未改，无新业务pytest或OCR批次。[实际记录](testing/OCR-word-layout-20261009.md)。

2026-10-09工具增量：依用户要求本机安装Windows-MCP0.8.7、bb-browser0.14.2、Ponytail/Impeccable/Taste四技能，并复用既有Scrapling0.4.15；全局按任务自动选择规则已写入。Windows独立MCP握手/19工具/只读显示信息通过，重启后当前聊天已发现19工具并原生调用DisplayInventory成功；bb-browser发布包不支持README所示--mcp，已采用CLI，合成浏览器→Scrapling提取通过；Scrapling4/4通过。业务源码/依赖不变，不改变真实模型/QCC/签发与生产状态，未重跑业务全套。实际命令、失败及安装范围见[工具记录](tools/REUSE-SUITE-20261009.md)。

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
