# D2g5d — 固定历史代际的合成分发

基线 `86daac9c6d13dae49dc30eac60113bda711625a9`，cwd D:/Documents/ChatGPT/律所项目；分支codex/contract-review-v2，fetch后0/0，仅用户AGENTS未暂存。复用既有已批准需求及前轮双代理设计，免重复访谈。上轮原生升级旧语义预检已完成，不重做。

## 约定范围

- schema19 `weixin-generation-dispatch-v1` 仅增加 UNIQUE INDEX weixin_dispatch_binding_cursor ON weixin_dispatch_receipts(task_binding_id,expected_task_cursor)。不新建重复delivery sidecar/DTO，保留18前驱36条native/non-native指纹。
- 专用Python合成API `dispatch_generation_descriptor` / `find_generation_dispatch_receipt` 使用持久descriptor sidecar定位历史目标，不读latest代替。旧公开分发及账号generation暂停guard保留；专用写要求native v19、已有代际、实际principal/owner/workspace、非恢复/撤销、root当前ACL/归档以及固定target当前完整scope/ACL。零代原始消息仍用root binding与有效grant，不误锁回旧poll scope。
- 沿用13字段immutable receipt（mapping_id=root；task_binding_id=实际目标）、TaskInbox/TaskDraft聚合及CAS。每(root mapping,fixed binding)按poll顺序分发，不比较不同binding的cursor；旧root pending不阻新代。事件namespace不变，不自动冻结/审查/外发。
- v19-only校验放行合法非零分发和generation后分发：receipt不得早于poll/generation/task event；root与后来target出生因果分开。零代grant仍按receipt历史时间解释；完整sidecar/poll/权限来源父链、撤权、相同binding不重叠和同stream前缀继续核验。v17/v18语义原样保留，不能借升级洗白非法旧记录。
- Query/精确replay使用固定历史目标权限；恢复/逻辑撤销/会话归档可只读找回，当前案件ACL/归档仍后端核。未知query零写、丢ACK不自动重发，事务任一失败全回滚。

## 任务分工与先后

1. 存储代理先冻结前驱、schema/约束RED→最小实现→GREEN；仅其分配schema/bootstrap/迁移/版本gate及新schema测试文件。
2. 运行代理负责dispatcher/共享私有pipeline及新运行测试，先模块缺失RED后实现；root独立负责versioned dispatch/generation校验、新完整性/原子恢复测试及必要旧升级夹具兼容，不重叠编辑。
3. 新增正例须真实TaskInbox/TaskDraft服务可查，固定gen1延迟至gen2后仍仅进binding1；跨stream独立，当前权限/恢复/时钟/并发/SQL故障/丢ACK/新进程及独立合成原件qxbak按可运行范围覆盖。各阶段命令、退出码、数量和输入SHA存实际证据。
4. 关联短组回归、四开发门；旧硬编码最终版本断言仅改为CURRENT，历史DDL/fingerprint断言不松动。由未编写对应产品部分的代理交叉Spec/Standards复核，再由root复算冻结证据。
5. 更新README/TODO/TASK_STATUS，扫描授权源码/文档/独立合成证据，fetch后正常提交推送并核远端SHA/tree。AGENTS保留，不强推、不覆盖协作者。

## 边界

真实微信/合同/模型/付费/外发/签发保持关闭；无安装机器人/新transport/HTTP/UI。可信身份与E许可后续推进。0.4.1不更新；未运行显式NOT_RUN。WIN-PATH-02/原生AV保持OPEN；不以短组通过关闭。收尾Obsidian成功才称已保存，TencentDB沿Stop；HumanLayer旧pending因Windowsargv限长未同步，保留原记录/待重试，不删他人内容、不恢复轮询。
