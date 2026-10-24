# D2e 对话页本机收件授权入口实测（2026-10-24）

基线1ddf55a，按[实施合同](../../../plans/2026-10-24-weixin-desktop-authorization-d2e.md)把D2d服务接入现有模拟合同任务卡。沿用当前中文工作台、原生按钮和同源登录；本片没有微信远端身份认证、跨目标generation或新模型能力。

## 源码实现与边界

domain.py仅追加 `WeixinConversationAuthorizationView`；`weixin_inbox/conversation.py` 提供 `read_authorization / refresh_authorization / find_refresh`。从当前实际principal、CID owner/workspace及对象权限定位已存在的synthetic task binding/mapping，不创建账号/绑定。投影仅返回synthetic模式、当前/已授权scope、grant revision/hash及真实状态，不含bot/peer/account标识、理由、合同正文或密钥。当前案件或关联intake转案后的案件归档也拒绝读取；归档/恢复但无mapping时返回阻断态和空授权，不编造绑定。

三入口均在 `/api/assistant/conversations/{cid}/weixin-authorization`：GET当前投影；POST `/refresh` 显式使用原WeixinPeerRefreshInput；GET `/refreshes/by-request/{request_id}` 只查固定结果。POST解析有界JSON前后两次核同源/CSRF/当前对象权限与restore fence，CID→mapping由后端重取；外层事务结束后复用D2d独立BEGIN IMMEDIATE，内部再次核当前身份、scope、ACL/撤权。旧GET不构成授权，caller不能传account/mapping/actor绕过CID。GET成功零业务/审计新增；既有拒绝审计可能独立提交，不宣称拒绝路径绝对零写入。

`web/weixin_authorization.py:is_weixin_authorization_read_path` 与真实recovery middleware仅放行两个精确GET；POST和类似poll/额外路径继续409。静态模块及三routes在现有app注册，无公开微信poll/dispatch/账号创建端点，也不更改schema16或旧存储。

现有对话页任务卡新增“微信收件授权 · 离线测试”。仅refresh_required且当前页面可写、快照稳定时可点“更新本机授权”；scope目标变化、撤权、归档和恢复态不提供更新。`assistant-weixin.mjs` 使用CID/epoch/read序号拒迟到结果，权限撤销/关闭清理状态；scope变化只GET，不轮询或自动POST。正常切换/新建与离开保护保留未知授权；退出登录可清理，不锁住退出。回执须关联request、下一revision、前hash及完整scope，不能将任意200 JSON称已保存。NETWORK_UNKNOWN保留原request，只显示GET查找；查询None仍保持未知，不重发。scope/材料能力沿后端D2d规则，授权成功不表示合同已审查。

## 本轮实际验证

本机原始证据在 `.local/weixin-desktop-20261024/`；`verification-summary.json`绑定9份改变的产品源码、2份最终JUnit、Node报告和3组浏览器报告。浏览器另外绑定未改的accounts.py，共10份运行源码。以下计数互相独立，不把Node子测试加进Python去重数。

| 实际命令或目标 | 回执 | 结果 |
| --- | --- | --- |
| View DTO、31条HTTP、D2d DTO/服务、旧assistant及recovery/task守卫；精确节点见本机backend-notes | `backend-regression.xml` | `.venv/Scripts/python.exe -m pytest ... -q --tb=short --junitxml=...`；exit0，122 passed，48.04s |
| `tests/integration/test_assistant_frontend.py tests/integration/test_task_draft_routes.py tests/unit/test_domain.py` | `frontend-regression.xml` | `.venv/Scripts/python.exe -B -X utf8 -m pytest ... -q --tb=short --junitxml=...`；exit0，135 passed，23.51s |
| 14个 `scripts/test_assistant*.mjs`，含新授权22项 | `node-all.tap / node-all.json` | 现有bundled Node v24.22.1，`--test --test-reporter=tap`；exit0，192 passed，0 fail/cancelled/skipped/todo |
| 新授权真实浏览器全流程 | `browser-run2/browser-report.json`及exit/log | `.venv/Scripts/python.exe -B -X utf8 scripts/validate_weixin_authorization_browser.py --output .local/weixin-desktop-20261024/browser-run2`；exit0，8.56s |
| DOCX先指令旧任务闭环 | `regression-docx/report.json` | `scripts/validate_task_drafts_browser.py --output .local/weixin-desktop-20261024/regression-docx`，前缀同上；exit0，6.54s |
| PDF先材料旧任务闭环 | `regression-pdf/report.json` | 上述旧脚本另带 `--format pdf --order material-first --output .local/weixin-desktop-20261024/regression-pdf`；exit0，7.47s |

