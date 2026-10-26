# D2g5g — 固定目标待收件列表实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox syntax; this is the current heartbeat's bounded backend/API slice.

**Goal:** 当前律师可在明确根CID与固定目标CID下分页查找尚未分发的合成descriptor编号，再沿已存在的明确POST/精确GET接口处理。

**Architecture:** 2026-10-26续作基线为已合入dhb_law的1924f01、codex/contract-review-v2（原计划4325711）。根CID仅解析其唯一mapping，目标CID只筛历史固定binding，不反解root、不读取latest目标。复用当前principal/对象ACL、现有schema19/20/21完整来源验证和固定source，不写收件/游标/任务，不增加数据库结构、依赖或真实微信能力。

**Tech Stack:** 现有FastAPI、集中Pydantic DTO、SQLAlchemy/SQLite、pytest。

**Spec:** sources/specification-v2.0.md；既定D2离线推进及docs/testing/weixin-dispatch-http/20261025/README.md、docs/testing/weixin-media-selection/20261025/README.md。

## 约束与接口

- 新DTO仅在domain.py：WeixinPendingQuery(target_conversation_id:UUID, cursor:UUID|None, limit:int strict 1..20 default20)；WeixinPendingDescriptorView(descriptor_id, conversation_id, received_at UTC, has_text bool, media_count strict0..20)；WeixinPendingPage(mode=synthetic, read_only=True, conversation_id=明确目标, items最多20, next_cursor)。不输出账号/bot/peer/mapping/binding/poll ID、合同正文/文件名、源事件/原始响应、reason/opaque upstream cursor/hash。
- GET `/api/assistant/conversations/{cid}/weixin-authorization/pending?target_conversation_id=UUID&cursor=UUID&limit=20`。根认证与同源先核，参数仅允许三个唯一键，未知/重复/坏格式拒绝。目标必须是当前有权读取的本机对话；无法映射root返回空页，非所属target/cursor拒绝。
- 服务public seam `pending.list_pending_descriptors(actor,cid,query,*,database)`。独立BEGIN IMMEDIATE内重新核根principal/ACL、完整schema19/20/21历史与明确target当前ACL/关联案件有效性。有mapping时target必须属于root binding或其任一历史generation，尚无descriptor不影响合法空页；无mapping仍返回空页。列表恢复围栏阻断，精确旧分发回执GET仍按既有白名单；不把新列表加入恢复白名单。
- 按COALESCE(固定sidecar binding,root binding)筛目标CID，只返回accepted且无dispatch receipt者，顺序为poll.next_revision、descriptor.ordinal。UUID keyset anchor必须来自同root+固定target的accepted原件，**即使已分发仍可推进分页**；不能用pending过滤查anchor。不信客户端位次/哈希；页外limit+1仅判断more，不回传额外记录。新poll追加可在后页出现，不承诺冻结全库快照。
- 对已撤销账号/映射及已归档对话，仅在既有当前对象读取权限下提供待处理元数据；不视为可分发权限，原POST仍核active/revoke/fence/CAS。案件归档/撤权、跨owner/workspace拒绝。旧target失权不阻另一个明确且有权target的分页，latest失权不替代历史target ACL。
- 本轮不接UI/新preview正文、不下载解密、不自动分发/冻结/执行/调用模型；安装版0.4.1未更新，WIN-PATH-02/原生AV继续OPEN。

## Review Focus

1. 同owner其他peer/account、目标CID反查root及foreign cursor不能跨根混入。
2. 页锚点在两次GET间被分发，后页仍正确，重复/blocked及已分发排除，单poll同ordinal边界不重不漏。
3. 明确历史target与当前target权限独立；旧pending不挡新target，当前真实principal与案件权限不可由缓存actor替代。
4. 读取零业务写、未知编号不制造记录；schema/父链/sidecar损伤拒绝，恢复只读白名单不扩大。
5. metadata字段严格脱敏、分页上限/唯一query、UTC及DTO字段精确；任意GET不产生模型/TaskInbox/TaskDraft/回执/游标增量。

## 实施与验收

- [x] root有效HTTP RED为404，退出1，输入SHA与日志已保留；沿用后端作者服务有效RED及45项测试，不把导入错误当有效RED。
- [x] 后端作者原domain.py、pending.py及服务测试已保全交接；root补web路由/HTTP测试。独审发现P2后root另补服务6行历史归属守卫及回归测试，原作者已完成，不存在并发覆盖。
- [x] 最终冻结五份源码/测试，3短组198不同Python、四开发门通过；569输入每组前后不变，不叠加作者/中间运行。无新UI，Node/浏览器NOT_RUN。
- [x] 未参与产品作者分别独立Spec与Standards复核：Spec原P2修复后0遗留，Standards0遗留；原4个独立探针不改断言复跑通过。README/TODO/TASK_STATUS及阶段测试记录已更新。
- [ ] 仅授权源码/文档/独立合成证据；保留用户AGENTS未暂存，获取远端后正常提交推送并核SHA/tree，非强推；三端收尾按本轮真实回执，HumanLayer限长pending不冒称云端同步。
