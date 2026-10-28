# 读取更新后的桌面验收接续

日期：2026-10-28。基线 `154ec10`，分支 `codex/contract-review-v2`；开工 fetch 后本地与远端无差异。已读取 `8682990` 统一聊天/材料授权、`154ec10` 离线评测，以及工作区现有 0.5.1 打包、统一样式和聊天显示改动。其他任务的改动与原始测试目录保留，本次不一并提交。

## 原因及最小修复

旧 `desktop/tests/acceptance.cjs` 登录后直接寻找“合同审查/合同工作台”链接。新版登录进入 `/assistant`，该旧独立入口已取消，脚本因此超时。新增分支先确认聊天输入框可见，经“工作区与接待”进入原案件回归；原 `/workspace` 路径继续可用。未删改建案、事实、导出或重启断言，未改产品代码。统一聊天合同流程由已有 `unified-business.cjs` 单独复验。

## 本轮实测

使用本项目 `.venv/Lib/site-packages/playwright/driver/package` 中的 Electron 驱动。仅对验收子进程清空 `ELECTRON_RUN_AS_NODE`、`NODE_OPTIONS`，未改系统环境。两个脚本都指定独立 `.local/unified-mvp/20261028-*` 资料目录和当前 `dist/desktop/win-unpacked/群兴法律工作台验证版.exe`，未安装或替换用户正在使用的程序。

| 命令与范围 | 结果 |
|---|---|
| `node desktop/tests/acceptance.cjs .local/unified-mvp/20261028-fresh-red <exe>`，修复前 | 退出 1；1 项完成后寻找旧链接超时 30 秒，实际失败重现 |
| 同脚本，修复后输出 `20261028-fresh-green` | 退出 0；15 项通过：首次设置/登录、聊天首页、原建案/原文/事实/意见/导出、后端停止和重启保留；页面错误 0 |
| `node desktop/tests/unified-business.cjs .local/unified-mvp/20261028-unified-current <exe>` | 退出 0；6 组通过：统一输入创建任务、分次材料保留任务、同窗建案/确认/模拟审查、重启保留；页面错误/浏览器外部请求/模型 POST 均 0 |
| `node --test scripts/test_assistant_generation_render.mjs` | 退出 0；19 项通过，含当前未提交显示改动的未知费用状态与来源定位；没有将这些改动归为本次实现 |
| 独立审阅 | Standards、Spec 各 0 项可行动问题；审阅只覆盖本次 7 行验收路径修改 |

当前包内 `package.json` 版本为 **0.5.1**，验收前后 `app.asar` SHA-256 均为 `7120ea328188dd2b112f02357f8a2f8374d9c006cf80ec9f6f72185443489ac0`。包包含已有未提交界面更新，不能以当前 Git 提交代替该打包输入身份。Electron 可执行文件资源版本 44.8.0 是运行时版本，不作为产品版本。

原始报告保留在上述本机目录；摘要：

- RED `report.json`：`e5d17dab74b0f8210a0715c763c40b3a03c39cb48ce0c3a88fdf9b93d56af97c`。
- GREEN `report.json`：`bef5cc6531467e24106efcecc93318f041fa47d2fd77e2a1e3fa9d2a313853fa`。
- 统一聊天 `unified-business-report.json`：`a0e66465d10a5085a334179925f3e8665dec1fb0ac2637dd6ac5fff1c054061a`。

截图、数据库、原件和完整临时资料目录不进入本次提交。原案件验收记录 100%/125%/150% 应用缩放下的页面宽度均未超过窗口；这不是实体显示器缩放或物理输入法验收。

## 边界与接续

以上为现有打包应用、隔离虚构资料的验收，不是 NSIS 安装/卸载、真实 DeepSeek/WorkBuddy、微信账号或法律质量验收；本轮未重跑完整 Python 套件，历史 6969 项通过不冒充本轮结果。WIN-PATH-02/原生崩溃保持未关闭。材料 AI 的跨轮语境、真实模型配置和微信联调仍须逐项验证，不能由本轮模拟合同通过推定完成。
