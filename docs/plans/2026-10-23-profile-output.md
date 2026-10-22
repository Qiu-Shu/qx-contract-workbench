# CH-07C1 同次回答与档案提案协议

基线 `1a7072bb905568a24292a53f3f3133c7c9fbb4f6`。沿用已批准的 v2.1、CH-07 设计及无人值守授权；复用现有 JSON 封套、DeepSeek 传输和档案合并，不另建抽取模型或网络客户端。当前主应用在运行，开发只使用独立合成资料和回环服务。

## 本片范围

现有普通回答协议只接受 text/citations，不能安全地从任意回复截取 JSON 作为档案。新增明确的 `profile-text-v1` / `profile-text-system-v1` 请求和独立 codec，同一个响应同时返回回答与字段提案。先只覆盖当前已保存用户文字；附件、历史对话、法库全文不进入该输入。

- DTO 都在 domain.py。可信请求沿用 MainRequest 的消息与来源摘要，增加协议、模板、档案基线版本；显式 source_revision 必须为正且等于本次 scope.input_revision，C2须从已保存用户消息核对，不能拿后来版本替代。
- 模型仅提供 text/citations/profile_changes；citations固定空数组，字段引文另用quotes；每项为既有 field/value、user_statement 或 model_inference、原文 quotes（Python Unicode 码点起止位置与逐字引文）。身份、作用域、版本、SHA、审核者和事实确认状态均由服务器填充，模型不能提供。
- codec 校验完整候选、严格 JSON、精确 quote 与当前位置，再构造既有 ProfilePatch/ProfileMessageRef；拒绝伪造原文、非空联系方式、received/checked材料和其他越权字段。新wire金额必须为十进制字符串、时间必须为明确带时区ISO字符串，拒绝隐式epoch推断；不改变共用人工DTO。未知值仍是 null，冲突并列保留，人工保护由既有纯合并执行。
- DeepSeekProvider 只增加懒加载的 generate_profile 入口，共用现有传输、预算上限、取消、错误与 usage 保留；默认 preflight 拒绝，密钥读取前后及返回有效候选后复核。撤权则不返回候选，保留received和实际usage。一次回环 POST 返回回答与提案，不增加第二次提炼调用。
- 原 MainRequest/MainCandidate、普通回答与资料辅助的请求字节、运行流程和接口不变。无新依赖、表、HTTP路由、registry许可或自动写库。

本片不是自动建档启用。C2必须同时完成版本化请求登记/历史验证、原生确认中的整理用途与完整字节绑定、固定保存钩子和迁移恢复，才允许应用发送新协议；旧普通文字许可不能默默升级。C3接档案面板与独立的本地联系方式处理。通用写作是否投影接待由受信流程决定，不由模型提案授予。

## 实施与验证

1. 在现有 build_request/decode_response/provider.generate 接口位置写有效失败；增加新协议DTO和纯codec。
2. 逐项增加来源、边界、资源上限、模型越权及旧字节兼容测试，不按实现重算期望。
3. 复用既有合成HTTP服务器，验证默认禁发、前后重核、一次请求同时产出、错误仍计实际usage、未知不重发。
4. 运行本片及受影响的普通/上下文/轮次provider、来源/合并关联回归和四开发门；独立Spec与Standards复核，保存命令、实际数量与退出码。
5. 更新TODO/README/TASK_STATUS与执行记录，正常推送并核对远端。

既有 WIN-PATH-02 的恢复发布 WinError5 继续开放；本片不改备份模块或重复上轮49分钟全套。无真实供应商、模型、原件、法库、安装器或云部署验证。
