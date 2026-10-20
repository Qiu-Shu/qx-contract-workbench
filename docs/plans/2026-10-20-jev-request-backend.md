# CH-05D1：Jev 单请求许可与主任务内可选阶段

基线 `27f224c6568fcfdd4c16f49c6533cf9741dbb464`，2026-10-20。已核对README/TODO/CONTRIBUTING/TASK_STATUS、v2.1、CH-05C执行记录及本地记忆；fetch后0/0、工作树干净，无遗留验证进程。复用已批准架构交接第3–4节，不重做配置、账本、队列或历史回归。

本片交付受信任后端和私有管道的完整处理链：实际草稿精确许可 → 保存后同一请求 → 可选辅助 → 原主模型。具体发送确认界面留CH-05D2；真实账号许可、费用来源与可接受预算尚未落实，不在产品界面填入任意正式价格。全部开发只用独立合成内容及本机回环。

## 固定接口

- `NativeJudgeControl(runtime, provider_factory=None, *, database=None)`增加authorize/revoke；无DB拒绝。业务DTO在domain.py：JudgeSendApproval保留原scope/composer/content摘要、request_id与固定primary_intent；NativeJudgeAuthorization带session_token、expected_config_version、max_total_usd与有效期。单次reserved_usd等于明确提供预算；不声称供应商收费上限。
- 后端从实际草稿预测保存后scope（仅input_revision+1），构造完整JudgeRequest并计算现有codec摘要；不接受renderer提供已批准policy/actor/权限。旧请求短摘要墓碑防撤权/重配/过期后复活；已有run仅精确历史existing。
- 一个待执行辅助许可；旧许可未收尾不得覆盖。reserved/sending必须查持久记录，即使policy过期、撤销或换配置仍不能绕过；无辅助attempt的主任务明确终态，或没有未收尾辅助attempt且旧许可已到期时释放槽。过期时仍在队列中的旧Main不会补建辅助：辅助只在首次提交事务中预留一次。新grant/墓碑只在数据库事务成功后发布。撤销仅本人session。
- 同一私有通道新增固定authorize_judge/revoke_judge；另声明 `judge_authorization_protocol=qx-judge-authorization-v1`，依赖现有Jev配置能力。旧仅配置后台仍可配置但不能接收新授权帧。无HTTP密钥/授权路由、无新renderer IPC。
- 现有GenerationTasks、attach_generation、build_local_app增加可选assistant_judge_runtime，同一实例由desktop_entry交给原生控制和任务。主attempt固定原Main lease，辅助缺配置/许可/预算在明确检查点跳过；存储损坏/回滚不可吞。事务提交后仍只建一个task，辅助runner完成后运行原Main runner，不添加第二截止计时器；取消/退出按既有策略阻止主发送、保留已收到回执，清理两种未发送预留。

## 执行与验收

先有效RED，再各模块目标回归，最后独立Spec/Standards和实际源码/冻结Windows进程验证。核对精确scope转换、单槽并发/过期发送、同请求幂等、跨会话撤销、Main许可不能授权Jev、辅助失败不阻主、取消/主撤权、事务故障无任务和重启不续权。只运行受本片影响的回归。

分工：后端许可作者负责domain/native_judge_control与新授权测试；任务作者负责task_manager/web装配及可选阶段测试；统筹负责私有控制两端、desktop_entry、进程验证、证据和GitHub同步。先独立设计复核，再对最终实现独审；WorkBuddy本轮状态busy/unknown，未派发，不用历史结果代替。

结束时更新实际结果、TODO/README/TASK_STATUS，白名单归档合成证据，正常提交/推送并核对远端。安装版0.4.1、真实法库、网盘未下载年份与阿里云均不由此片宣称完成。

## 本片实际完成

CH-05D1已按上述范围实现。201桌面测试、157/83/32三组Python目标及四开发门通过；独立Spec/Standards复核关闭1项授权发布后过期P2。Windows源码10组（Jev/Main各1次合成回环），新冻结控制7组通过，285仓库输入摘要稳定。冻结未执行供应商，日常确认UI、真实费用前提与完整CH-05仍未完成。新未压缩后端增加9,426字节，未增加依赖/schema/队列。详细命令、退出码、数量、分组时间和限制见[本片证据](../testing/jev-request/20261020/README.md)。
