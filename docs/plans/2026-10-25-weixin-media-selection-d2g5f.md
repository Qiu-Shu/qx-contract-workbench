# D2g5f — 待收件附件显式关联本机原件

沿当前49e7b55、codex/contract-review-v2继续用户已授权的无人值守实施/正常推送，保留AGENTS用户改动。采用Ponytail最小改动、既定TDD/独审和Impeccable Operate现有界面；不重做A—C解析桥、D2g5e分发或已验底座。

## 意图与范围

微信离线FILE目前只带pending元数据、没有attachment_id。原“更新读取状态”只能按已有attachment_id找附件，用户另行上传原件后仍无法关联。复用既有TaskMediaResolutionInput与PATCH、当前CID materials/精确parse查询，增加明确选择入口。原收件、原文件、解析及修改历史保留，不推断附件内容或自动匹配同名文件。

在原任务“已收集记录”每个缺原始attachment_id的材料行内，显示有label的原生select与“关联所选原件并更新读取状态”。只列当前对话已上传DOCX/PDF，不默认选第一项；空态引导下方上传并读取，未完整读取则明确阻断。显示两个文件名并提醒人工核对对应关系，沿原浅色/中文系统字体/表单与按钮，不换视觉系统、不引新依赖/图标/动画。已关联后原“更新读取状态”使用当前replacement.attachment_id，仍可明确改选另一原件。

选择只是本地草稿，直到明确确认才写。关联保留original.media_id/event_id与task expected_revision，file name/mime/hash/attachment_id/精确parse_revision全部从当前材料及parse响应构造，不相信文件名自动对应。只有readable且DOCX原有三视图/PDF original准确parser才ready，沿既有服务最终同CID/原件/parse/冻结/CAS/fence校验；不新增DTO/schema或后端权限捷径。

## 交互与并发合同

- 任意await后复核CID/epoch、当前任务及revision、材料快照和选择；切换、loading、dispose、撤权、同CID材料变化使旧异步结果失效，不向新对话/旧任务提交。
- 材料变化使未提交的选择失效并明确提示，跨CID/撤权清除保护视图；hasPending包含尚未提交的选择，busy/readonly/frozen/pending状态正确禁用。
- 新关联操作NETWORK_UNKNOWN后，复用现有task GET及media_resolutions历史，只查询精确expected_revision+1、event/media/action/replacement的保存结果，不再PATCH。未找到只保留待查询，不凭当前latest状态猜成功；既有其他task操作行为不改。关联成功和后续刷新失败分别处理。
- 文件名/正文仅textContent；每项选择可键盘操作、focus沿现式，窄窗口无横向溢出。无新模型/审查/下载解密/外发，后端仍synthetic-only。

## 分工与验收

- [ ] 前端代理仅assistant-tasks.mjs与新Node行为测试，先有效RED和输入SHA，再最小实现；若确需小样式只改task-media局部。先读craft-floor；不写根状态/Git/记忆。
- [ ] root负责计划、独立合成FastAPI/Chromium功能及1280/360两视口一次批量视觉检查、回归/证据/状态/Git。必要修复后至多一轮视觉确认，不循环抛光。
- [ ] 后端代理复核并补实际HTTP的同CID resolve/外CID、伪hash/解析版本、陈旧CAS/冻结/恢复拒绝矩阵；产品后端不改，不把原有绿测当新增功能RED。
- [ ] 覆盖DOCX/PDF明确关联、无默认选择、空/未读/partial/foreign parser、同名不自动配对、旧replacement更新、双击与异步竞态、未知提交只GET、当前权限及原收件不覆盖。Node全关联、适量Python关联、四开发门，按不同ID计数不累加重复；分组前冻结产品与测试输入。
- [ ] 未写产品者独立Spec/Standards复核和证据核算。仅提交本轮授权源/文档/独立合成样本；fetch后正常推送并核SHA/tree，不强推。状态区分源码/既有测试/本轮实测/未实现。

真实微信账号/合同外发/产品模型/付费调用保持关闭；可信微信、transport/下载解密/E有限期授权及pending descriptor列表仍待。0.4.1不更新；全仓长进程/安装版未验记NOT_RUN，WIN-PATH-02/原生AV保持OPEN。收尾三端按AGENTS实际回执，HumanLayer限长pending不得冒称同步成功。
