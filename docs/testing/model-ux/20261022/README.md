# 对话页模型 UX 小片证据（2026-10-22）

执行合同：[docs/plans/2026-10-22-model-ux.md](../../plans/2026-10-22-model-ux.md)。
基线：`8c609ac`。起因：所有者反馈"API 已配置但发送按钮灰色"，并直接指令两项 UX 变更。

## 排查结论（发送按钮灰色）

- 密钥已保存（本机 OS 保护存储有 deepseek.bin）、后端存活、api.deepseek.com 直连可达、当日 runs/attempts/conversations 全 0（发送从未到达后端）。
- 根因：模型"启用"为后端进程内存态，重启即失效；用户在旧进程配置后重启，新进程处于"本次运行未配置"。capability 拉取需要已保存草稿；设置返回路径本就会整页重载，本片另补窗口焦点回来时自动重拉（`focus → refreshGeneration`）。

## 变更内容（三件套）

1. **自动配置（所有者明确要求的安全姿态变更）**：`desktop-settings.json` 新增严格校验的 `model` 键；设置页配置成功持久化、显式停用清除、换密钥不清除；后端就绪即用已存密钥自动恢复所选模型，失败安静回退；恢复副本永不自动配置；Jev 不参与。每次发送的原生确认窗、单次 lease、会话绑定、120 秒有效期全部不变。
2. **对话页切换模型按钮**：新 `model-bridge.cjs`（两个 IPC，仅对话页主 frame/ready/非恢复副本可调）；`#switch-model` 位于「保存草稿」左侧，无桥时隐藏；切换成功后自动重算 capability。
3. **capability 焦点刷新**：窗口重新获得焦点时自动重拉生成条件。

## 验证结果

| 验证 | 结果 | 证据 |
| --- | --- | --- |
| 前端全套件（新增渲染 2 项：按钮矩阵、模板位置） | 68 passed / 0 failed | [frontend-suite.log](frontend-suite.log) |
| 桌面全套件（新增 model-bridge 5 项、导航更新 2 项旧语义 + 新增 2 项；桥键断言同步） | 270 passed / 0 failed | [desktop-suite.log](desktop-suite.log) |
| 四项工程门禁 | 均 exit 0 | [门禁1](gate-1.log)、[2](gate-2.log)、[3](gate-3.log)、[4](gate-4.log) |

Python 后端零改动（`git diff` 可证），无需关联 pytest 家族复跑。

## 开发过程修正记录

- `beforeCredentialChange` 曾一并清除持久化选择，导致"换密钥后重启不再自动配置"——违背所有者意图，改为仅显式停用清除；对应测试（渲染进程崩溃→换密钥→重启仍恢复配置）按新语义通过。
- 自动配置由 fire-and-forget 改为 `await`（消除测试与真实启动的竞态）。
- **推送后真实启动回归（当日修复）**：settings 的 `model` 键被展开进 `backend.start` 参数，而 `desktop_entry.py` 启动参数严格白名单不含 `model` → `BACKEND_REJECTED`，后端拉不起来。修复：main.cjs 传参前剔除 `model` 键（该键纯属桌面侧持久化）；model-settings-navigation 夹具 `Backend.start` 记录参数并新增断言"start 参数不得含 model 键"防回归。修复后桌面全套件 270/270；真实启动验证：python desktop_entry 进程拉起、回环端口监听正常（[desktop-suite-after-hotfix.log](desktop-suite-after-hotfix.log)）。

## 边界

无 schema/依赖变更；每次发送仍逐次原生确认；密钥不落任何文件（设置文件只存模型名）；安装版 0.4.1 不变。
