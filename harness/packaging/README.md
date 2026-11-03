# 群兴 Windows 安装包

Windows x64 用户级一键安装，首次启动配置 DeepSeek API Key。用户无需安装 Node 或 Python。API 验证通过官方余额接口完成，不提交模型任务。

## 文件边界

程序及独立运行环境在安装目录，用户材料和加密设置在 `%APPDATA%/QunxingHarness`。首次安装只复制法律库、Skill 和工作规则，不包含开发机的 `.local`、用户材料、微信会话、API Key、浏览器账号或测试数据。旧版工作台使用不同安装标识，保留原位。

关闭桌面窗口后后台继续运行以接收微信。安装器和卸载器通过本安装实例的随机令牌控制接口停止后台进程树，不结束其他 Node 进程。卸载保留用户资料。

## 构建

`stage.py <新的暂存目录> --version 0.2.1` 从明确列出的本机依赖和项目源码生成分发内容。`refresh-stage.py <暂存目录> 0.2.1` 在并行开发完成后刷新业务源码和配置。`build.cjs <暂存目录> <输出目录>` 使用既有 electron-builder 26.15.3 / Electron 44.8.0 生成 NSIS EXE。构建工具来源路径固定在脚本中，仅构建机使用；最终运行路径由安装位置生成。

随包分别携带文档 Python 3.12、Scrapling Python 3.12、Windows-MCP Python 3.14，避免原生模块版本冲突。Node 依赖按版本解析，冲突依赖保留局部嵌套。Python `.dist-info` 和 npm 包内许可随依赖保留；法律库和 Skill 许可证保留原目录结构。

## 验证

- `node --test desktop/setup-service.test.cjs desktop/installed-runtime.test.cjs desktop/installed-migrations.test.cjs desktop/installed-contract-migration.test.cjs`
- `python -m unittest discover -s packaging -p test_stage.py`
- `check-first-run.py`：真实 Electron 引导页、无效输入不保存、显示/隐藏及窄窗口。
- `check-transition.py`：模拟服务商接受虚构密钥，但真实执行加密、IPC、独立后台启动、更换密钥及微信弹窗。**服务商验真在此用测试替代，未调用付费模型。**
- `check-portable.py <分发运行目录>`：便携 MCP 握手、缺失样式的虚构 DOCX 读取、默认批注、意见书、四项工作方法、公开网页读取、Windows 控制状态。末尾可加 `documents legal` 只执行相关服务的验证。
- `check-installed.py <安装目录> <隔离资料目录>`：实际安装程序的首次引导、无效输入拒绝、虚构密钥下主界面启动、桌面桥和微信入口顺序。
- 同一命令末尾加 `upgrade` 检查已有配置启动；`check-upgrade.cjs <安装目录>` 比较升级前后材料、私有映射、加密凭据摘要，以及实际运行的 `settings/describe` 恢复策略。

打包完成前直接执行包内 Node 与 Harness 版本检查，避免遗漏运行依赖。从 0.2.3 起 NSIS 使用支持差分的非固实 7z，同时生成 blockmap 和签名更新清单；排除开发用 `.d.ts` 和 `.map`。内部程序名继续为 `QunxingWorkbench.exe`，桌面名称为中文。更新流程、首次安装边界和发布方法见 [UPDATES.md](UPDATES.md)。构建检查和运行验收均以最终文件为准。

0.2.1升级仅替换摘要匹配0.2.0已发布默认值的合同Skill，AGENTS只替换已知旧合同段落；自定义内容保留。模型恢复迁移按补丁顺序合并同一provider设置，再补新增错误码，保留地址、凭据、自定义次数及模式。原设置先备份，完成后记录独立迁移标记。

只使用隔离资料目录。实际程序的虚构凭据通过仅测试时开启的本机调试接口保存，并正常关闭程序以保存Windows加密环境；没有复制用户密钥，也未用真实模型测试密钥验真。测试引导 `check-transition.cjs`、`seed-packaged.cjs` 和测试脚本均不进入分发文件白名单。

## 使用边界

微信需要用户本人扫码。bb-browser 的浏览器连接需要用户安装/启用对应扩展；不会迁移开发机登录态。Scrapling 动态抓取优先检测本机 Chrome/Edge，普通 HTTP 读取可独立使用。Word 外部打开需要用户已有 WPS 或 Office；不随包安装办公软件。

本构建没有商业代码签名证书，Windows 可能显示未知发布者提示。当前底层 Harness 为 0.2.2-alpha.2。不把本机隔离测试称为另一台干净电脑验收。
