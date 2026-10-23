# CH-07C2d 独立 Spec 复核

日期：2026-10-23。基线 `d3c3b173af0fe3f3f0d878df6793a601e181d081` → 当前冻结工作树（含新增文件）。对照 `docs/plans/2026-10-23-profile-desktop.md` 的八条接口/安全合同；范围为可信桌面授权入口和最小静态模块修复，不把后续统一对话提交/自动保存侧栏列为本片缺陷。

**结论：最终受审范围内无未关闭 Spec 缺陷。独立探针 9 项通过，0 失败/错误，退出码 0，0.140 秒；21 份审查输入前后 SHA256 一致。**

## 实际核对

- `profile-basis.cjs` 校验完整 17 字段及 7 字段 scope，固定用途/模板/handler；严格布尔、安全整数、摘要与接待 id/revision 配对及 intake scope 绑定；返回独立、有固定顺序的副本。`model-control.cjs` 为 authorize_profile 接五字段，仍用同一私有协议；`backend.cjs` 只增加对应委托。
- `model-session.cjs` 的 authorizeProfile 使用实际 ACK 决定 profileStatus，withAuthorization 不采信 callback 伪造的相反状态；配置锁、单次 lease 和失效清理复用。existing 不产生新 grantedToken，失败时不撤销本次没有新增的许可。旧 plain/context 继续原返回形状，Jev 无档案授权路径。
- `profile-approval.cjs` / `model-approval.cjs` 对页面五字段选择进行克隆；当前文字和直接 basis 从本机服务读取；确认前后核对完整 scope、文字、cookie、全部 basis 和活动状态。同 wire 的合法保存目标/版本变化仍改变 basisKey 并拒绝旧确认。最后一次身份检查失败会由原 lease 清理新许可。只调用 profile-preview，不调用生成或档案提交。
- `model-approval-window.cjs` 六字段详情继续原隔离 modal、父窗/main-frame、网络封闭与关闭清理；正文与计划用 textContent。project_intake=false 即使已有目标也显示不同步；无目标的投影说明已经改为有可用于接待字段并形成有效变更时“尝试”创建。窗口展示保存意图，未声称已保存。
- `preload.cjs` 仅增专用 authorizeProfile；未增加永久并列业务按钮，未改聊天发送流程。两个新增桌面模块纳入 package.json 明确文件白名单，无新增依赖。
- 最小范围扩展：`src/cn_contract/web/app.py` 仅将已被聊天 import graph 使用的 `assistant-context.mjs` 加入静态白名单；没有改路径解析或扩大为任意静态目录。新增 HTTP import graph 测试检查 200、JS MIME、源码字节及未知文件 404。此修复是让既有聊天模块实际加载所必需，不扩业务权限。

## 审查前观察已闭合

1. 草稿不持久化技能选择：计划第 4 条现已改为固定文字协议，服务端拒绝带技能的提交，后续页面负责互斥；没有新增虚构 draft.requested_skill 校验。
2. 初读施工状态将 awaiting_input 放入 INACTIVE；最终文件已移除。独立探针证明此状态在 profile-preview POST 前拒绝。
3. 接待创建文案已从笼统“有有效变更”改成需要可投影字段和有效变更；独立 DOM 探针覆盖投影开/关，不把计划说成保存结果。

这些是冻结前观察与修订，不记成独立探针的失败次数。

## 独立验证证据

运行入口：

```powershell
.\.venv\Scripts\python.exe .local/profile-desktop-20261023/spec-review/run-review.py
```

实际 Node argv、cwd 见 `command.json`；原始输出 `output.log`、JUnit `results.xml`、退出码 `exitcode.txt`；汇总 `summary.json`；21 份完整 SHA 见 `inputs-before.json` / `inputs-after.json`。

9 项包括：authorized/existing 不能被 callback 伪造替换（2）；晚失败仅撤销本次新增授权（2）；没有实际 native 调用不能伪造许可（1）；awaiting_input 在预览前拒绝（1）；同 wire 不同合法保存目标的完整快照不等价（1）；投影开/关条件说明、文本输出及离页清理（2）。

边界：本次独立探针是 Node 内存合成 backend/snapshot 与 VM DOM，没有网络、真实 Electron、Python DB 或供应商调用。未重跑作者全桌面/前端/实机验收，作者 366 Node、68 前端、19 HTTP 与 5 组 Windows 结果不并入独立 9 项分母；此前 4,393 Python 全套也不称本轮独立结果。没有改产品/产品测试、没有提交。
