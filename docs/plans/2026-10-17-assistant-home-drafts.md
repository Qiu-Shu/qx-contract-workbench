# CH-02A：可用的对话首页与本机草稿

在e46ce3c读取前提之上落实v2.1已经确认的首页，不重新选风格或框架。当前能力目录明确generation_enabled=false，首片实际功能为自动保存草稿、技能选择、分页历史、最近任务查看／取消及恢复只读；发送与附件呈现明确不可用原因。此片不是完整聊天生成／附件／Jev验收。保持Enter发送／Shift+Enter换行契约并防中文选字误发，未接执行器时Enter不产生排队假任务。普通消息以textContent呈现，Markdown依赖等生成链接通时采用。

## 边界与分工

- 页面后端独立assistant_pages.py；现有app只装配并登记静态文件。native工作台显式开启assistant_home_enabled，其他构造默认关闭；登录后根据session的服务器限定home_url选择站内入口，其他角色保留工作区，恢复副本优先恢复页。两个HTML路由必须认证／律师角色及当前对话归属，不在页面内嵌正文。恢复仅放行精确/assistant及/assistant/UUID，编辑禁用。
- 原生ES模块按网络、状态、呈现、输入和装配拆分。没有浏览器持久正文缓存，无外部资源，无数据库／模型直连，无第二套会话。
- 状态模块负责单通道保存与版本：每次读取不影响正在输入文字；保存期间新输入保留，较旧回执只更新已保存基线，再串行保存新版本；失败保留文字且停止自动重试。创建结果未知保留原request_id，再次明确重试沿同键。草稿写入结果未知先读取核对，匹配同一scope及版本/content才认为已保存；冲突保持本机文字和服务器文字，显式选择后再保存，不自动覆盖。
- 切换／新建先完成当前保存，失败阻止切换；加载中禁编辑，递增页面代号使迟到读取不能污染当前对话。空白首页不建空记录。退出／刷新对未保存或未知结果提示。权限撤销立即清空不可访问的历史及输入。
- 历史按服务端游标加载，保留滚动；列表即使空但cursor非空仍有继续加载入口。最近任务直接显示持久状态，queued显示“已登记，尚未执行”，取消重新读取，不能以本地倒计时模拟进度。本片用手动刷新状态，无生成流；SSE消费随运行器接线另验。

## 前端文件及接口

HTML为assistant.html，CSS为assistant.css，五模块为assistant-{api,state,render,composer}.mjs和assistant.mjs。body数据属性conversationId、readonly、libraryEnabled均由模板生成。关键ID：sidebar、nav-toggle、new-conversation、conversation-list、more-conversations、account-name、logout、home-title、scope-label、history、older-messages、run-status、refresh-run、cancel-run、skill-cards、more-skills、selected-skill、clear-skill、composer-form、composer、add-material、send、save-draft、save-status、notice、conflict-panel、server-draft、keep-local、use-server、capability-details、body-size。动态内容使用textContent，textarea不被普通渲染重建。

API模块：request(path,{method,body})、getConversation(id,before)、createConversation(body)、saveDraft(id,body)、listConversations(cursor)、skills()、session()、cancelRun(id,body)。错误给出code/status，无直接展示未信任服务端消息。

状态createDraftController(api,{onChange,onConversation,uuid,readonly})返回对象：state（id/view/text/savedText/skill/status/error/conflict/dirty/loading），edit(text)、selectSkill(skill)、open(id)、newConversation()、save()、retry()、resolveConflict('local'|'server')、loadEarlier()、refresh()、cancel()、canLeave()、close()、revoke(error)。revoke仅处理401/403并清除状态及过期异步回执；普通错误不得清空草稿。onChange只通知渲染；onConversation在身份改变时更新当前URL。scope及草稿版本完全使用服务端快照；服务端未知写结果不得换ID。

## 验证

服务页面及角色／身份／恢复／资源白名单的实际HTTP检查；Node异步行为用延迟Promise模拟保存中继续输入、未知创建／保存、冲突、撤权和迟到读取，不只比字符串；真实浏览器批量核对桌面1366×768与窄窗口、键盘/合成IME、草稿重开、技能不发请求、XSS纯文本、分页/切换及网络失败。冻结候选后端与既有Electron壳复核资源与旧入口。物理中文候选窗、系统DPI与新安装器不能由浏览器合成事件替代。独立代码／视觉复核、阶段记录及本地提交，完整回归在该首页集成稳定后进行。
