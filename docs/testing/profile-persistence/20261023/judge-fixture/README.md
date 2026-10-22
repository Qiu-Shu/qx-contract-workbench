# Jev 授权测试替身修复

原因是测试 Service 未跟随主模型控制接口新增 authorize_context，真实 NativeModelControl 已提供该方法，桌面启动直接采用它。初始精确目标测试 1 failed（exit 1），构造阶段即抛 AttributeError，尚未进行派发。

只在测试替身补一个立即抛错的方法，未改产品代码。目标与相邻协议测试 36 passed（exit 0）。两次局部负控制分别把 Jev 授权故意派发到 main.authorize、main.authorize_context，原测试均如期失败，证明新增 stub 不会掩盖越权。

实际日志及 JUnit 见同目录；report.json 记录退出码、数量、前后摘要与 CodeGraph 查询。只变更 test_judge_authorization_protocol.py；未调用真实模型，未重跑全套，未提交或推送。
