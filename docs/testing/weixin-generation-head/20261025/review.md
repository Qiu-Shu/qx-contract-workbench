# D2g3 复核口径

固定点dee54eaf096b9e930dc82c9d095bffa6434fe257到本轮工作区。四产品文件为domain.py、weixin_inbox/generations.py、weixin_inbox/conversation.py、web/weixin_authorization.py。另有四个新测试、旧recovery精确两项预期调整、计划和证据；用户AGENTS.md不纳入审查/提交。

## Spec：独立本机审阅

独立代理d2g3_head_atomic先编写11项实际SQL竞争/损坏/schema/重开Database测试，RED→GREEN后冻结四源及本测试SHA并进行Spec只读复核。未发现确认产品阻断：七字段严格冻结DTO/零代摘要 iff/scope哈希；root/history/latest target与投影在同一accounts._transaction；零代lastgrant或mapping、非零latest；当前ACL不豁免，历史不承诺当前授权；根CID包装及精确GET路径不扩张运行时，暂停guard保持。

独立额外实跑latest owner/workspace两个HTTP用例，复现409与原测试403预期差异。generation_integrity原本要求记录target当前owner/workspace仍符合不可变来源，篡改先判历史损坏；fail-closed且无披露。root读取源和日志确认，保留产品原顺序，将两个测试精确分类为409，普通ACL仍403。该两例失败日志和最终根回归均保留，不隐藏最初44＋2。

审查输入四源SHA256依次为domain `99ea0d5793dfecdc84fe1f3379dd6562850e56a02750aa4dcd12e32b50c4eebb`、generations `4d7e82d8b8dd1b7cca030545e506c937407870c802efe927234e2cf18bf70004`、conversation `de25074489e652d20493850763559ea3fe36ca2ba35381cb0cfdba5ba752e96f`、web `1a283a94183a38204508f8117ae8343540f2edca2f18049ca3ed50c4b1c2bd36`；与根最终运行摘要核对。Spec代理没有修改产品或别人的测试。

## Standards：root核查，独立代理未完成

root核对AGENTS的集中DTO、当前权限/UTC、不可变历史、合成验证及Ponytail最小充分改动要求，结合既有D2g1/D2g2模式检查四文件diff；0项确认违规。安全wrapper负责CID归属，核心服务负责事务授权，分层有实际边界；未加schema/依赖/前端或真实调用。全文历史校验与写锁开销保留为限制，不通过移出事务牺牲一致性。

此轴并非独立第二代理结论：新代理及对已完成代理follow-up均被宿主拒绝 `agent thread limit reached`。随后新D2g3 WorkBuddy任务wb-bg-ab333ef24568经native ACP session/load核实requested/actual=`kimi-k3-2`、model_verified=true，但其Bash申请被桥接拒绝（allowed=false），状态cancelled、无答复结论，未自动重试。不能把此任务、调度成功或模型核实称独立审查通过，也不重复上轮D2g2失败任务。

本片已满足独立Spec与实际独立测试后由root复验；**独立双轴完整流程未完成**，独立Standards审查NOT_RUN。生产、UI、安装版及真实账户链路均未据此确认。原生崩溃和WIN-PATH-02不关闭。
