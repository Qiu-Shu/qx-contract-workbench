# CH-05D2：同窗独立辅助许可实测

2026-10-20，基线 `a1ecd7e7d06112e228719586e4d35fe65a906036`。本片复用原生确认窗口及既有两份会话生命周期：主模型与 TypeSafe 的接收方、用途、输入和程序预算分别表达；辅助默认未选，拒绝辅助仍可继续获准的主流程。生产装配不传 `judgeBudget`，真实辅助发送仍关闭；合成预算只在未打包的测试 observer 中注入。[实施记录](../../../plans/2026-10-20-jev-confirmation.md)

## 实际执行

所有下列最终命令退出0。窗口/会话/编排目标分别21/62/30项被最终240项包含，不相加。有效RED分别保留旧11通过新8失败、16失败、旧20通过新8失败的原始日志；内外租约末检查反例及补偿另有独立设计探针。

| 执行 | 实际结果 | 证据 |
| --- | --- | --- |
| `node --test desktop/tests/*.test.cjs` | 240/240通过；0失败、取消、跳过；5.360秒，37份输入前后相同 | [记录](node-all.json) · [日志](node-all.log) |
| 四项开发检查 | schema、默认关闭、来源及依赖开发模式均exit0 | gate-1至gate-4的JSON及log |
| Windows源码 `--judge-closed` | 6组：配置Jev但不注入预算，辅助禁用；Main 1 POST、Jev 0，历史刷新不重发 | [实测](default-closed-ui/report.json) |
| Windows源码 `--judge` | 8组：先Main-only，再独立新文字明确双选；精确回环顺序Main、Jev、Main，合计Main2/Jev1；同run完整hash、独立预留、费用unknown、内部待核及不重发均核对 | [实测](source-ui/report.json) |
| Windows冻结 `--judge --frozen …` | 5组：当前Electron确认窗→旧已验冻结后端，Main/Jev各一次私有授权后各停用；generations提交0，八类业务表均0 | [实测](frozen-ui/report.json) |
| 独立复核 | Standards 0待修，另4个边界探针exit0；Spec静态0未解决发现 | [Standards](standards-review.md) · [Spec](spec-review.md) |
| WorkBuddy本轮 | 实际连接、指定4文件Read完成，无写入/执行/外查；建议经过统筹纠偏 | [回执及采用边界](workbuddy-review.json) |

三种UI执行各自绑定510份输入，前后相同；开发只用独立合成账户、文字和凭据。脚本本轮顺序执行命令见[driver](driver.md)，输出目录分别为 `.local/jev-confirm-20261020/default-closed-ui`、`source-ui`、`frozen-ui`。实际 Electron 44.8.0/Windows 本机，不是纯页面截图模拟。源码tripwire仅观测HTTPX/HTTPX2精确回环发送，未宣称全进程网络零；冻结网络未做全进程观测，不称冻结供应商执行成功。真实供应商调用未请求。

## 界面与失败边界

统筹实际查看了源码初始、100/150/200%应用缩放、双选、默认关闭及冻结选择共7张截图：中文文字可读，长文保留独立滚动，控件不横向溢出；缩放后主窗口需纵向滚动到操作区，取消/确认均可达。脚本另验默认取消焦点、键盘Enter取消、原草稿保留、字面script文本及确认期间草稿变化拒绝。应用缩放不等同于切换Windows系统DPI或第二台机器验收。Impeccable Operate既有界面检查运行一次，detect输出空列表；无需追加视觉改动。

授权顺序为主先辅后；明确辅助拒绝可跳过，未知回执停止捕获后台。末次异步身份检查保留在双租约内；内层辅助许可已释放而外层末检查失败时，等待停止原后台并拒绝成功，不影响替换后台。产品保持旧主模型四字段/布尔窗口契约兼容。完整文字、当前版本、会话和权限仍由后端重验；没有增加普通页面预算入口或新协议/表/依赖。

## 构建复用与边界

本片Python产品及打包资源未变，逐项核对D1构建记录中的220份后端相关仓库输入相同，复用冻结exe SHA256 `564a347488b4930f5928851c44571e2e8ecaa5f1ebefdbe2b195654a07271f07`。[复用核对](backend-reuse.json)并非完整第三方闭包证明；本轮未重打包、未测总体启动/内存，没有重复跑D1 Python目标或历史全套。

真实账户许可、价目来源和可接受预算未落实，不能由本次0.02合成预留替代；预留不是供应商收费上限。未做新安装器或更新安装版0.4.1，未修改真实材料/法库、Aliyun或网盘年份。自动档案、白名单钩子与完整业务技能仍待后续。

只白名单归档合成工程记录；运行DB、DPAPI密文、完整测试资料目录、依赖与exe留本机。`final-product-test-inputs.json`绑定最终工作树原始字节，Git允许CRLF→LF的文本规范化另有提交前核对。manifest保存本目录其余文件SHA256，不包含自身；Spec中的计划SHA对应实测结果追加前版本，产品与测试输入未变。
