# CH-05C 实施与交接

2026-10-20，基线2956482；完成架构交接中的第一片，使用现有工程。实际结果见[验证记录](../testing/jev-native/20261020/README.md)。

| 接点 | 最终改动 |
| --- | --- |
| credential factory | 固定 provider=deepseek/typesafe；TypeSafe canonical envelope；旧 Main 裸密钥兼容；共同使用原文件安全和异步保护实现 |
| model session/settings | 固定 kind=main/judge；沿同一生命周期与受信任 IPC；共享忙碌锁；Jev 不暴露 withAuthorization |
| model control/backend | ready 新增可选 judge_control_protocol；两个固定操作共享 nonce/sequence/pending；无新 HTTP 配置路由 |
| Python domain/native control | NativeJudgeConfigure 在 domain.py；NativeJudgeControl 只配置现有 JudgeRuntime；NativeControlHandler 固定组合，故障 disable_all |
| 原生设置 | 两个入口到同一设置页，独立凭据/运行状态；保存/配置/批准分开，秘密提交后清空；共用返回及失效守卫 |

190桌面测试、119关联Python、四开发门均通过。Spec/Standards静态独审无未关闭发现；实际Windows源码与新冻结后台各9组通过。新增运行依赖/表/队列为0，后端目录较CH-05B增加2626字节，不代表总体资源目标完成。只构建验证后台，不替换安装版0.4.1。

后续CH-05D仍未实现：按既有草稿的精确scope转换建立独立JudgePolicy，接收方/用途/输入/预算单独确认；一个GenerationTasks任务内执行可跳过辅助阶段，再继续原已允许主流程。JudgeRuntime当前单policy槽需明确首版串行边界；不得建第二registry或队列。Jev未配置/无许可/失败时不得扩大主权限。材料分类/运营风险和附件需要各自可靠来源映射。

本片没有使用真实账户、费用、材料或云端。真实价格/账号许可与未知费用对账不能由本机“配置成功”推定。原法库及未下载年份状态未变；GitHub按既有协作流程正常提交同步，完成后核对远端SHA。
