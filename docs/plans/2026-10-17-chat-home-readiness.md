# 对话首页接线检查与下一切片

日期：2026-10-17。依据已批准的[完整规格](chat-first-architecture-v2.1.md)，下文保留实现前的接口检查。当前消息分页前提及 CH-02A 本机草稿首页已经实现并通过完整 2,094 项回归，见[实际证据](../testing/chat-home/20261017/README.md)；生成、SSE 消费、附件与档案面板仍待接通。原生模块采用 `.mjs`，下表 `.js` 是当时的拟议文件名，不代表两套并存实现。

## 已确定的组件取舍

保留Jinja、同源静态JavaScript与现有Electron。原生textarea负责输入；消息解析与清理采用固定制品的markdown-it、DOMPurify，真正开始渲染模型Markdown时再登记依赖、许可证与制品摘要。普通文字仍用textContent，不提前以HTML展示用户消息。

Deep Chat实测见[兼容证据](../testing/chat-ui-compat/20261017/README.md)。它在当前CSP下可适配，但未消除作用域、草稿版本、失败和重连状态；首版不加入该依赖。输入法试验用了合成浏览器事件，不等于Windows候选窗验收。

已在独立目录取得并实测markdown-it 15.0.3和DOMPurify 3.4.17浏览器制品，两脚本130,614字节，13组合成检查通过；尚未纳入产品。正式采用须登记两主包及五个内嵌依赖许可（含entities的BSD-2-Clause），固定制品与当前安全通告。见[制品准备](../testing/chat-render-compat/20261017/README.md)。当前Electron禁止新窗口及外部导航，保留href不等于可以点击外链；不能在渲染适配中静默放宽桌面策略。合成长URL表格虽无整页溢出但首列已过窄，产品表格需要单独验证可读列宽与局部横向滚动。

## 当前代码接线事实

2026-10-17接续更新：下表原先识别的两个读取缺口已按[分页计划](2026-10-17-assistant-history.md)实现并完成218项目标／关联及实际冻结验证，见[证据](../testing/chat-history/20261017/README.md)。HTTP GET、创建重放及草稿响应均有界；`read_conversation`的旧服务默认仍保留完整读取。首页应消费新`AssistantConversationPageView`的`next_before`与`latest_run`，未知发送响应按同对话request_id查找；不创建新任务猜测恢复。以下其余接线要求继续适用。

| 现有位置 | 已有能力与首页必须处理的差异 |
|---|---|
| `web/assistant.py` | 同源认证接口、严格DTO、取消与SSE。没有HTML页面，也没有主模型执行器 |
| `assistant/service.py::read_conversation_page` | HTTP已默认最多50条，向前游标必须属于当前对话；旧read_conversation仅供兼容调用 |
| `AssistantConversationPageView` | 包含持久草稿／版本、next_before及latest_run；重开从服务端找回任务，不依赖浏览器内存中的run_id |
| `AssistantDraftInput` / `AssistantMessageInput` | 字段为`content`、`expected_scope`、`expected_composer_revision`、`requested_skill`；不要照规格的概念例子错误发送`text`或`requested_skill_id` |
| `AssistantConversationPage` | `items`可能为空而`next_cursor`仍非空：关联权限过滤以扫描页为边界，必须保留继续加载入口 |
| `AssistantSkillCatalog` | 当前`generation_enabled=false`、`state=not_connected`。与最终设计的ready/setup_required/unavailable不同；只按实际值展示，不把卡片当可执行证明 |
| `assistant/service.py::_current` | 当前仅handling_lawyer／reviewing_lawyer可使用此切片；不能让新登录默认跳转使其他既有角色失去原入口，也不能通过卡片给助手角色增加律师权限 |
| `web/static/workbench.js`登录处理 | 固定跳转`/workspace`；新默认入口应有明确开关，只接受服务端限定的站内目标 |
| `web/app.py`静态资源端点 | 固定白名单；新增模块须逐项登记，不能为方便改成任意路径读取 |
| `web/recovery.py` | 已允许精确assistant API只读路径；HTML新页仍需单独登记，恢复副本不启用保存／发送／上传 |

