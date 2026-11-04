# 群兴界面文案补丁

固定用于 Harness `0.2.2-alpha.2`，由 `pnpm patchedDependencies` 管理，执行 `pnpm install` 时自动应用。

- `dsh-client-ui-settings-models`：中文首次使用弹窗改为工作台介绍、四项法律业务及资料/微信入口；按钮为“开始使用”。
- `dsh-client-ui-conversation`：中文首页标题改为“AI师兄法律助手平台”，标签改为“法律助手”，输入提示改为法律需求与资料。

- `dsh-client-ui-workspace`：增加 `sidebar.workspaces.business` 列表插槽，四业务入口位于原生工作区上方，保留原生会话树。
- `dsh-client-ui-chat`：保留附件预览补丁，增加 `conversation.chat.assistant.business` 链式插槽；未注册业务展示时直接返回原消息组件。原生复制遇到完整接待标记时只复制客户回复，不含内部参考。

保留原组件、首次使用记忆、按钮行为和许可证。上游 npm 包将界面组件编译进 `lib/client.js`，因此补丁作用于该文件；升级上游版本时需重新核对补丁位置。

新建安装暂存目录时，`packaging/stage.py` 会复制当前已应用补丁的依赖。目前 `refresh-stage.py` 会遍历 `pnpm-workspace.yaml` 的受管补丁同步对应依赖；运行前先执行 `pnpm install` 应用补丁并同步锁文件。业务引导还需要整包复制 `desktop/integration` 的新增服务端和浏览器文件，不能只替换原 `client.js`。
