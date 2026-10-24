# D2e：对话页的本机合成收件授权入口

基线1ddf55a；沿当前分支保留AGENTS用户改动。先将D2d授权能力变成可见、可操作的现有对话页流程，再做跨目标generation；本片仍拒绝跨目标/转案。复用登录、CSRF/同源、不可变grant和合成TaskDraft架构；无新schema/依赖/真实微信/模型/发送。

## 后端契约

domain.py追加WeixinConversationAuthorizationView：mode Literal['synthetic']='synthetic'，state Literal['unbound','current','refresh_required','target_changed','revoked','archived','restored_blocked']，current_scope ScopeSnapshot，authorized_scope ScopeSnapshot|None，grant_revision严格非负整数，scope_sha256 SHA256|None。未绑定时authorized_scope/hash为None且revision0；绑定时完整并核scope摘要。DTO只在domain.py。响应不暴露bot/peer/account标识、授权理由、合同正文或密钥。

新增weixin_inbox/conversation.py读当前对话授权投影：使用实际principal/owner/workspace及_owned的当前对象权限，通过现有task binding按conversation定位唯一mapping（不创建binding/account）；当前会话归档、映射/账号撤权、restore fence只显示阻断态，其他当前ACL或案件归档拒绝读取。最新grant通过D2d helper核验；state current必须scope完全相同，refresh_required必须五目标身份不变、input/material单调增长且精确当前scope；其他变化target_changed。GET不推进游标、不新增grant/任务/模型run。未绑定态也是实际查询结果，不能宣称微信已连接。

GET /api/assistant/conversations/{cid}/weixin-authorization →上述View。

POST /api/assistant/conversations/{cid}/weixin-authorization/refresh →WeixinPeerScopeGrant，body原WeixinPeerRefreshInput。先同源/CSRF/当前对象授权和restore fence，再解析有界JSON；之后由conversation再次解析映射并复用accounts.refresh_synthetic_peer（内部独立BEGIN IMMEDIATE），不得信任caller mapping/account/actor。CID→mapping不可变关系和业务服务再核权限，不能用旧GET快照授权。允许同request幂等服务语义，不自动重发。

GET /api/assistant/conversations/{cid}/weixin-authorization/refreshes/by-request/{request_id} →grant|None；当前CID权限+mapping归属+accounts.find_peer_scope_grant再核，恢复副本可查，未绑定可返回None。未知结果只能查询，不自动POST。所有入口通过现有app注册与静态allowlist，无公开微信poll/dispatch/账号创建写端点。

真实恢复middleware只精确放行上述两个GET读路径（is_weixin_authorization_read_path），POST继续隔离；不能只在普通app夹具上验restore flag。无mapping但归档/恢复时允许阻断态的authorized_scope/hash均None、revision0，不编造绑定。状态优先恢复隔离→对话归档→账号/peer撤权→未绑定→scope分类。

## 现有对话页

模拟合同任务卡内新增一行“微信收件授权 · 离线测试”，复用现有字体/颜色/quiet/text button；不改框架、总布局或动效。不显示技术ID/哈希/费用模型细节。未绑定明确“本对话尚未绑定本机合成收件；真实微信未接通”。只有refresh_required且本地非只读、非busy/dirty/materialAction/冲突时显示可操作“更新本机授权”。授权范围清楚限定“同一目标的输入和材料版本”，点击才POST，理由使用固定“对话页显式更新同目标输入和材料授权”。成功只按真实回执+重新GET确认显示，不能说任务已审查/消息已外发。

独立assistant-weixin.mjs控制状态；assistant.mjs导入、drawState/dispose/hasPending切换保护接续。每CID/scope变化GET一次，epoch/read序号拒迟到响应；不轮询。页面关闭或权限撤销清理旧状态。未知POST结果保留原request，不自动重发，显示“查找本次授权结果”仅GET；None仍保留未知状态并可继续查询。页面重开只读当前投影，不能因加载自动新增grant。使用textContent，控件具可见文字、focus、disabled/loading/error和窄窗口状态。

## 验收与边界

先失败测试：DTO/状态读写入口缺失、route鉴权/CSRF/跨CID/畸形JSON、Node状态与迟到/未知结果，再最小实现。合成覆盖正常刷新与真正grant表只增1、未绑定读取零新增、CAS/范围漂移/撤权/归档/成员撤除/恢复阻断、账号标识不泄露、真实模型/发送API无调用。浏览器用临时合成workspace、本机Chromium，至少桌面+窄窗口、实际DOCX上传使授权失效→点击刷新→重载保持、丢ACK查询及撤权/恢复呈现；外部请求0，安装版不更新。沿既有DOCX/PDF任务浏览器回归。

保留当前schema16与旧后端回归，四开发门，独立源码/计数/文档复核；只提交本轮授权源码、文档和独立合成样本，正常推送并核远端SHA/tree。跨目标generation、真实微信资格/账号/轮询、E模型/付费、机器人/外发/签发、新安装包和生产验收均未实施或NOT_RUN；0.4.1、原生长进程崩溃、WIN-PATH-02继续开放。HumanLayer/Obsidian/TencentDB按轮收尾，不恢复五分钟轮询或读其他聊天。