## 首页之前补齐的两个读取边界

1. **有上限的历史读取。** 新增服务端消息分页，首批最多50条，按消息持久顺序从最近一页向前读取；游标必须核对同一对话归属。保持旧服务调用的兼容性，不能修改历史记录或用offset假定并发消息不存在。目标测试覆盖101条合成消息、前后边界、同名/同revision消息、外案游标、读取期间新增消息，以及完整历史无重复遗漏。
2. **重开页面找回原任务。** 由已授权的对话快照返回当前／最近运行定位；不查询另一对话的运行，不把任务状态存入localStorage来充当事实来源。发送请求结果未知时保存原request_id与完整请求，先核对服务端；必要重放只能同键同内容。页面重开只是读取，不重新POST消息。目标测试覆盖已登记但响应断开、queued/cancelled/blocked、恢复副本及撤权。

以上使用现有表，不为两个只读投影额外开库或改迁移。具体DTO仍只在domain.py定义。新增读取路由继续执行当前用户/工作区/关联对象授权。

## 页面模块职责

| 拟新增文件（均相对`src/cn_contract/web/`） | 单一职责 |
|---|---|
| `templates/assistant.html` | 语义结构：232px侧栏、最大840px对话面、四卡/更多、标注名称的输入与状态区 |
| `static/assistant.css` | 现有浅色设计值、中文16px/1.7、输入112–240px、焦点、1000/720px适配；无联网字体 |
| `static/assistant-state.js` | 当前对话快照、编辑版本、请求身份、选择技能；不依赖DOM或网络 |
| `static/assistant-api.js` | 同源请求、错误白名单、事件订阅/关闭；不包含材料解析或业务判断 |
| `static/assistant-render.js` | 安全呈现和增量更新；不改变作用域，不整页重建输入框 |
| `static/assistant-composer.js` | IME/Enter/Shift+Enter、技能焦点和输入保留；不直接调用数据库/模型 |
| `static/assistant.js` | 连接上述职责，处理页面生命周期；不扩展成另一份workbench.js |

模块按实际需要写小接口，不先造通用前端框架。只新增必要的app装配，旧合同、接待、法库页面继续使用现有入口。

## 必须验的状态顺序

- 空白首页不创建空记录；首个非空草稿才建conversation。创建响应未知时不换request_id制造第二条。
- 保存请求单通道串行，发送绑定已知scope/composer版本。较旧保存返回不覆盖用户继续输入；冲突保留两份文字，让用户核对，不静默采用较新服务端草稿。
- 点击技能只选中，不发送；文字和已选材料保持。若填示例，只能在输入为空且不处于组合输入时进行。
- 不将未接入执行器的queued记录描述成正在生成。当前首页验证可保存草稿、看历史、取消旧排队任务；发送和上传依真实后端能力启用。最终功能要到相应CH接通后验证。
- 切换对话时先处理未保存草稿；以递增页面身份丢弃旧GET/SSE/保存回执，不让旧案内容出现在新案。请求取消不是远端运行已取消。
- SSE以既有run_id和最后seq续读；重复/乱序不重复呈现。access.revoked立即清掉已撤权呈现并关闭流；stream.reset重新读快照，不能重新生成。
- 关闭页/登出时有未保存或结果未知输入要明确提示。不能使用sendBeacon绕过认证/CSRF，也不把案件正文写入浏览器持久缓存。

## 实施验证与完成口径

先完成读取边界的小切片并验证，再做页面；页面使用独立合成账号和材料。用现有本机Chromium验证键盘、组合输入事件、快速切案迟到回执、网络失败、刷新恢复、1366×768及窄窗口、错误/焦点、CSP与外部请求。物理Windows IME与系统125%/150%DPI单独记录实际验证；浏览器缩放不能替代系统DPI。

在候选冻结后端与现有Electron壳中验证新页资源装配与旧页入口。首页单独通过不意味着模型、Jev、附件、档案投影或整个CH-02至CH-11完成；与对应服务接通后再逐项关闭缺口。每切片保留独立复核、实际证据和本地提交，不重复跑上一切片已完成的全量导入或测试。
