# D2g3 最新代际 head 实测

基线dee54ea，按[实施合同](../../../plans/2026-10-25-weixin-generation-head-d2g3.md)新增本机只读head。schema17、原子追加和账号暂停守卫保持；不是微信运行切换、真实模型验收或安装版更新。

## 源码已实现

`WeixinGenerationHeadView` 集中七字段：`mode=synthetic`、`state=history_only`、generation、generation_sha256、scope、scope_sha256、checkpoint_revision。严格非负整数、零代 iff 摘要null、scope精确摘要；省去账号/bot/peer/actor/root/taskbinding/自由reason，不添加can_append。完整record摘要仍为opaque凭据，历史头不承诺当前执行权限。

`generations.read_peer_generation_head` 在既有 `accounts._transaction` 的 BEGIN IMMEDIATE 内重核当前root、完整历史和最新目标当前权限并构造头，代际/摘要/checkpoint来自同一锁快照。零代取最后有效grant或原mapping的持久授权scope，非当前会话snapshot；非零取最后generation。仅核root和latest当前对象权限，不因更早非latest目标成员变化误挡最新head，完整来源校验仍不省略。

`conversation.read_generation_head` 仅按根CID解析原mapping，事务服务随后重核；未绑定返回null，不反向搜索历史root、不编造零代或游标。GET `/api/assistant/conversations/{cid}/weixin-authorization/generations/head` 复用当前身份/同源，并只在恢复白名单增加这一精确路径。会话归档、逻辑撤权及恢复副本可读历史，案件成员撤销/归档仍拒绝；POST仍受完整权限/CAS和恢复fence限制，整个账号收件继续暂停。

## 本轮实际验证

全部命令及退出码、UTC时间、运行前后19份输入（14相关产品源码＋4新测试＋1更新旧测试）SHA见verification-summary及各组JSON。最终根JUnit按classname/name去重，不重复累计作者46、独立11或其他历史阶段的统计。

| 本轮实际范围 | 证据 | 结果 |
| --- | --- | --- |
| 新DTO、head service/HTTP、独立atomic四模块 | root-new.xml/json/log | 57项，exit0 |
| 旧Input/generation service/atomic/backup四模块 | root-generations.xml/json/log | 100项，exit0 |
| D2g2 receipt/HTTP/recovery三模块 | root-http.xml/json/log | 64项，exit0 |
| 旧View/authorization HTTP/暂停guards三模块 | root-authorization.xml/json/log | 77项，exit0 |
| 原14个assistant Node模块 | node-all.json/log | 192项，exit0，fail/cancelled/skipped/todo均0 |
| schema --check、defaults、sources/dependencies development | 同名json/log | 四门exit0，来源13仍NOT_PRODUCTION_APPROVED；55runtime＋1build、native_build_verified=false、network_calls=0 |

共**14模块298个不同Python用例**，最终0失败、错误或跳过。pytest使用本项目 `.venv/Scripts/python.exe -B -X utf8 -m pytest ... -q --tb=short --basetemp=<本项目.local独立目录> --junitxml=...`，分短进程执行；Node为现有bundled v24.22.1。完整argv在JSON，不把阶段925/814/310/241与本轮298相加称全仓总数。原始证据保留在本机 `.local/weixin-generation-head-20261025/`，公开文本副本仅统一LF和行尾空白；不上传库、qxbak、原件、截图、转储或凭据。

## 验收矩阵

| 场景 | 本轮实测 |
| --- | --- |
| 无grant、最后grant后root scope又增长、连续两代 | head分别准确取mapping、grant及latest完整scope/hash；不以当前版本计数代替授权来源，checkpoint精确 |
| HTTP head→显式POST第一/第二代 | 请求仅用HTTP头和目标会话/binding构造，不读取内部账号表；旧head新request追加409，不自动重试 |
| 当前root与latest权限 | root他人/未知/workspace、latest案件成员撤销/案件归档拒绝；非latest旧目标成员变化不误挡最新head。latest owner/workspace篡改被完整历史先判409，普通ACL丢失403 |
| 归档/逻辑撤权/恢复/版本增长 | 历史head固定；成功前后业务与audit逐行相同；目标CID不反查root，未绑定null且不创建记录 |
| 真实native恢复fence后重建app | 精确GET head200且值不变，POST409；head/、head/x、heads、Head、head/polls仍409；非qxbak浏览器新增验收 |
| head与append、head与poll双向竞争 | 实际两个Session/SQLite BEGIN IMMEDIATE等待，无sleep/忙轮询；头返回完整旧或新快照，旧gen/checkpoint用于追加409，未拼接不同时间数据 |
| schema/历史损坏、新Database | 前16版、pre-inbox及未知结构409不升级；scope/grant/generation摘要篡改409不修复；新Database读两代准确且历史/audit不写 |
| 私密投影与近似路径 | 响应精确七字段，不出账号/peer/root/actor/binding/理由；同源/登录仍核，恢复仅精确路径放行 |

关联旧服务组保留独立合成消息/queued run来源样本；不能把全部298项概括为零run。新增head不启动worker或模型，不改旧payload、grant、游标或任务。成功只读无业务/audit写；权限拒绝可沿既有机制记审计，不声明所有拒绝绝对零写。

## 失败分类与复核

首次收集因unit和integration同名测试模块产生1 collection error（exit2）；将unit重命名为head_view，未改产品，不作为业务RED。随后根46和独立11项均因DTO/服务/路由缺失明确RED，0 setup errors。初次实现后44通过、2失败：测试把latest owner/workspace身份篡改预期为403，实际旧generation_integrity在ACL前校验不可变来源并返回409。独立代理另行复现这两项；精确改为409 VERSION_CONFLICT，成员/案件ACL仍严格403，未改产品守卫或用“403或409”淡化预期。最终作者46、独立11与根四组均通过，所有原失败日志/XML保留。

独立本机Spec复核无确认产品阻断，root规范/安全核查无确认违规；[review.md](review.md)分别记录口径。第二独立Standards代理因宿主agent thread limit未启动，WorkBuddy新任务虽核实Kimi-K3仍因Bash权限拒绝取消，未审查完成、未自动重试；**不称已完成独立双轴审查**。

## 尚未实施与 NOT_RUN

明确桌面页面/操作、按代际接收/分发与历史生效边界、可信微信身份/账户资格和E有限期模型许可仍待。head成功不是写授权或真实收件，当前账号继续暂停。浏览器UI、全仓、安装版Electron、真实微信/产品模型/合同、付费、签发外发、新安装包和独立Standards代理审查均 **NOT_RUN**。安装版仍0.4.1，原生长进程访问冲突和WIN-PATH-02保持 **OPEN**。全库历史校验和BEGIN IMMEDIATE会占用写锁，这是当前完整性边界的代价，未在此片优化或声称生产性能完成。
