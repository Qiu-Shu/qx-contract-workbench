# WorkBuddy 本轮连接与意见处置

本轮实机status为connected=true；新任务 `wb-fd133d592937` 在本仓库绝对cwd内完成，只允许读取 renderer、history.py、assistant.html 三文件。回执有3次Read completed、end_turn、无错误，无写入或联网。完整原始回执为 `workbuddy-review-completed.json`；不以此前任务或其他记忆聊天的回执代替本次连接。

WorkBuddy在限定文件内未发现高危阻断，提出3个防御性疑点。主代理没有直接照单改代码，已核对实际调用前提：

- renderer对于缺失conversation_id的防线确实比对正常错ID的分支弱，但当前控制器所有对话读取先由 `checked(view,id)` 拒绝缺ID或错ID，历史也校验当前scope。该构造不能通过当前受控入口成为可显示状态；记录为防御性观察，不称本轮已发现跨案泄漏。
- 重复message_id不会到SQL后被误判403：新增 `MainGenerationHistoryQuery` 在1–50有界列表上拒绝重复，HTTP将校验错误转为422；该路径已有测试。一条消息多run或一个run多attempt另有数据库UNIQUE约束（assistant/schema.py、assistant/model_schema.py）。
- read_attempt返回之前经 `validated(MainAttemptView)`，ScopeSnapshot为必填非空类型；prepared input也先校验。因此history中的getattr不是对任意缺字段对象运行。损坏记录应由既有验证/隔离机制处理，不能把未经验证的假对象当成可到达泄漏。

费用和法律状态检查意见与当前代码一致：Decimal原值显示为估算/未知/未发送；模型草稿固定内部待核，不认定法律事实。其提及未来“actual”费用分支不属于当前DTO支持的状态，未因此增加猜测性分支。

静态意见不能证明浏览器、Windows或模型实际可用。主代理已查看实际浏览器/桌面记录，独立代理另有入口及展示审阅；两个实际P2和一个修复回归的关闭凭证以README所列为准。WorkBuddy的源码行号仅用于其当时回复，定位以当前源码为准。
