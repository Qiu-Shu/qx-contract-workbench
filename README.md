# 群兴法律工作台

当前桌面产品为 **Harness 版 0.2.1（2026-11-03）**：一个输入框处理接待、合同审查、办案整理和模拟法庭，支持文档/图片、微信、可选脱敏及上下文压缩。

- [Windows 安装包与版本说明](https://github.com/Qiu-Shu/qx-contract-workbench/releases/tag/v0.2.1)
- [新版使用说明](harness/README.md)
- [最新交接与后续工作入口](harness/docs/2026-11-03-GitHub交接.md)
- [默认批注、意见书及模型中断恢复](harness/docs/2026-11-03-自动恢复与新版安装交接.md)

新版源码位于 `harness/`。根目录的 Python 工程和旧版桌面保留历史，并提供新版复用的文档解析/OCR；[旧版 README](README.legacy.md) 中的 0.6.x 是另一条版本线，不能与新版 0.2.1 按数字比较。远端已有合同拒收回退修复保留。

安装包自带运行环境，首次启动输入自己的 DeepSeek API Key，微信由本人扫码。用户资料保存在 `%APPDATA%/QunxingHarness`，升级和卸载保留资料。安装包未签名，尚未在另一台干净电脑验收。

源码开发仍依赖已记录的本机工具路径，迁移前先阅读 [开发与构建说明](harness/packaging/README.md)。工作区、密钥、微信登录态、客户原件和脱敏映射不进入 Git；688 MB 安装程序作为 Release 附件分发。
