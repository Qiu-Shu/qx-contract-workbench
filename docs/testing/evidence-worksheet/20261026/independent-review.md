# 独立复核及关闭记录

review_evidence_worksheet按仓库AGENTS及requesting-code-review流程独立审查，基线af1ba29；未修改产品代码。以下修复由主执行者完成，随后独立探针及专项回归复核。

1. 表单内容未加入rows时，refresh只检查dirty()而忽略formDirty()；另一窗口新版本可能被保留的旧rows覆盖。独立concurrent-edit探针复现；新回归先RED。修复将表单编辑同样纳入版本冲突，刷新返回false，base_revision仍旧1；真实后端CAS拒绝，不能借刷新把旧清单标成新版本。未自动合并其他窗口事实。
2. 连续回查依据A、B，B先到，A迟到覆盖B。独立late-source探针复现；新回归先RED。修复独立detailEpoch，成功/错误均核对，reset/刷新/历史切换清空。修复后迟到A未改变B详情。

终审反馈：本次审查范围内无剩余确认阻断。独立跑过后端11、schema45、前端12及额外HTTP3项；主执行者复跑HTTP3和两份Node探针并核输出。HTTP覆盖旧陈述保留但新ID不得使用旧来源、非所有者不得读历史/回执、原件I/O期间撤权最终拒写。另独立验证旧19及新schema均精确识别，两者加未知对象后拒绝。

原始探针文件和最终输出在本目录。两个前端探针的concurrent_row_preserved false字段是旧探针仍尝试提交旧内容的显示值；修复后实际refresh_result false、submitted_base_revision 1，真实数据库版本2会以409拒绝，不应误读为修复后仍成功覆盖。

独立复核不是全仓回归或生产/法律验收；本机浏览器与关联回归由主执行者另验。运行依赖清单、安装版、Windows及真实法律质量边界仍开放。
