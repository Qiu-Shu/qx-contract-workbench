# CH-07C2b2b-B：内部档案执行与恢复闭合

基线 `9a0d2df3767dc8252f1530be4f949583fd250af2`，沿已批准v2.1和档案许可切片接续。Codex认领；只用独立合成工作区，不触安装版或真实资料。开始工作树干净、远端0/0、开放PR为空、无活动测试；WorkBuddy本轮native_unavailable，使用子智能体复核。

## 交付合同

复用现有attempts/receipts/outputs、预算、单次claim、runner和恢复封存。档案专有逻辑放`providers/profile_attempts.py`，公共账本仅做明确格式分派；业务DTO仍在domain.py。native/HTTP/任务调度/UI入口本片不接通，完整性检查只有与本片所有语义校验一起完成才开放新格式。无新依赖、schema、模型调用或通用钩子框架。

1. 内部`enqueue_profile(actor,cid,request,db,runtime,project_intake=False)`在短事务中用C2b2a从数据库重建保存计划、C2b2b-A核对许可，再复用预算核验、save_message和实际saved input构造登记round1。相同请求只找回同attempt；旧普通消息不得升级；换用途、计划或许可不得重放。取消、claim或恢复后不重发；failed_before_send只释放既有预算，不复活旧run。
2. 复用claim，在实际发送和采纳前重核当前DB权限/作用域/保存基线与完整许可。网络等待不持DB事务。runner显式使用profile reply/provider接口，超时和任务取消按既有sent_unknown结算，无自动重试。费用与候选采纳分离。
3. 当前文字提案必须绑定本次message、source revision、精确Unicode位置/quote/hash、scope、base profile revision；不接文件、旧消息、非空回答citations、document_statement或已收材料。复用纯函数校验于结算与历史验收。联系方式和事实仍待核；无模型manual edits。
   独立复核补充：出处展开后候选规范JSON最多240KiB，为现有256KiB完整输出读取上限预留16KiB固定元数据壳；超限记无有效输出但保留用量，不写不可读档案。
4. 撤权、改绑、当前资料或档案/接待基线变化时，丢弃候选但保留已收到费用，无output或handler。仍有效的候选在同一外层savepoint里完成profile_store._commit、模型输出/费用、固定response.ready、profile.save/1处理回执和终态事件。成功/unchanged关联原ProfileCommitReceipt，失败不可通过换事件或版本重试。
5. 固定保存request_id为`uuid5(NAMESPACE_URL, 'qx-profile.save:1:' + str(run_id))`。response.ready payload固定attempt_id/output_id/basis_sha256/handler_id/handler_version；保存结果事件profile.saved/profile.unchanged/profile.blocked payload固定attempt_id/output_id/event_seq/handler_id/handler_version/outcome/reason_code/profile_receipt_sequence。两类事件均internal，handler行逐项对应。模型model.finished继续既有结构。
6. profile_store权限拒绝可能rollback并提交审计，savepoint本身不能防止这一点。保存尝试必须发生在费用/output/response事件写入之前；在保存异常的savepoint外重新require_active、读取sending+claim并重新_current。重新核验失败只落费用；仍有效则记录保留回答及blocked(version_conflict/save_failed)。不得沿用被rollback的ID/事件。最终账本写入失败应向上抛出，整个成功savepoint回滚，不能留下半档案。
   实测修正：外层savepoint使用显式SessionTransaction生命周期，不能使用SQLAlchemy的with上下文；后者在deny结束事务后阻止新审计事务。仅仍active时rollback，已提交拒绝审计不再回滚。
7. 历史验收复用所有旧模型、附件、法库、Jev、档案校验；新增格式校验完整basis/wire/原请求摘要/许可单次形状及output patch。固定handler必须与同次output、ready和结果事件一一对应，成功回执的request与候选/保存计划严格相同，保留已有profile_integrity语义重放。拒绝孤立handler、缺handler、混合格式、额外事件、伪造来源/目标/回执和重新计算摘要后的篡改。reserved/sending恢复仍封存为未发/未知，不创建handler或续发。

## 验证与交付

先保留有效失败验证，再实现目标测试：实际合成SQLite到回环HTTP单次请求、原子档案/接待、回执、重放/预算/权限/取消/在途修改/保存错误/拒绝审计、慢响应期间第二会话可写；历史篡改和实际qxbak恢复/禁写/不调用。补受影响的旧账本/runner/资料回答/档案/备份回归及四开发门；不因文档变动重跑完整旧套件。独立双轴复核，记录实际数量和稳定输入，README/TODO/TASK_STATUS及本地提交后正常推送并核对远端。

安装版仍0.4.1；WIN-PATH-02最终目录偶发WinError5独立开放。源码合成通过不代表真实供应商、界面或安装器验收。下一片接原生用途许可、HTTP/调度和档案面板。
