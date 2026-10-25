# D2g4 独立复核与根核查

固定基线5f3353c。用户AGENTS.md在开始前已修改，哈希保持不变，未纳入提交。产品只有新leaf、旧授权互锁、主入口导航、原模板/4条CSS，以及app.py新文件的精确静态白名单；未改后端业务、DTO/schema、权限、收件guard或依赖。

## 独立Spec/Standards：同一审查者两轴

独立代理d2g3_head_atomic先编写35个行为用例，初始缺模块失败；随后真实Promise时序及UTC回执负例发现6类实际失败。root修复后，该代理冻结输入复跑41 Node全部通过，另运行既有HTTP导入图与新Node桥2项通过、旧授权22 Node通过，均未计作额外不同测试。代理未改产品或其他测试，只写自己负责的新Node文件和本地审查记录。

Spec：明确保存、两阶段未知只查、固定请求而非head推断、scope/CAS、晚到回调、当前权限/稳定性复核、恢复readonly及导航守卫，最终0确认阻断。

Standards：复用当前API传输/框架与本机绑定服务，状态留在单一leaf而不另造通用引擎；控制器与后端仍是当前权限来源。textContent呈现动态标题/理由，4条CSS作用域局部，无外部字体、图片、依赖或模型请求。最终0确认违规。详情及9个审查时输入散列见independent-review.json；计划完成标记随后由root更新，产品/测试8个输入未变。

该代理未独立跑浏览器或审阅新浏览器脚本；真实浏览器与脚本验证属于root。当前宿主拒绝激活第二Standards代理（agent thread limit reached），本片只有一名独立审查者的两轴，不称两个独立代理。本轮WorkBuddy未运行，未重试此前Bash被拒任务。

## root复核与实际边界

root读取所有diff并复跑最终229不同Python、233 Node，两组真实本机浏览器与四门。首轮浏览器揭示静态allowlist遗漏，使用已有HTTP导入图先复现404再补精确文件名。新浏览器脚本复用旧本机服务/合成账号和qxbakAPI，所有网络限回环、原始数据库/备份/截图留.local，未向Git提交。两个独立事务可能只完成binding，页面不会宣称历史已保存；已得到合法历史回执后若状态刷新失败，只报告状态未更新，不误造未知写/重发。

前端scope校验是展示守卫，不代替domain DTO与后端当前ACL/CAS/fence；历史记录摘要在前端是不透明值，只核scope摘要、请求及前代CAS绑定。目标清单显示标题与版本属于当前用户已授权会话，后端写时再次核对；外部并发修改可能409，页面要求重读，不自动提交。

## 补完D2g3的历史欠审

本轮开始时，独立代理d2g2_standards_review完成dee54ea→d6627de四产品文件静态Standards复核：集中DTO、同事务head/history/latest权限/checkpoint、CID归属与精确恢复GET、无schema/运行时扩张均符合仓库规则，0确认违规。它未运行测试；不是本片D2g4第二审查者。旧D2g3当轮NOT_RUN描述仍保留，以本轮补审事实修正当前欠办状态。

## 本轮最终冻结的14个验证输入

- `src/cn_contract/web/app.py`：`2b6d0a6387cc6b35f7b3ed460688a52306c7572411dc2822086ab431ad0c9d14`
- `src/cn_contract/web/static/assistant-weixin-generations.mjs`：`ffbec4f241a3aaaadb13ed553c9a68dc60d956b3e69bcb466c652fbc2e0bdf75`
- `src/cn_contract/web/static/assistant-weixin.mjs`：`cd85ade8d9d5875a7e9a9e3373b89aace9668ff79de2121dc3e95eddd9dd7fa0`
- `src/cn_contract/web/static/assistant.mjs`：`f77a8ee5f06d33a6447373c53945ca745607983bbb274db609b870e31829406e`
- `src/cn_contract/web/static/assistant.css`：`462f0bf64736f8866eb6bfa55fb33215ddead203fd2abecf5e0fc09bbb438aa7`
- `src/cn_contract/web/templates/assistant.html`：`42903dbd8d6c6420f3492bec7f2472e3fac3603b4614960cf2391ef97c14a965`
- `scripts/test_assistant_weixin_generations.mjs`：`f816fece130349fed4d3dfe7bb7e4a4d598388d49965f35c478de134479f70fc`
- `scripts/validate_weixin_generation_browser.py`：`2c4c3a9b30b6f65063a684e2613ea2f7fb2ff7e7fa169ad0b3b0ec5d4b9cc735`
- `tests/integration/test_assistant_frontend.py`：`ac0445dab0a8b320dcf0789d2b68170fb750baecec7adbf5cabe940f546a012a`
- `src/cn_contract/weixin_inbox/generations.py`：`4d7e82d8b8dd1b7cca030545e506c937407870c802efe927234e2cf18bf70004`
- `src/cn_contract/weixin_inbox/conversation.py`：`de25074489e652d20493850763559ea3fe36ca2ba35381cb0cfdba5ba752e96f`
- `src/cn_contract/web/weixin_authorization.py`：`1a283a94183a38204508f8117ae8343540f2edca2f18049ca3ed50c4b1c2bd36`
- `src/cn_contract/web/recovery.py`：`db9361d5a5944bc51474635844b6e65656d2c9c171f824efd6e1d10e8c39230f`
- `src/cn_contract/domain.py`：`99ea0d5793dfecdc84fe1f3379dd6562850e56a02750aa4dcd12e32b50c4eebb`
