# D2g2 代际历史追加 HTTP 实测

基线 aa20028，依[实施合同](../../../plans/2026-10-25-weixin-generation-http-d2g2.md)接通两条本机接口。仅改 domain.py、weixin_inbox/conversation.py 和 web/weixin_authorization.py；schema17、原子代际服务及整个账号的收件暂停逻辑未改。不是微信运行切换或生产验收。

## 源码已实现

- POST `/api/assistant/conversations/{cid}/weixin-authorization/generations`：路径为原始根会话，复用既有八字段请求；新目标 scope 不要求与根 CID 相同。解析前后复核当前身份、同源、CSRF、根归属、恢复 fence、会话归档和账号/root 撤权。独立 generation context 允许第二代；原 refresh 仍拒绝存在代际的账号。
- GET 同路径下 `/generations/by-request/{request_id}`：固定记录或 null；只核指定根，不由目标 CID 反查历史。恢复、逻辑撤权、会话归档或 scope 增长可读历史；实际根与固定目标当前对象权限仍由原服务再次核验。
- 集中 `WeixinGenerationReceiptView` 精确11字段，固定 `mode=synthetic/state=history_only`。不返回 root/account/bot/peer/actor/task binding/自由 reason/消息正文；scope 摘要和首代前驱关系自洽。`generation_sha256` 是完整底层记录的固定凭据，删减投影不能据此自算完整记录摘要。
- HTTP wrapper 只解析根归属和投影，仍调用 D2g1 的 BEGIN IMMEDIATE 原子服务；完整当前 root/前代/新目标权限、scope 与 generation/hash/checkpoint CAS、旧 request 幂等均复用，不另造写事务。恢复只读白名单仅增加精确固定查询，POST 和近似路径不放行。

## 已有测试与本轮实际验证

旧 D2g1 测试并非仅引用历史结果：本轮重新执行其 DTO/service/atomic/backup 四模块100项。旧对话授权View/HTTP和代际暂停guard三模块77项也重新执行。新DTO/HTTP/独立恢复三模块64项由根代理再跑。以下计数只取三份最终根JUnit，不重复累计作者50或独立14。

| 本轮命令范围 | 证据 | 实际结果 |
| --- | --- | --- |
| 新DTO、HTTP、独立恢复 | root-new.xml/json/log | exit0，64项，进程32.297s |
| 既有Input/service/atomic/backup | root-generations.xml/json/log | exit0，100项，进程65.266s |
| 既有View/authorization HTTP/guards | root-authorization.xml/json/log | exit0，77项，进程36.703s |
| 原14个 `scripts/test_assistant*.mjs` | node-all.json/log | exit0，192项，fail/cancelled/skipped/todo均0 |
| schema --check、defaults、sources development、runtime dependencies development | 同名json/log | 四门exit0；13来源仍 NOT_PRODUCTION_APPROVED，55 runtime＋1 build，native_build_verified=false，network_calls=0 |

根JUnit按 classname/name 去重为**10模块241个不同Python用例**，0失败、错误或跳过。三个Python组均使用 `.venv/Scripts/python.exe -B -X utf8 -m pytest ... -q --tb=short --basetemp=<本项目.local独立目录> --junitxml=...`；完整 argv、UTC起止和退出码在JSON。Node使用现有bundled v24.22.1。14份相关产品源码＋3份新增测试的运行前后SHA一致，源码摘要与去重结果绑定[verification-summary.json](verification-summary.json)。用户AGENTS.md原有未提交改动摘要不变，未暂存。

原始日志/JUnit位于本机 `.local/weixin-generation-http-20261025/`。公开文本副本仅统一LF及去除行尾空白；未上传工作库、qxbak、合同、截图、转储或凭据。

## 验收矩阵

| 场景 | 实测证据 |
| --- | --- |
| 两代追加、第一代原请求重放、固定GET、未知null | HTTP实际通过；generation仅两条，旧历史/游标/任务表不变；账号poll仍STATE_CONFLICT |
| 旧请求改scope/hash/checkpoint/binding/reason或新request持旧CAS | HTTP409；不新增记录；固定GET仍返原投影 |
| 未登录、CSRF、Origin/Fetch-Site、他人/未知根、workspace、归档与逻辑撤权 | 在有界JSON解析之前拒绝；解析期间改变root owner/archive/account revoke也拒绝，generation0 |
| 重复JSON键、非法JSON、超256KiB、额外root/account/actor/时间/模式字段 | 分别422/413，无业务写入 |
| 历史目标scope增长/会话归档、账号逻辑撤权 | 固定GET200且业务/审计快照不变；目标案件成员丢失403，不因历史得到当前访问 |
| 实际native workspace写入恢复fence后重建app | 固定GET200、未知null、POST409；尾斜杠、head、polls、坏UUID和多余后缀仍409；不是本片新增qxbak浏览器验收 |
| 实际HTTP提交后模拟ACK丢失 | 对外500不泄内部错误/理由；已落一条，随后只GET找回且全部其他表/模型记录不变，无重新POST |
| 目标CID反向查询旧root与回执隐私 | 目标路径GET null/POST409；精确11字段，敏感标识/理由不出响应 |

独立恢复14项先RED（缺路由/包装/白名单）再GREEN，根代理最终64包含它们。普通成功GET快照含audit；拒绝可沿既有机制独立记审计，不声明拒绝绝对零写。关联旧服务测试含受控合成消息及queued run样本，不把全部241项概括为零run或零模型基础设施；本片新增HTTP未启动模型。

## 失败与独立复核

根50项RED、独立14项RED均exit1且0 setup errors，属于DTO/路由/context/精确路径缺失，不冒充64种业务逻辑缺陷。最小实现后作者50、独立14和最终根三组全部通过。独立白名单测试将随机UUID改为固定含字母样本，避免大小写测试偶然无字母；未修改产品来迁就夹具。

Standards与Spec两个独立本机审查均无确认遗留项，详见[review.md](review.md)。WorkBuddy任务已由native ACP核实 `kimi-k3-2`，但申请Bash被桥接权限拒绝后取消，未完成审查；未自动重试，Spec由本机独立代理替代。不能将模型核实或任务派出称审查完成。

## 尚未实施与 NOT_RUN

本片无最新CAS head、页面操作或按代际实际接收/分发；账号仍暂停，不称可运行转案。可信微信身份/账户资格及E有限期模型许可继续待办。浏览器UI、全仓测试、安装版Electron、真实微信/产品模型/合同、付费、签发/外发、新安装包均 **NOT_RUN**。安装版仍0.4.1，原生长进程访问冲突及WIN-PATH-02保持 **OPEN**；关联备份通过不能替代原故障修复或安装版验收。
