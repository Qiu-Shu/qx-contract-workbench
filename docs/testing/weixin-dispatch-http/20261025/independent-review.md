# D2g5e 独立整体复核

结论：**Spec 0 个确认产品问题；Standards 0 个确认违规，0 个需修复的 smell。** 本报告由同一名未编写本片产品的代理分别核对两个轴线，不冒称两名独立审查者。没有为通过审阅修改产品或既有测试。

## 范围与冻结点

实际 workspace：`D:\Documents\ChatGPT\律所项目`。基线由父代理指定为 `02e7e32a7d16c583d20d02396c6dc08cc348b65d`；按子任务范围未执行 Git，不声称本审查另行验证远端或提交树。本代理先只读研究上一片断点，之后审阅四个冻结产品文件；未参与这四个文件或本轮新增 tests 的编写。

| 产品文件 | 完整 SHA256 |
|---|---|
| `src/cn_contract/domain.py` | `f8f64176edbc9866887ade894680492769ae46b8ddd4bc3c6bc107632b89fe2e` |
| `src/cn_contract/weixin_inbox/conversation.py` | `025fe5960dcfb967fdcf871d3589f068e10094717b6ac54ea09a11f538ca1c14` |
| `src/cn_contract/weixin_inbox/generation_dispatch.py` | `a1f22dc3c7813f9a28a050acb46f3880ad9316ad3b98e83bb260e04a8f9df361` |
| `src/cn_contract/web/weixin_authorization.py` | `0f5b0756a1f3ba85d2776e681db3ef0da3d2e66088b4ee034623c99358a4d45f` |

需求依据：`docs/plans/2026-10-25-weixin-dispatch-http-d2g5e.md`（首次复核 SHA `b1ee8d34ad2c21d9b23753dade7a6efeb63d9e714b1631ab174b814c753305f1`）、D2g5d 既有服务合同、用户合成离线与恢复边界。标准依据：当前 AGENTS、CONTRIBUTING、DTO集中/后端权限/UTC/原子性/原件与审计不可覆盖/复用现有模块，以及 Ponytail 最小充分原则。`independent-review.json` 和 `independent-probe.json` 保存完整范围及哈希，不用短 SHA 代替冻结输入。

代码定位来自当前磁盘 CodeGraph（完整读取四文件相关符号）及精确 rg 调用点；旧分发函数体与本代理本轮早先读取的 D2g5d 源码核对。未执行 Git diff；此限制不影响下面的当前产品独立边界探针，但不代替父代理提交 allowlist/diff 检查。

## Spec

- **同一最终事务的 CID 与固定来源**：`conversation.py:158–166` 在 `accounts._transaction` 内取 `_generation_context`，将实际 mapping ID 传给 `_dispatch`；`:169–178` 在同一事务解析 root 并调用 `_find`。`generation_dispatch.py:81–86,102–105` 在任何 TaskInbox/receipt 写入或返回前精确比较 descriptor mapping 与 CID root。错误 peer/account/root 不能借有效 CID 选择别人的 descriptor。
- **固定 target 而非 latest**：既有 `_source:31–66` 仍核完整父链、实际 principal、账号归属、root ACL、持久 sidecar 的固定 binding/scope；新 receipt 继续 `_scope_reason(active=True)`、逐固定流 earliest、共享 `_deliver` 和最终 `_validate`。未增加读取 latest 的授权替代。receipt 的 conversation_id 由固定 `task_binding_id` 查得并在同一事务内形成 DTO。
- **两条 HTTP 与有界输入**：`weixin_authorization.py:64–73` POST 前后复用当前权限、CSRF、同源，再在线程池进入最终原子服务；GET 同源和当前根权限后进入精确固定查询。输入 DTO 在 `domain.py:4869` 仅允许 descriptor_id，继承 frozen/extra-forbid；service 再验证 model-copy 绕过。
- **输出与未知结果**：`domain.py:4873–4889` 输出精确 9 字段，cursor 必须加一；`conversation._dispatch_receipt:148–155` 用 DTO 字段白名单投影。未直接返回内部 receipt/plan、身份、正文、理由、binding 或 upstream 游标；SHA 明确为完整回执的不透明标记。POST 完成提交后才返回；精确 GET 不调用写管线。
- **恢复/逻辑状态**：exact regex 只增加 lowercase UUID `/dispatches/by-descriptor/{id}`，未放开 POST/前缀/列表；现有恢复 middleware 的方法阻断继续有效。find 沿当前 root/固定 target ACL，逻辑撤权/会话归档不误作新授权，写/重放仍受 fence、revoke、active 和已有 generation 限制。
- **兼容与范围**：两个原 Python 公共 API 签名保持 `(actor, descriptor_id, *, database)`；原 transaction 仍保留在公共入口。仅提取 `_dispatch/_find` 共享 seam，没有新 schema、worker、transport、自动分发、模型或 UI，也未改旧 legacy guard。

