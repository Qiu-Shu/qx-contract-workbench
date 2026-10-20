# WorkBuddy 本轮复核及统筹核对

2026-10-20 本轮 status 确认 connected 后提交 `wb-93002fc64088`，本轮 wait 返回 completed/end_turn。实际成功读取2文件：上下文接续准备、providers/policy.py；请求的 providers/codec.py 不存在，按指令跳过，未追加搜索。3次Read权限请求不等于3文件读取成功。未执行命令、联网、真实材料或产品测试。

1. 新上下文需要独立格式许可：采纳为后续发送条件。现有 require_policy 只处理旧 MainRequest；不能从其扁平hash接口推出当前旧链已经允许上下文。本轮不扩大旧类型、不调用它授权上下文，也不登记模型任务。
2. “prepare缺字节检查”：不采纳为缺陷。实际 policy.prepare 调用 main.build_request，后者在生成规范JSON后明确比较 UTF-8 字节数与 config.max_input_bytes。WorkBuddy 未获准读取 main.py，推论不完整。本轮新纯预览保留同一完整请求计数口径，超限显示 input_too_large，不修改旧保护。
3. 默认字段可能改变 V1 字节：采纳。独立新DTO，旧DTO没有新增字段；既有固定V1请求973字节及摘要有回归验证。新预览本机长度上限不改变旧协议预算。
4. 字段白名单、预览与实际投影一致：采纳为设计要求，但纠正其事实表述。当前旧 build_request 是显式投影content/message_id/quote_sha256，并非把完整请求对象全部外发。当前CitationRef没有原始文件路径字段，其metadata等仍不应自动进入新上下文。本片只投影明确字段；问题、标题或引文正文中本来包含的路径文字不会被偷偷改写，白名单不等于自动脱敏。真正的供应商发送与预览字节一致性还需后续执行切片验证，本轮未发送。

回执与建议仅是静态方案复核，最终产品结论分别由测试、双轴审查和本机HTTP探针支持。未把历史WorkBuddy状态当本轮连通。
