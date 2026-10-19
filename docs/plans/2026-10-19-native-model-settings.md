# CH-04G 日常主模型设置接线

承接已批准 v2.1 和 CH-04F；本片完成原生设置的配置生命周期，下一片 CH-04H 再完成具体发送的原生确认。两者沿用同一私有控制协议，不增加 HTTP 授权端点。配置成功只能称“本次运行已配置，尚未授权发送”，不称真实联网已验证。

## 本片边界与设计

- 继续 Electron / FastAPI / Jinja2。页面沿用已有中文、系统字体、浅色工作面；在原模型设置中区分密钥存储和本次运行配置。保存密钥不自动配置，配置不创建授权或调用模型。
- 独立 `desktop/model-session.cjs` 管理配置生命周期和固定供应商参数；`model-settings.cjs` 只做可信设置页 IPC、短事务与固定结果投影；`setup-model.js` 接管模型设置交互；main 仅装配与管理后端寿命。
- 本机凭据只通过已有 `withSecret` 回调交给已有 `Backend.configureModel`。不加入命令行、普通设置文件、渲染器回传、日志或备份。每次配置装配独立版本，重启后回到未配置。
- 打开模型设置保留正在运行的后端；返回时回到之前的可信本机页面。备份/恢复和切换工作区仍停止原后台。进入设置前尊重现有未保存内容拦截。退出、后台故障、进程替换使配置展示失效。
- 保存/移除密钥前先撤掉当前后端配置。撤掉失败必须关闭自有后台并返回固定失败，不能继续保存后仍让旧密钥生效。配置失败不能留下已知旧配置或假成功。
- IPC 继续只允许原窗口、主框架、精确设置页和正确状态；共享忙碌锁拒绝重入。await 后复核窗口/后台代次，迟到结果不更新新页面或新进程状态。恢复副本只能存取凭据，不能配置生成。
- 不读取实际用户密钥，不使用真实合同，不改变安装版或法律库。所有实测采用独立中文路径、合成密钥及本机测试环境。

## 固定供应商目录

2026-10-19 核对 [DeepSeek 官方价格页](https://api-docs.deepseek.com/quick_start/pricing/)：当前接受 `deepseek-flash` 和 `deepseek-v4-pro`；采用繁忙时段、缓存未命中的输入/输出标价，分别为每百万 token 0.3/1.2 USD 与 1.32/3.96 USD。这是配置估算依据，不保证实际账单或账号模型可用；未调用账号接口。固定 HTTPS 接收方仍由已有 Python provider 控制。

本片预设沿用输入上限 65,536 bytes、输出上限 4,096 tokens、超时 30 秒。价格用十进制字符串。界面显示接收方、模型和估算依据，不由渲染器提供任意端点、密钥引用、模型配置、价格、预算或批准。

## 接口约定

- 保留 `desktop:model-status/save/remove` 及其 `{status,code?}` 返回。
- 增加 `desktop:model-runtime-status`、`desktop:model-configure(modelId)`、`desktop:model-disable`；返回 `{ok, runtime:{state,model}, code?}`，state 为 unavailable/unconfigured/configured，model 仅为固定模型 ID 或 null。不返回秘密、配置摘要或授权版本。
- main 将 `createModelSession({store,getBackend,onFailure})` 交给 `registerModelSettings({...,runtime})`。getBackend 只返回当前已启动且非恢复副本的自有后端。会话模块只保存配置元数据及对应后端对象，不保存明文密钥。
- 会话 API：`status()`、`configure(modelId)`、`disable()`、`beforeCredentialChange()`；最后一项失败时必须阻止密钥存储写入。onFailure 在必要时停止对应后端并回到错误页。
- preload 增加 modelRuntimeStatus/modelConfigure/modelDisable；不提供通用 IPC 或读取密钥能力。

## 实施与证据

1. 先补会话/IPC生命周期失败测试，再实现固定目录、配置/停用和替换前撤销。
2. 模型界面拆分、状态文案、键盘与窄窗；不得扩大原 setup.js。
3. main 接线与保留服务的返回流程，验证备份和恢复仍停止后台。
4. 独立审阅权限、异步竞争、密钥边界和 UI 状态；运行对应 Node 测试。
5. 实际 Windows Electron + 实际 Python 后端 + Windows safeStorage：设置页保存/配置/切换/停用/替换/重启；回到首页 PID 与会话不变、能力仍 unapproved、POST 拒绝，无外部请求。页面缩放与窄窗截图、无日志泄漏、源码稳定摘要。
6. 维护打包白名单和未安装构建路径；本片若不改 Python，复用 CH-04F 冻结后端，不因 UI 改动无差别重跑整个回归或重新构建。
7. 更新 TASK_STATUS、接续计划和 Obsidian，保存实际数量及退出码，本地提交。

## 后续 CH-04H

可信主进程从自有会话和后端取得当前草稿，展示接收方、确切内容与单次费用边界，用户明确确认后才调用 CH-04F authorize；再由既有首页固定请求和队列提交。重启、切换草稿/案件/配置、取消和未知响应不自动重试或继承批准。此功能不能由本片“配置成功”代替。

## 本片执行结果（2026-10-19）

固定目录内联于model-session，未增加catalog依赖。IPC除isAllowed入口资格外，使用captureGuard绑定文档epoch，在await之后与后台身份一起复核。setup.js从98行缩至54行；模型界面逻辑独立。主进程使用activeBackend绑定实际工作区/实例/接收origin，返回地址与该对象绑定，设置页保留运行服务。独立复核发现renderer崩溃时原服务未停止；现错误恢复持忙碌锁等待其关闭（或既有关闭Promise），正式测试与真实崩溃场景均已关闭该问题。

106 Node、四开发门通过，470验证输入稳定；独立12探针+8正式导航回归通过，后8项包含在106内。真实Windows Electron源后端8组与冻结后端8组通过，各175输入稳定；复用CH-04F冻结EXE，212构建输入与其摘要一致。0实际模型调用；配置仍未授权。未重新打安装器，无包体或RSS改善声明。证据与失败历史见[阶段记录](../testing/native-model-settings/20261019/README.md)。
