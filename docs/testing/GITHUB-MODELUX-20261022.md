# UX-01 对话页模型 UX 小片 GitHub 同步回执（2026-10-22）

- 仓库：`Qiu-Shu/qx-contract-workbench`（私有），分支 `codex/contract-review-v2`。
- 产品提交：`af0183d`「UX-01: in-place model switch, startup auto-configure, focus capability refresh」（13 改 + 4 新，含执行合同与证据目录）。
- 推送输出：`8c609ac..af0183d  codex/contract-review-v2 -> codex/contract-review-v2`（正常推送，未 force）。
- 远端核对：`git ls-remote origin codex/contract-review-v2` 返回 `af0183dec3994e533f64de3dba602752210833d0`，与本地 `git rev-parse HEAD` 逐字符一致。
- 敏感模式扫描：diff 与全部新增文件对真实密钥模式（sk-*/bearer）0 命中；settings 只持久化模型名，密钥仍在 OS 保护存储。
- 验证摘要：桌面全套件 270/270、前端全套件 68/68、四开发门 exit 0；Python 后端零改动。证据：[model-ux/20261022](model-ux/20261022/README.md)。
- 安全姿态变更说明：取消"每次运行手动配置本次运行"为所有者（宋萌律师）2026-10-22 直接指令；每次发送的原生确认窗逐次核对不变。
- 本回执为独立第二次提交，推送后同样以 ls-remote 核对为准。

## 追加：同日回归修复同步（hotfix）

- 修复提交：`c63336e`「UX-01 hotfix: strip desktop-only model key from backend.start params」——推送后真实启动发现 settings 的 `model` 键泄漏进 backend.start 参数，触发 `desktop_entry.py` 启动参数白名单 `BACKEND_REJECTED`，后端拉不起来；修复为传参前剔除该桌面侧键，并在 model-settings-navigation 夹具加防回归断言。
- 验证：桌面全套件复跑 270/270（[desktop-suite-after-hotfix.log](model-ux/20261022/desktop-suite-after-hotfix.log)）；真实启动验证：python desktop_entry 进程拉起、回环端口 127.0.0.1 监听正常。
- 推送输出：`100a0bf..c63336e  codex/contract-review-v2 -> codex/contract-review-v2`（正常推送，未 force；当时代理 502 抖动，经多次重试成功）。
- 远端核对：`git ls-remote origin codex/contract-review-v2` 返回 `c63336eadf30d96fd5627d4bb562bf67dd20f34d`，与本地 `git rev-parse HEAD` 逐字符一致。
