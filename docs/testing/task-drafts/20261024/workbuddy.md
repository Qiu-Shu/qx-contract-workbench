# WorkBuddy 独立复核及处置

2026-10-24，工作区 `D:\Documents\ChatGPT\律所项目`。用户恢复后台协作后使用独立后台会话，只读检查本片核心、DTO、HTTP、任务前端及相应测试；未授予运行命令、写产品、接触真实材料或外发权限。

工具回执：任务 `wb-bg-581a8e553e82`，状态 `completed`，请求及实际模型均为 `kimi-k3-2`（Kimi-K3），`model_verified=true`，来源 `native ACP session/load`；`stop_reason=end_turn`，无权限请求，worker 已释放。不是根据模型自述认定身份。此前恢复前的任务回执不可查，不重复派发、不计作已完成证据。

WorkBuddy 本次为静态审阅，未运行任何测试。以下处置由 Codex 对照当前源码及本轮执行独立核验：

| 反馈 | 核验与处置 |
| --- | --- |
| 显式 task_id 指向满额草稿使整批 413 回滚 | 确认并修复。有效 RED 1 failed，修复后核心 32 passed。溢出事件及完整媒体落为待分配，同批其他事件及游标正常提交，重放幂等；手工超量 assign 仍拒绝。见 core.md。 |
| 暂停/取消草稿收到显式普通消息时转为待分配 | 保留并明确设计语义。收件回执返回 unassigned，原始 task_id 保留，面板列出待分配记录；避免为了关联状态丢失整批原始消息。不会恢复已取消任务。 |
| advance_execution 只检查 read，建议新增 write 权限 | 未确认现有 HTTP 越权。审阅范围未含 bridge/security；当前 read/upload 角色集合相同，无 write 动作，prepare 明确检查 upload、review 明确检查 review，服务层仍检查当前会话归属和案件成员。未照搬不存在的权限名。 |
| 更新读取状态无法修复 ready 材料版本冲突 | 接受真实 UI 缺口，修复 ready 状态也可更新读取引用。其“find 总是旧版”解释不成立：materials.items 为每附件当前唯一选择；实际问题是 ready 行没有更新按钮。 |
| 已排除材料没有恢复入口 | 确认并修复。增加恢复并更新读取状态，ready 材料也可填写原因后排除；保留不可变处理历史。UI 对应有效 RED 后通过，见 ui.md。 |

桥接重试、SQLite 事务及并发绑定的未核实猜测未作为事实。现有桥接独立探针覆盖重复 prepare/review、撤权、原件篡改、失败事务回滚及同摘要不同附件；数据库会话使用现有串行写事务机制。完整 Windows 安装版、真实微信和真实模型仍为 NOT_RUN。

## 代码协作：两种到达顺序的浏览器验收

用户随后明确允许 WorkBuddy 写代码，另派单文件任务 `wb-bg-1daf075dc094`，会话 `8b186993-60d2-4ddd-b6e4-2dc1410cf410`。实际模型仍为 `kimi-k3-2`，原生 ACP 回执 `model_verified=true`，状态 completed；仅允许并实际批准 4 次对 `scripts/validate_task_drafts_browser.py` 的 Edit。产品文件只读，未运行命令或安装工具。

WorkBuddy 增加 `--order instruction-first|material-first`，提取共用上传/读取 helper；附件先行时先验证无指令不得冻结且 execution 数为 0，再把指令补入同一草稿。补齐精确记录数量断言，报告显式保存到达顺序。

Codex 复核后实际运行：指令先行第一次通过；附件先行在已自动展开的任务面板再次点击 summary，误收起面板而找不到运行按钮。属于验收脚本操作时序问题，保留失败报告，没有放宽产品规则。Codex 改用现有“审查合同 · 模拟”按钮的幂等展开动作后，两种顺序最终均退出 0，分别完成 6/7 组步骤。各自 2 inbox、1 draft、1 execution、1 document、1 review、0 assistant run；无页面异常或外部浏览器请求，840 宽无横向溢出；两份临时 native 数据库的结构及来源完整性均通过。详见本目录 README 的实际命令。
