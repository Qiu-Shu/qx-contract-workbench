# DeepSeek 首批离线接入范围

2026-10-03。用户已指定 DeepSeek，并明确本轮先完成接入和离线验证，真实调用暂不开始。最终交付目标为 ChatGPT 插件；本轮不建立外部插件、账户或托管项目。

状态：DESIGN_PENDING。第一批具体设计已在聊天中提交确认，尚未新增适配源码或测试；不能把 T13 的815历史回归计作新接入通过。本文件记录实际预检、复用边界与待实施范围。

|现有能力|本轮复用|保持的边界|
|---|---|---|
|ModelProvider、ModelRequest、ModelResponse、ModelUsage|使用原三类操作与唯一领域模型；增加纯离线请求/响应适配|业务DTO仍只放domain.py；不直接序列化完整案件上下文到外部|
|strict_json|有界对象、重复键、非有限数与深度检查|官方JSON模式不等于法律schema、锚点或批准校验通过|
|MockProvider及注册门|默认审查链保留原行为|DeepSeek不能靠环境变量、duck typing或用户传入的provider对象进入真实审查|
|T08预算网关|未来复用短事务、预留、发送标记、未知停发与对账的方法|模型token费用不是QCC积分；模型独立账本、价格批准与币种转换仍未实现|
|T13拒绝门与受限交付|保留现实批准缺失时BLOCKED|DeepSeek接入意向不构成QCC、真实资料、律师签发、生产或平台隧道批准|

拟实施的有限改动：固定文本请求参数，校验明确的模型标识、输出token上限、JSON响应及用量；离线响应正常、截断、工具调用、型号漂移、缺用量、超限与未知结果分别测试。合成价格只能作为显式离线测例，不猜正式费用或把缺失用量填0。第一批不增加真实网络transport、不读取key、不开放既有workflow注册门，也不自动修复或重试付费请求。

本次公开预检核实Chat Completions/JSON/token契约；模型名称与价格会变化，须按执行时正式文档和获批快照核验，不能从历史别名或公开优惠推断账户实际价格。[官方请求与响应](https://api-docs.deepseek.com/api/create-chat-completion/)、[JSON模式](https://api-docs.deepseek.com/guides/json_mode/)、[模型列表](https://api-docs.deepseek.com/api/list-models/)、[公开价格](https://api-docs.deepseek.com/quick_start/pricing/?tab=case-studies)。公开源读取不是供应商API联调；预检中两个无query地址打开超时，后用官方搜索取得规范，实际过程保留在`.audit-local/deepseek-preflight/READ_ONLY_REPORT.md`。

新增功能测试当前NOT_RUN。没有搜索或读取密钥、安装新SDK、接受协议、创建账户、付费模型请求或真实材料上传。真实接入仍需单独完成可信模型配置与批准登记、数据政策/地域/保留约束、模型持久费用账本、当前价格/汇率、有限调用范围与安全key引用；法律规则和两律师gold继续分别阻断。

未来插件的后端复用、身份与文件桥见[ChatGPT目标映射](CHATGPT-plugin-target-map.md)。该方案PLANNING_ONLY，尚未安装、连接或发布，当前不将本机stdio与ChatGPT网页连接混为已完成。
