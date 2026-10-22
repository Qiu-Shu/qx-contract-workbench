# CH-07C2a 实测：发送内容与本地保存计划绑定

基线 `37773d92f08e0b3bc2fed27064ceb011e8a72cd6`。Windows 本机源码验证，只使用独立合成材料；不是安装器、真实模型或法律质量验收。

## 本片实际完成

新增纯离线 `profile_preparation`，复用 C1 的同一私有 wire builder；DTO 仅追加到 domain.py。basis 同时绑定完整 UTF-8 请求、system/配置摘要及本地保存用途、档案基线、接待目标/版本和投影选择。整个 basis 摘要才覆盖保存计划，不能用相同正文摘要授予不同的存档行为。

prepare 从已保存 run/message 的视图构造精确 C1 请求，核对请求幂等键、消息关联、用户角色、原文、scope/composer 的保存前后版本。不赋予发送或保存权限，不访问秘密、网络或数据库。合成集成测试实际执行已有 service 保存用户消息，再离线准备并解析合成响应；任务保持 queued，模型账本没有被创建，档案/接待没有写入。

## 实际验证

| 检查 | 本轮结果 | 原始记录 |
| --- | --- | --- |
| 初始 RED | 6失败，缺少准备模块，exit1 | [命令](red.json)、[日志](red.log) |
| 最终关联回归 | **380通过，0失败/错误/跳过**；12文件，含54新增；7.75秒 | [目标](target-nodeids.txt)、[日志](target.log)、[JUnit](target.xml) |
| 输入稳定 | **538份**源码/配置/测试/脚本前后摘要一致 | [运行报告及完整摘要](target-verification.json) |
| 四开发门 | schema、默认关闭、来源、运行依赖均exit0 | [schema](gate-1.log)、[默认](gate-2.log)、[来源](gate-3.log)、[依赖](gate-4.log) |
| Spec独审 | **12组通过**，exit0，0待修 | [报告](spec-review/report.json)、[独立探针](spec-review/probe.py) |
| Standards独审 | **9项通过**，exit0，0待修 | [审查说明](standards-review/final/README.md)、[JUnit](standards-review/final/results.xml) |

独审核对固定基线 C1 builder 的实际字节，包括中文、emoji、转义和长文本；旧 DTO 定义不变，冷导入准备模块不加载 HTTP、SQLAlchemy、FastAPI 或 PDF。未测量包体/整机内存，不据此宣称资源下降。

首次组合回归因 unit/integration 文件同名而收集失败（exit2），改集成文件名后通过；[原日志](collection-failure-target.log)、[记录](collection-failure.json)。两项开发夹具修正、独审长参数触发 Windows 环境变量上限也如实保留于[开发记录](development-record.json)；修正前结果不算最终通过。未重跑此前49分钟全套，既有3816通过/3失败的历史事实不变。

## 未完成与接续

本片无新 registry/native/HTTP、schema、账本或自动保存钩子。当前数据库成员关系、权限、选中附件、档案/接待最新版本仍须由可信装配器核验；离线自洽不能替代这些检查。C2b必须把原生用途确认、完整 basis 比较、新版本迁移、账本历史校验和固定原子保存一起闭合，才允许应用发送该协议。C3继续档案面板与本地联系方式。详见[执行合同](../../../plans/2026-10-23-profile-send-basis.md)。

WorkBuddy 本轮状态 `native_unavailable`，未派发；独立复核由子智能体完成。运行中桌面、真实原件/法库、安装版0.4.1、云端均未操作；WIN-PATH-02恢复发布问题仍开放。[开始状态](preflight.json)。GitHub是否同步以单独回执为准。
