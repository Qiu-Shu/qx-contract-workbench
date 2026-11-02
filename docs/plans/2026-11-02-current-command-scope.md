# 当前指令范围：隔离修复片

状态：隔离源码及本机合成工程验证完成；最终402后端、628桌面页面、四开发门通过，旧版本及原内容证据回放一致。见[实际工程记录](../testing/unified-plan/20261102/current-command-scope.md)。最后独审增量由Codex验证，不称最终独审零发现。主仓代码未合入；原v1/v2商标对照保留0/4原答、0/8评分和原失败。下一片执行[商标v3单方法两轮内容协议](2026-11-02-trademark-v3-followup-content.md)，新2/4分母，尚未初始化/冻结/生成。合同补发仍等待已发出的用户确认，不重试。

主仓D:/Documents/ChatGPT/律所项目保持当前WIP与合同556份源码封印。已创建且附加隔离工作树：C:/Users/Administrator/.codex/worktrees/trademark-command-scope/律所项目。HEAD为15acd84546616f8c44dc394e04bf7753cad72739，detached；Git可见WIP复制939文件，另6175摘要相同，无缺失。不安装、不提交、不推送，不自动覆盖主仓。

## 要解决的行为

明确“请做商标初筛。”之后追加“若后续补充材料到达，应在同一案件续办”，不得过滤当前无条件请求。条件本身未满足时不得触发，条件前件与逗号/分号后的从属动作不能被切开后误当授权。用户后发暂停、取消、只接收、否定、引用及转述仍优先。原完整失败问题在主仓`.audit-local/trademark-followup-quality-20261102/fixture.json`，不可为跑绿而替换。

## 设计与实施边界

1. 在隔离工作树先扩展RED，覆盖当前商标请求+后续条件动作“再整理”、纯条件命令、逗号/分号连接的条件前件、明确否定、引用/转述、先后操作顺序。现有8项诊断3失败5通过；同组120项既有单元通过。两组各自报告，不合并宣称全绿。
2. 保持`business._command_text`、默认旧`execution_hold`及旧方法选择语义可重建；优先给现有current入口提供明确的句级范围解释。`_latest_command(current=True)`已有当前入口参数可复用，但先审查全部调用者。当前business记录回读不重跑classify，不需为此臆造数据库迁移。
3. 商标v1/v2的select/validate_snapshot按旧解释保持；因方法指纹不覆盖选择代码，本次不能在旧id下静默改变语义。需要新商标方法版本时固定新id/system，旧system及渲染逐字保持；同步domain白名单、skill_registry和桌面依据。禁止顺带重写合同v3、刑事方法或提示词。
4. 前端现有assistant-business.mjs也按整行过滤条件；同步当前入口的相同反例，保留发送、未知回执找回与暂停保护。微信调用共享后端，按影响范围补合成控制回归；不启真实微信。
5. 沿用实际预览/排队/保存/回读接口做新当前指令的最小合成验证，再验证旧v1/v2请求/成果完整字节与历史记录不变。方法变更后的内容对照方案须在任何生成前另记，原v1/v2失败预检不得删除、改成通过或混入新组成绩。
6. 用原主仓.venv/Scripts/python.exe运行，工作目录/显式PYTHONPATH必须为隔离工作树，记录实际导入路径。先目标RED/GREEN，再关联回归和必要开发门、独立Spec/兼容审阅。新文件留隔离目录；主仓只更新状态与报告。完成后再核对主仓未变和如何安全纳入，不能自动破坏仍冻结的实验。

原始证据在主仓`.audit-local/trademark-followup-quality-20261102/`：preflight.log（exit1）、routing-red.*（首份含1个诊断脚本错误）、routing-confirmed-red.*（3失败5通过）、routing-review-receipt.json、worktree-copy.json。隔离目录同名audit下保存worktree-routing-red.*及worktree-existing-baseline.*（120通过）。独审为静态复核，实际测试由Codex执行；未检验完整全仓/安装版或真实模型。
