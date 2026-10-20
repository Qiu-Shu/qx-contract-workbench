# WorkBuddy 本轮计划复核与处理

任务 `wb-4cc5182886cd`，本轮 status connected 后派发，completed/end_turn，三个获准 Read 事件、无错误。完整回执同目录 workbuddy-completed.json。它读取的是接线实施前的 manager/recovery 源码；不是新增功能验收。

1. 旧 submit 拒 skill：事实正确，计划本就要求新 research 入口。新增 submit_research 复用 _admit/_dispatch/_tasks，旧 submit 继续拒技能。不是放宽旧模型入口。
2. 无 runtime 不能执行旧链：事实正确，现将 manager 与模型配置解耦，本机执行器不进入模型/Jev。合成 HTTP no-model 检查直接验证。
3. cancel 协程不等于线程退出：接受这一实现检查点。本机 runner 使用 shield 等待线程；先 interrupt 封存，保留任务容量直到线程结束。合成阻塞线程测试验证 close 未提前返回、迟到无回执。
4. 恢复白名单：补新的精确 fullmatch 读路径，既有中间件方法拦截不变；合成 qxbak 真实恢复后读引用/历史成功，POST 拒绝。
5. history 省略 API 前缀产生文档歧义：实际薄路由位于 /api/assistant/conversations/{id}/research-history。计划现写出全路径，不新增页面白名单或扩大访问。

附注的后台 fence 检查由既有 B1 发布重核与新 cleanup 的 fence 拒写保护；幂等由服务保存摘要及初始研究事件确认。以上须以本阶段最终测试/独审结果为准，WorkBuddy 未运行任何测试。
