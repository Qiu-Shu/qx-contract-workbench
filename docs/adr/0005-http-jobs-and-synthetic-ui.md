# ADR 0005 — T10 本机页面、HTTP 接入与持久任务

状态：采用，仅独立虚构开发。实际浏览器、法律金标准、真实外查批准和生产状态分别记录。

页面与 HTTP 是现有 T02–T09 服务的薄接入。固定 FastAPI、SQLite、Jinja 模板及原生 CSS/JS，不另建审查引擎或第二套业务 DTO。`domain.py` 仅追加有限输入 DTO；ReviewRun、18 维核心 schema 和默认参数保持。`create_app(settings, *, database)` 必须接受显式、已初始化且配置相同的 Database，导入不建库、初始化用户或启动 worker。`start_job(JobInput, actor, *, database, parameters, idempotency_key)` 同样显式接受存储和受保护参数，不提供隐藏数据库。

真实会话 cookie 使用 HttpOnly/SameSite Strict；CSRF cookie 只存验证令牌，写请求重验实际会话、令牌、同源、当前角色和案件成员。客户端 Actor、保护字段或 UUID 不授权。业务错误固定四个字段，授权先于读取和解析 JSON/multipart。六类页面使用明确中文表单，原文仅写入 textContent，固定 Jinja Environment 显式 autoescape=True/StrictUndefined；合同不是模板源码。资源同源，无 CDN、字体下载或公共原件目录。散列、结构位置和原始类型收进详情。

上传仅接受服务器登记的独立虚构内容 hash；普通演示仅登记四个固定虚构 DOCX。客户端文件名、`synthetic=true` 或环境密钥不能证明材料获批。上传、基线、实际解析、候选、完整事实确认和审查分别留存版本。普通 mock 输出受 T06 validator 约束；失败的 ReviewRun、raw 尝试和实际用量提交后，任务也显示 failed，保留 result_ref 供授权核对，不把“已存证”误称“审查成功”。

排队前实际认证/CSRF/权限/当前输入核验在短事务内完成，job input 与 queued event 在同一 savepoint。单 worker 原子 claim 后提交，再开始工作。JSON payload、actor/session/matter、输入和案件 hash 不可更新，事件只追加。Idempotency-Key 按 actor+matter+action 隔离，同 key 同 payload 零第二副作用，换 payload 409。读取重放仍重验身份、案件、版本；已完成审查还调用实际 read_run(current=True)，patch 和 bundle 重放还调用 T09 load_patch/read_bundle，不能复活已撤销批准。重启 running 任务保守 blocked，不自动重发。

本地解析与 mock 计算使用有界 CPU 事务，结束后另一个短事务重验真实会话及实际完成输出的当前性。解析自己的事实版本变化允许完成，但随后另一连接发生文件、事实或立场变化即受阻。审查读取当前 run manifest；查询重验 frozen plan 与原输入。单机 SQLite 仍有本地 CPU 写锁窗口，不宣称分布式队列、任意高并发或完整进程沙箱。

查询 HTTP 只短认证、精确计划批准和排队；worker 使用 T08 exact Database Factory 与真实 SDK，在 SDK 等待期间没有请求 Session。真实外查默认关闭。工程测试可以由服务端显式登记单一 localhost synthetic MCP endpoint，仍须实际发现、绑定、价格、预算与计划批准；客户端字段、普通 scope 和环境变量不能启用它。该入口只验证受控本机模拟连接。成功收据、失败零扣费、未知占额/次数、网络期间另一连接提交、撤销会话/改变立场后的 durable 账本及零第二发送分别实测，不替代账户、官方 schema、价格、许可或真实批准。新案没有预算批准时展示待批和默认 20/6/1/0，不偷偷生成批准。

五类人工处置追加 HumanDecision，接受意见不等于 patch 或正式签发。精确替换使用实际 full anchor.quote，单独批准完整 old/new/reason 和 audiences，复用 T09 三受众草案与当前 hash 下载。高风险草案由不同的当前复核成员批准；can_sign 只属正式门。独立虚构 demo 可显式设定模拟复核身份的签发能力以实际观察硬门，mock 始终以 T09 的 403 BLOCKED_LIVE 拒绝，无 override。

`demo-server` 是单独显式本机示范命令，只绑定 127.0.0.1、单 worker、新建项目 `.local` 子目录和四个虚构身份；创建案件时只邀请明确填写的复核用户名。退出要求 worker 停止并关闭数据库。已有目录不会覆盖。其公开模拟密码不是现实账户或律师资质。正式应用初始化、现实身份及部署批准仍需后续任务。

T09 的复杂/对外原件修改人工降级、QCC 收据报告消费者和整份补丁后语义重审未实现项保持；真实模型、规则/政策/许可、律师金标准、现实试点与生产仍阻断。TestClient 六页和四份 API 旅程不等于普通浏览器通过，浏览器与 Word 的实际证据由独立根任务记录。
