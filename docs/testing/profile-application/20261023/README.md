# CH-07C2c：档案用途的后端应用入口

基线 `3d0e1859041572ed9c574e7a917afd044aedc6bf`，2026-10-23 Windows本机、独立合成材料。

CH-07C2c已完成档案用途的后端应用入口：预览重建当前草稿及保存计划，私有管道许可固定一次调用，HTTP登记与原任务队列复用；已登记请求只找回，许可失效后用GET读取，不重发。完整Python回归4,393项通过、0失败/错误/跳过，四开发门通过，558份输入稳定；独立Spec9项、Standards10项通过。实际本机子进程/管道/HTTP合成链验证恰好一次回环调用。桌面用途确认与档案侧栏待接，安装版0.4.1及WIN-PATH-02开放状态不变。

## 实现与验证

- [执行合同](../../../plans/2026-10-23-profile-application.md)：7个产品文件，业务DTO保持domain.py集中；两个独立模块承载档案许可和HTTP用途，旧入口仅接线。没有新依赖、数据库结构、第二队列或第二次提炼模型调用；Jev不参与该分支。
- 完整配置Python套件 **4,393 passed / 0 failed / 0 errors / 0 skipped**，退出码0，验证器记录3312.391秒。单次全套已包含新合同8项、HTTP38项、原生42项和真实子进程1项，不将前期开发通过数或独立探针叠加。[实际命令/前后摘要/退出码](target-verification.json)、[原始日志](target.log)、[JUnit](target.xml)。D盘全新临时目录复用已有独立DuckDB运行时，不访问真实法库。
- schema、默认关闭、来源development、运行依赖development四门均退出0，命令及日志在本目录。源码、测试和配置共558份输入前后一致，最终文件另经[摘要清单](accepted-inputs.json)核对。
- 新增真实Windows子进程测试通过私有stdin控制管道配置和许可，并经实际TCP登录、草稿、预览、登记、档案/接待保存与历史回查。授权前拒绝，重复POST、GET及native existing不增加请求；供应商**1次回环、0外部**，完整发送字节与预览一致，EOF退出码0。此测试也包含在本次全套；早期单项记录见[日志](process-green-02.log)。这是源码后台进程，未测试Electron窗口或冻结安装器。
- 独立[Spec9项](spec-review/report.md)及[Standards10项](standards-review/report.md)通过、开放发现0；分别16和265份输入稳定（均包含7个产品文件）。前者核对当前权限、精确重放、提交后派发；后者实测排队后撤权/重配、DTO变异和重复JSON键拒绝。只读[计划复核](plan-review/report.md)明确POST与GET找回界线。

## 开发期失败记录

缺DTO、缺HTTP/原生入口的有效失败验证保留在contract-red、development-http/red、development-native/red-functional与process-red中。其他早期失败包括原生配置/用户角色夹具、C盘磁盘预算前提，以及进程历史GET遗漏message_id；它们属于测试设置问题，不冒充产品缺陷或静默删除。

原生作者扩展回归曾135项中126通过、1夹具失败、8个磁盘前提错误；换D盘后134通过、1夹具失败；最后原生42项中41通过，修正角色夹具后原单项通过。HTTP作者最终38项通过。独立Standards重复JSON键探针补齐其他合法字段后重新验证10项通过。各原始命令、退出码及日志分别保留在development-*和standards-review；这些历史计数不与最终全套相加，也不冒称当时单次全绿。

## 边界与下一步

预览不授予许可、不写业务记录；发送前后均核验当前权限、版本及保存目标。native existing仅表示已有登记，不代表新许可；原许可失效后重复POST拒绝，客户端应使用既有GET找回。档案候选仍待律师核对，不自动确认事实或覆盖人工更正。

下一片复用现有Electron确认窗接用途和保存目标，再接档案侧栏；当前没有律师可用的自动归档按钮。安装版仍0.4.1；本次全套通过不能证明WIN-PATH-02间歇目录拒绝访问已经修复。未访问真实材料、真实模型、F盘法库、云或未下载年份；无整机资源/新安装包结论。

WorkBuddy阶段开始与本轮接续均native_unavailable，未派发；独立复核由Codex子智能体完成。原始合成文本证据按逐文件白名单复制，未复制临时数据库或运行产物；[清单](evidence-manifest.json)记录每项摘要。GitHub同步以随后独立回执为准。