文档口径提醒（非产品缺陷）：无 root mapping 的 CID，`find_dispatch:173–175` 返回 null，不按 target CID 反查 root，延续既有 D2g2 风格；已经绑定的 root 对未知/不属于自己的 descriptor 返回拒绝。已向父代理提醒，计划的“未知拒绝”宜明确这个无绑定 null 情况，不能把页面尚无绑定当成某个 descriptor 已存在。

## Standards

DTO 仍集中在 domain.py；无绕开来源/权限/版本核验的客户端决策。最终 write/read scope、共享服务和投影在同一短事务，外层线程池不等待外部网络。既有完整性、恢复 fence、TaskInbox/TaskDraft 聚合和来源校验复用，没有复制 DDL/receipt 管线或新增平行材料存储。最小 wrapper 为同时核 CID 与来源所需，私有 root_mapping_id 约束用于新边界而不改变旧公共签名；没有确认的 speculative generality、数据 clump 或无目的 middle-man。身份秘密不出现在新 View；无日志/外部发送改动。

本轮源码/测试之外的 Git、依赖、发行包、真实账号或模型是否改变由父代理 allowlist/状态检查负责；本审查不伪称完成这些检查。

## 独立实际探针

本代理只在 `.local/weixin-dispatch-http-20261025/` 新写 `independent-probe.py` 与 runner，没有导入本片新增 routes/conversation 测试作为探针实现；只复用 D2g5e 之前的原生合成 workspace、CID/账号/代际准备及消息构造 helpers，并直接调用当前真实 HTTP/服务。

实际命令（runner 另将完整 argv/UTC/原始 stdout/XML 记录）：

```text
.venv/Scripts/python.exe -B -X utf8 .local/weixin-dispatch-http-20261025/run-independent.py
```

退出码 **0**；pytest **5 PASS，0 FAIL/ERROR/SKIP，7.30s**。不是父代理新增 64 例或回归的重复累计。594 个源码、测试、fixture、标准/规格、独立脚本输入前后 SHA 完全一致，差异为空；四产品哈希与上表一致。

1. 在两次 HTTP authorize 和 body 解析均完成后、实际线程池服务执行前归档 root；最终事务 409，TaskInbox/receipt/cursor/run/execution 全部不变。
2. gen1 描述接受后新增 gen2，再使后代 target 当前案件 ACL 拒绝；原 gen1 描述仍只分发到记录 target，9字段回执及 GET 一致，身份、正文和游标 canary 均不输出。
3. 同一律师、同一账号下另一 peer/root 的 CID，GET/POST 该描述均 403且任务表零变；实际 root 仍能成功分发，避免“整个 descriptor 本身无效”的伪反例。
4. 实际服务提交后主动丢 HTTP ACK，GET 找回同一 descriptor 回执；把写路径替换成必失败断言后 GET 仍成功，TaskInbox/receipt 各一条、状态不变。
5. 用 inspect 核旧公共签名，精确恢复 predicate 接受唯一路径、拒尾斜线/extra/uppercase/邻近路径/坏 UUID。

原始证据：`independent-probe.py`、`run-independent.py`、`independent-probe.log`、`independent-probe.xml`、`independent-probe.json`。本审查没有产品 RED，因未发现确认 bug；不制造失败证明。恢复真实 qxbak、跨进程、完整父链回归等未在这5项独立探针重跑，需由父代理实际最终验收支持。

## 实际限制

本独立审查未运行全仓长进程、Node、浏览器/Electron、安装版、真实微信/合同/模型/付费或网络，均 NOT_RUN。未改 src/tests/docs/Git/配置/依赖/数据库（探针仅独立合成临时库）/记忆，未读取或指挥其他聊天。安装版仍未验证，WIN-PATH-02/原生 AV 未验证修复，不能关闭。结论仅适用于上表四个冻结产品 SHA。
