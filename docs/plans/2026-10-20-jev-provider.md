# CH-05A Jev 薄提供器与纯路由

从 `7dd5abb` 接续已批准 v2.1 和本日协议笔记。本片新增独立 Jev 提供器、固定问题模板、严格响应解析及纯工作流建议；不改首页、安装版或持久队列；既有主模型仅补两行日志包装兼容修复，生成及授权流程保持。没有真实凭据、真实材料或模型调用；生产默认关闭且没有接线。复用已有 httpx2，不新增 SDK。

## 实现契约

- 业务 DTO 仍放 `domain.py`：`JevConfig`、`JudgeRequest`、`JudgeChoice`、`JudgeNoul`、`JudgeUsage`、`JudgeResult`、`RouteDecision`。配置固定 `jev-1.13.0` / `typesafe-systemone-v1`，默认关闭，输入最大64KiB、响应最大256KiB、外层最大2000ms。
- Request只有本机请求ID、完整scope、purpose、必要text和可空explicit_skill。不接收任意问题、URL、密钥、权限结论。固定purpose为primary_intent/material_kind/possible_result_guarantee，一次只投影必要问题；完整scope留本机，不上送。
- `JevProvider(config, secret_resolver, *, preflight=None)`，`judge(request, *, expected_config=None)`。preflight为可信后端同步回调 `(request, config) -> skip_reason | None`，不接受renderer传入；缺省返回no_egress。它是下一片接现有权限/预算/持久attempt的入口，不是本片已经实现这些授权。显式主意图已选、关闭、不需要辅助等本地跳过不读密钥、不初始化HTTP。任何未来调用方须先保留完整请求、做权限和预算检查并持久claim，才可允许发送。
- 线上端点固定；合成工厂只允许精确 `127.0.0.1:<port>/v1/systemone`。无代理/重定向/自动重试，依赖延迟载入。总截止涵盖前置、连接、读取、解析、结果采用和清理；取消向上传播，未知发送不重发。
- Result区分ok/skipped/timed_out/failed/invalid与not_sent/sent_unknown/received，包含本机ID、输入摘要、耗时、可空供应商ID/usage；答案只能在ok时存在。未收到usage不补零，超过截止不可采用答案。输出不包含原始正文/密钥/异常字符串，不声明法律事实或批准。
- `choose_workflow(explicit_skill, judge_result, allowed_skills)`仅返回可空workflow/source/reason。显式选择优先，非法显式选择不被Jev替换；unknown/失败/不在可选集合都保持当前已授权流程（workflow=None）。不处理权限或切换供应商。调用方保留完整诉求和附件，纯函数不能单凭标志证明保存完成。

## 验证和交付

先失败测试，再实现DTO/路由及提供器。使用合成回环验证固定wire、严格Choice/Noul、缺/空usage、错误/重定向/慢响应/逐块慢读、总截止、取消、敏感日志与不重试；检查关闭时的依赖载入及网络为零。运行影响域回归、独立双轴复核、默认/schema/来源/依赖门，记录实际命令/退出码/数量和文件摘要。本片无生产接线，不为未被导入的新模块重建安装器；单独检查模块可由冻结构建收集，真实安装版接入以后验证。

保留首次失败日志。不得把本机回环当TypeSafe连通或中文法律质量验收，不把前置回调当已经实现持久费用/外发权限，不自动重建数据库或重新导入法库。

## 2026-10-20 实施完成记录

本片工程验证完成。新增独立DTO、codec、薄传输与纯路由，复用httpx2、默认关闭且未配置preflight即跳过。原主提供器两行wraps兼容修复关闭交替日志递归；实际model只认已验证回执，严格固定选项和2000ms采用截止保持。

最终367关联用例通过（154新用例含其中）、489输入稳定，四开发门通过；独立Spec36项及Standards4组通过。源码与独立Windows冻结探针各4组通过，均仅一次合成回环、外部0；11明确构建输入与EXE绑定一致。没有构建桌面后端/安装器，不声称真实Jev、持久费用授权接线或法律质量完成。单模块资源观察有少量新增开销，不宣称总包体/RSS/启动下降。完整命令、退出码、修复和harness失败区分见[实际证据](../testing/jev-adapter/20261020/README.md)。

下一片CH-05B沿既有原生配置/权限/费用/任务边界接线；先保全完整请求、核对scope/配置与独立外发许可，durable claim后才放行preflight。未知发送不可自动重试，建议采用前重验版本。不得把本片callback当已经落地这些控制，不重做本片已完成测试或协议研究。