两份JUnit按classname/name去掉2个重复task route守卫，最终**9模块255个不同Python用例**通过，选中结果0失败/错误/跳过。Python前端包装测试还会调用11份Node脚本，这些重复运行不重复计入192；不是全仓单次测试。修改前baseline脚本也exit0，提供沿用界面实图和旧DOCX流程依据，不当作改后验收。

四开发门在最终源码上exit0：`-m cn_contract.cli schema --check`、`scripts/verify_defaults.py`、`scripts/verify_sources.py --mode development`、`scripts/verify_runtime_dependencies.py --mode development`，前缀 `.venv/Scripts/python.exe -B -X utf8`。13来源仍NOT_PRODUCTION_APPROVED，55 runtime+1 build、native_build_verified=false、network_calls=0。Impeccable单次机械detect覆盖HTML/CSS/新模块，exit0且返回[]；沿既有Operate视觉，未新增字体/图像/依赖/动效。

## 浏览器实际验收矩阵

| 场景 | 实际结果 |
| --- | --- |
| 未绑定、绑定GET及重载 | 无账号/映射/grant自动创建；初始grant0、授权POST0 |
| 第一注册合成DOCX上传 | scope真实失效；键盘聚焦+Enter明确更新，grant1、POST1；重载仍有效且不再POST |
| 第二不同注册合成DOCX上传与丢ACK | 路由fetch先让服务commit，再abort回执；页面显示未知，点击GET查到同request，最终grant恰2/浏览器POST恰2 |
| 真实qxbak恢复+attach_recovery | 恢复2个grant/2附件；页面restored_blocked且只读；固定回执GET200，负向refresh POST409，无新增grant |
| 公共peer撤权服务 | 原页面重新读取显示不可逆revoked，不能从此入口复活 |
| 桌面1280/窄窗口360 | 文字和操作可读、键盘可用、无横向溢出；两批已有截图核对后停止视觉迭代 |
| 新授权场景运行数量 | assistant/model_attempt/review/task execution等均0；外部浏览器请求0、pageerror0 |
| 旧DOCX/PDF两组 | 各2条事件→1草稿→1执行→人工事实确认→恰1个Mock结果，刷新不再审查；assistant_runs0、外部请求0、pageerror0 |

新授权场景没有poll/descriptor/dispatch，不能称实际微信收件联调；旧DOCX/PDF的Mock结果不能称真实模型。新授权场景零运行不概括为全部浏览器场景零Mock结果。完整断言、请求次数和源码SHA在验收脚本与本机报告中。

## 失败与独立复核

后端有效RED为缺View DTO27 failed、缺模块/route31 failed；首轮自动pytest ID含256KiB负载导致Windows临时路径setup错误，已改短ID，另修独立成员表名及先关闭旧app再重建恢复app的夹具，不把30 failed/2 errors算最终行为RED。Node先有missing module加载失败，落实现后首轮17 passed/1 failed是文案断言误用“更新”，改为实际“已保存”；随后真实不相关JSON回执反例18 passed/1 failed，补request/scope回执关联后GREEN，最终扩展22项含迟到/并发操作。首次Node原始输出见本聊天工具回执，最终完整TAP保存在本机；未虚构缺失日志文件。

浏览器首轮因脚本点击恢复页已禁用的能力按钮而失败，修为实际details summary；fence表名同步改为ops_restore_fences。只修验收脚本，第二轮完整通过，首轮失败log/report保留，不当作产品RED。独立review最先发现真实recovery读白名单接线缺口，已由精确predicate及真fence HTTP/真实恢复浏览器闭合。独立Node探针核对迟到POST跨CID不恢复旧状态、dispose后迟到读被忽略，POST仍1；最终源码与证据冻结复核另记本机review-notes。本轮未启动WorkBuddy新任务，未把上一轮中断复核计为通过。

## 尚未实现与NOT_RUN

跨目标/转案的显式generation、真实微信资格/可信远端绑定和transport、登录/轮询/下载解密/发送Outbox、产品真实模型/付费与E有限期授权仍待。机器人、真实合同外发、法律意见签发、新安装包、安装版Electron、全仓回归均NOT_RUN。安装版0.4.1、原生长进程崩溃及WIN-PATH-02继续开放；浏览器源码验收不等于安装版验证。运行SQLite未加密，qxbak加密不等于运行库加密。
