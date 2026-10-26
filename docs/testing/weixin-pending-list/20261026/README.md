# D2g5g 固定目标待收件列表：2026-10-26 实测

基线 `1924f01bc2dda0f4b12c311e125a5a0f649ce2f7`，沿 `codex/contract-review-v2` 续作已保留的服务、DTO及测试。已合入的 dhb_law 使当前结构为 schema21；本片复用既有19/20/21完整历史校验，不改数据库、依赖或前端。

## 实际行为

新增 GET `/api/assistant/conversations/{cid}/weixin-authorization/pending`，要求明确 `target_conversation_id`，可选 UUID `cursor`、1..20整数 `limit`（默认20）。先认证根及同源，再拒绝未知、重复、格式错误参数；事务内重核当前用户、根和明确历史目标权限。有mapping时目标必须属于根或该根任一历史generation；无mapping返回空页，合法目标没有消息也返回空页。

只返回尚未分发的合成收件元数据：descriptor编号、目标CID、UTC接收时间、是否有文本、附件数量。固定历史目标筛选、被分发的游标仍可续页；不返回消息正文、文件名或通道身份，不自动分发或调用模型。撤销账号/映射不取消既有读取权限，也不恢复分发权限。恢复围栏阻止列表，精确旧回执GET仍可查。

## 最终验证

| 组 | 不同用例数 | 退出码 | 结果 |
|---|---:|---:|---|
| pending服务与HTTP | 86（服务48、HTTP38） | 0 | PASS |
| 分发服务、对话入口及HTTP | 93 | 0 | PASS |
| 分发完整性与事务边界 | 19 | 0 | PASS |
| 合计（按ID去重） | 198 | 0 | PASS |
| 独立Spec探针 | 2 | 0 | PASS，原P2关闭 |
| 独立Standards探针 | 2 | 0 | PASS |

完整argv、用例ID、退出码、日志/JUnit摘要和最终五文件SHA见 [verification.json](verification.json)。每个最终运行前后569份Python/配置输入完全一致，发布记录前再对当前源码逐项核对。先前作者45项、HTTP中间35项、81项专项及重复运行均不叠加到198。未将4个独立探针混入根代理测试计数。

四开发门均退出0：`python -m cn_contract.cli schema --check`、`python scripts/verify_defaults.py`、`python scripts/verify_sources.py --mode development`、`python scripts/verify_runtime_dependencies.py --mode development`。来源13项仍标记NOT_PRODUCTION_APPROVED；运行依赖55包+1构建包、network_calls=0，native_build_verified=false。

## 失败、修正与独立复核

1. HTTP有效RED：原单用例返回404，退出1；其输入SHA保存在 [red-inputs.json](red-inputs.json)，[日志](red.log)。新增最小路由接线后初次HTTP为35通过/1失败，失败来自测试错误要求目标案件拒绝时无审计；核对既有 `security.deny` 后只修测试，验证恰一条脱敏拒绝审计及其他业务表不变。[原日志](http-first.log)保留。
2. Spec独审证实P2：同owner但不属于根的目标被当空页返回，与计划拒绝语义不符。作者补服务2项+HTTP2项先实际失败，再于完整历史验证后补6行归属检查；4负例和合法无消息generation空页均通过。[RED](relation-red.log)、[GREEN](relation-green.log)保留。这不是已证实的数据泄露。
3. **Standards：0项遗留**。2项独立案件归档探针原样重跑通过，[记录](standards-review-final-record.json)。**Spec：原1项P2修复后0项遗留**；独立2探针源码SHA未变，RED→GREEN，[记录](spec-review-report.txt)。可复现探针保存在 [probes](probes)。

服务最初有效RED及作者验证保留于本机 `.local/weixin-pending-list-20261025/backend-handoff.md`。本次完整原始结果、569输入快照及执行裁决保存在 `.audit-local/weixin-pending-http-20261026/`。随仓证据将工作区路径改为相对路径，失败日志去除一行尾空格；原始字节及其摘要保留在本机，独立探针SHA针对原始探针文件。

## 限制与交接

恢复验证使用合成RestoreFence及重建本机应用，未在本片执行真实qxbak归档往返。只读成功请求零业务写，权限拒绝保留既有安全审计。每页最多物化limit+1条加游标来源，但复用完整历史验证会重复扫描；不宣称O(limit)性能。

本片无UI变更，Node/浏览器、全仓长进程Python、安装包、真实微信/模型/客户材料均NOT_RUN；安装版仍0.4.1，WIN-PATH-02与原生AV仍OPEN。后续待UI列表入口、可信微信身份与资格、下载解密、E有限期模型许可。未启用真实服务、付费或外发。

用户原AGENTS.md改动保持未暂存；同步只包含本片源码、测试、计划及合成工程证据。提交及远端SHA/tree结果以后续 [GitHub同步回执](github-sync.md)为准。
