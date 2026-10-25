# D2g5e 固定消息的对话HTTP分发与找回

> 执行沿既有TDD/分工独审流程；用户已明确无人值守、沿当前分支实施并逐片正常推送，不重复访谈。

**目标：** 将已实现的固定历史代际合成分发接成根对话拥有者可明确调用、按精确descriptor只读找回的HTTP入口。

**架构：** 复用现有FastAPI授权路径、集中DTO、固定分发管线和SQLite短事务。既有Python公开API不变；仅提取可在同一事务复用的私有分发/查询，最终事务内同时解析根CID、核对descriptor所属root mapping及当前固定目标权限。schema19和旧入口guard不变。

**依据：** [D2g5d合同](2026-10-25-weixin-generation-dispatch-d2g5d.md)、[D2g2 HTTP合同](2026-10-25-weixin-generation-http-d2g2.md)、当前规格v2.0及用户本轮heartbeat。基线02e7e32；保留用户AGENTS未提交改动，使用现有开发环境，不安装依赖。

## 最小接口与取舍

只接两个精确入口，暂不新增全量pending列表、raw poll预览或新UI。全量列表需要多个历史目标的分页权限政策，raw计划含账号/peer/session/opaque cursor，不适合直接暴露；精确接口可以独立完成边界验收，供后续同一任务页面复用。

- POST `/api/assistant/conversations/{cid}/weixin-authorization/dispatches`，body仅`descriptor_id` UUID。身份、当前根归属、CSRF、同源、恢复/撤销/归档先于有界严格JSON读取，读取后再核，最终原子事务再核。
- GET 同base的`/dispatches/by-descriptor/{descriptor_id}`，同源、当前根及固定历史目标ACL；不依latest、不按拥有的其他peer/目标反解root。已知未分发返回null；未知/不属于根的descriptor拒绝，不泄漏私有来源。恢复/逻辑撤权/会话归档只允许权限下的固定读取。
- 新集中`WeixinGenerationDispatchInput`和`WeixinGenerationDispatchReceiptView`。view仅9字段：mode=synthetic、state=recorded、descriptor_id、conversation_id、task_event_id、expected_task_cursor、next_task_cursor、created_at、receipt_sha256。摘要是完整内部回执的不透明标记，不伪称可据投影重算。无账号/mapping/binding/bot/peer/session/source正文/理由。
- GET恢复白名单仅接精确lowercase UUID路径，不扩到POST、列表、尾斜线或任意子路由。丢ACK后只固定GET，不自动重发；新写/重放继续native19、已有代际、earliest/CAS/撤权/fence守卫。

## 分工与验收

- [ ] root先写服务/DTO失败测试，保留输入SHA与实际RED；最小实现domain.py、conversation.py、generation_dispatch.py，不新建表/DTO文件或复制完整性管线。
- [ ] HTTP代理先写真实服务准备的HTTP行为RED，最小接web/weixin_authorization.py与精确恢复谓词；禁止修改root产品文件。
- [ ] 实测固定目标晚分发、另一peer/account/根和目标权限、未知/未分发/重放、顺序、错误body及解析前后撤权、恢复只读、丢ACK、零模型/零外发；后端最终事务CID匹配必须独立受测。
- [ ] 短组关联回归、四开发门，按最终不同node ID计数不累计重复。未运行全仓/Node/浏览器/安装版均NOT_RUN，已有故障不关闭。
- [ ] 未编写产品的代理整体独审；HTTP作者仅交叉审root部分，作者排除明确。更新README/TODO/TASK_STATUS及实际证据，扫描明确allowlist，fetch后正常提交推送并核SHA/tree。

真实微信/合同/产品模型/付费/签发外发保持关闭；不安装机器人、不新增transport/下载解密。可信身份/资格与E有限期许可仍后续推进。0.4.1不更新；WIN-PATH-02/原生AV仍OPEN。收尾Obsidian取得成功才称保存；HumanLayer保留自有pending并按实际回读报告；TencentDB沿正常Stop。
