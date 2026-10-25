# D2g5f 前端独立审阅（含修复后复验）

审阅者未编写本轮前端产品或 Node 测试；仅编写另一个 HTTP 验收模块，该模块排除在独立审阅声明之外。审阅对象为 `49e7b55` 基线上的 `assistant-tasks.mjs` 工作区变更与新增 `scripts/test_assistant_task_media_selection.mjs`；来源为本轮 D2g5f 计划、AGENTS、CONTRIBUTING。未运行全套 Node/Python、浏览器、真实资料或模型。

初次审阅输入 SHA256（修复前）：

```text
src/cn_contract/web/static/assistant-tasks.mjs 028e7dea3ba13711b2892d7ab4339d73fa016525af9cd3b8ba5038b0fe815497
scripts/test_assistant_task_media_selection.mjs 4d34f0cf7dae7ec53ceac4395bae5ba9afa69a0f7d7cf0d8650144159ab92a56
```

## Standards

0 个确定的标准违规。改动复用原生 select、现有 POST/PATCH/GET 与 DTO，没有新依赖或后端权限捷径。文件名、原始消息与提示均走 textContent；当前 CID/epoch、draft revision/collecting、loading、材料 frame 和具体 choice 身份在异步读后核验；只读/冻结与 busy 控件受限。错误处理区分已确认保存后的列表刷新失败。

## Spec

### [P2，已修复复验] 新材料 frame 可被陈旧 host 通知回退，已重选的新原件消失

- 位置：`src/cn_contract/web/static/assistant-tasks.mjs:119`–`:122`、`:190`、`:338`。
- 计划要求：“材料变化使未提交的选择失效并明确提示”，并要求材料快照在异步流程内一致。服务返回较新 materials 后，用户依该新快照重选，后续无关的旧 host 通知不应再把候选退回上一版本。
- `resolveMedia` 检测 GET 材料与当前 frame 不同后直接 `renderMaterials(materials)`，仅推进模块私有 `materialsView/materialKey`；父 controller 中的 `state.materials` 仍是旧值。下一次 `state(oldState)` 通知无条件走 `renderMaterials(state.materials)`，又设置旧材料并清空 mediaChoices。
- 可复现序列：host 当前材料 revision 1，文件 local；GET 返回 revision 2，保留 local 并新增 new-file；首次操作安全失效并正确展示新候选；用户重选 new-file；父 controller 发送原先 revision 1 的普通通知；new-file 从下拉消失且新选择丢失。
- 独立 Node 探针已实证：正式运行 **1 FAIL / 1 PASS，Node exit 1**，产品/作者测试/探针前后摘要稳定。失败断言为 `an unrelated parent notification must not reinstall materials_revision 1`。现有 56 项作者测试没有这个 GET 私有 frame 推进后再次收到旧 host frame 的组合。
- 最小修复方向：将这次材料更新与 host 当前材料同步，或对同 CID 可比较的材料 scope/revision 保留已知较新 frame，并明确处理绑定变化；保持下一次异步提交前的 frame/choice 重新核验。补永久回归，避免只检查 candidate 是否存在而漏掉旧 host 回退。
- 影响是人工选择丢失、候选退回和重复失效；本次未发现因此绕过后端权限或写入不匹配附件，故不是数据外发/越权结论。

## 独立探针与边界

正式探针 `independent-media-review-probe.mjs`（SHA256 `623fd3fc84b637f84e9834ed72b46c8c8e25e27c8425ca38f99bf7dd0bd06c12`）只复用作者测试的 fixture 前缀，新增两个由审阅者独立编写的行为断言；不把复用 mock harness 称为真实浏览器。

1. 材料 frame 回退：FAIL，见上。
2. NETWORK_UNKNOWN 后，精确 revision+1 的目标 resolution 存在于历史，而 latest 已变为后来的另一个 replacement：PASS，确认只 GET 找回原结果，不再次 PATCH，也不错误坚持 latest 必须一致。

`independent-media-review-probe.json` 保存实际 argv、UTC、exit 1、前后输入 SHA 与 `changed_inputs=[]`；原始 TAP 日志为 `.log`。外层 Python 采集脚本 exit 0 表示采集完成，**不能冒充内部 Node exit 1 已通过**。

初次试写探针把 GET 中旧候选删除，提前命中“未找到原件”分支，未测到预期回退路径。该初始记录完整保留为 `*.initial.*`，不用于本 P2 的正式失败证据；修正为保留旧候选并新增候选后，失败精确落在旧 host 回退断言。

修复前总计：Standards 0；Spec 1 个 P2 未解决。真实微信、下载解密、模型、浏览器及安装版均 NOT_RUN。

## 最终修复复验

作者在 `renderMaterials:119`–`:126` 增加同 CID 的可比较 scope 守卫：保存快照的 binding/input/materials 任一整数 revision 已更高时忽略陈旧通知；`clear:98` 清 scope，CID 切换不延用旧会话；正常等值或递增 scope 仍接受变化并清选择。现有后端在同 CID 上三类 revision 单调追加，因此该守卫没有把当前材料写权限交给前端，也没有放松提交前的 frame/choice 检查。新增作者回归包含三种 revision 各自回退，以及等值/新绑定 scope 继续生效的正向分支。

审阅者使用**原正式探针完全不变的字节**重新执行：**2 PASS / 0 FAIL，Node exit 0**；原 RED 日志和 metadata 未覆盖。记录保存 `independent-media-review-probe-green.log/json`；输入前后 SHA 一致，原探针 SHA 仍为 `623fd3fc84b637f84e9834ed72b46c8c8e25e27c8425ca38f99bf7dd0bd06c12`。

最终审阅对象 SHA256：

```text
src/cn_contract/web/static/assistant-tasks.mjs 32bdb69c76353e2899f6c3c40bb84742d7e39a651dc1e99ca450aed385bbae50
scripts/test_assistant_task_media_selection.mjs 008b556fc31a0b4f20ee2a13a496b92e82d824d23670e832398c37953deca523
```

最终结论：**Standards 0 个未解决，Spec 0 个未解决；历史发现 1 个 P2 已由作者修复并经原探针 GREEN 复验。** 本审阅者未编写产品或作者 Node 测试，也没有独立重复运行作者全套；其 81 项结果由作者/root 实际记录单独提供。浏览器及真实能力仍不属于本独审执行范围。
