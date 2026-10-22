# CH-00A3 接待服务解耦与加载验证

基线 `1a73e36f687b6dc0eab98892149737c02e8d9ce6`，2026-10-23 北京时间。本片依据[执行计划](../../../plans/2026-10-23-intake-decoupling.md)，只用独立合成材料。

## 结果

接待直接复用应用层建案函数与纯记录编码，不再导入 Web 服务/作业存储；Word 在导出时加载。旧 Web 入口保留同一函数别名。建案权限、角色、复核人、材料模式、规则/政策、嵌套事务、记录摘要与导出受众均保持原行为。未新增依赖、DTO、schema、路由或档案功能。

| 检查 | 本轮结果 | 证据 |
| --- | --- | --- |
| 新进程导入边界失败验证 | 修改前 1 failed，实际被 docx 导入触发 | [RED](import-red.log)、[XML](import-red.xml) |
| 首批导入＋接待回归 | 14 passed，exit 0；已包含在后述147项中 | [日志](green.log) |
| 13文件关联回归 | **147 passed，0 failed/errors/skipped，exit 0**，pytest 163.12秒 | [文件清单](target-nodeids.txt)、[日志](target.log)、[XML](target.xml) |
| 四项开发检查 | schema/defaults/sources/runtime 全部 exit 0 | [实际命令与输入](target-verification.json)、[1](gate-1.log)、[2](gate-2.log)、[3](gate-3.log)、[4](gate-4.log) |
| 验证输入 | 520个源码、配置、脚本、测试输入摘要前后一致 | [回执](target-verification.json) |
| Spec 独立复核 | 4探针通过，0待修；真实HTTP转案失败注入命中，全部表回滚后可重试 | [报告](spec-review.md)、[命令](spec-command.json) |
| Standards 独立复核 | 4探针通过，0硬违反/需修改判断；迁移AST、编码、导入边界和别名保持 | [报告](standards-review.md)、[回执](standards-probe.json) |

四项检查仍是 development 范围：13个来源的既有 NOT_PRODUCTION_APPROVED 提示保留；55运行包/1构建包、网络调用0，native_build_verified=false。未执行完整项目全套、GUI、冻结后端或新安装器验证。各阶段和独立探针计数不累加成“总测试数”。

## 加载收益及边界

同一 Python 3.12.14、同一[探针](measure_import.py)、每次全新解释器：未跟踪7次、另开分配跟踪3次；前后探针SHA一致。

| 独立接待模块导入 | 修改前 | 修改后 |
| --- | ---: | ---: |
| 已加载模块数 | 584 | 438 |
| 不带分配跟踪的导入耗时中位数 | 0.6157912秒 | 0.5709488秒 |
| Python跟踪分配峰值中位数 | 41,330,852字节 | 35,343,162字节 |

跟踪峰值约下降14.49%。修改后的所有样本均未加载 web.services、web.storage、docx、documents.ingest、review.workflow；[修改前](import-before.json)、[修改后](import-after.json)。先测前再测后、样本有限，耗时受缓存/系统负载影响；不把该数字当成整机启动、应用可输入时间、RSS、安装包或完整运行内存收益。导出实际仍需要已锁定的 Word 依赖。

## 接续核对及旧失败

- 开始及发布前 fetch：基线与远端无分叉，开放PR为空。接续的是协作者已完成的发送/轮次/选片/模型UX代码，没有重复实施旧阶段；README中旧“应用发送关闭”状态已按证据纠正。
- WorkBuddy 本轮状态为 `native_unavailable`，无专用会话活动端点；[状态摘要](workbuddy-status.json)。未派发、未自动重试，不采用旧连接回执充当本轮协作。独立复核使用子智能体。
- WIN-PATH-02 原两失败项在未改产品前复跑：仓库专用目录2/2通过、原 `D:/pytest-base` 下新目录2/2通过；[本地日志](win-path-02-local.log)、[原位置日志](win-path-02-original-location.log)。两次是同2个用例，不是4个不同用例，且已纳入本轮关联回归。**未复现、根因未定、没有修复或降低文件守卫**；此前日志本身不能证明扩展路径或链接数是根因。
- 活动 Electron/后端未停止，所有验证使用独立合成目录；真实工作区、原件、F盘索引、真实模型及云端均未操作。安装版仍为0.4.1。

## 接续

[CH-07设计复核](../../../plans/2026-10-23-profile-draft-readiness.md)明确：复用接待版本链，增加来源/人工保护；首次保存须同时闭合档案修订、接待投影、回执/事件、版本冲突、迁移及只读恢复。本片未实施自动档案。

`evidence-manifest.json`校验所选原始证据的实际字节，不覆盖本README及其自身。GitHub同步结果以独立发布回执为准。
