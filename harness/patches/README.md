# 群兴界面文案补丁

固定用于 Harness `0.2.2-alpha.2`，由 `pnpm patchedDependencies` 管理，执行 `pnpm install` 时自动应用。

- `dsh-client-ui-settings-models`：中文首次使用弹窗改为工作台介绍、四项法律业务及资料/微信入口；按钮为“开始使用”。
- `dsh-client-ui-conversation`：中文首页标题改为“AI师兄法律助手平台”，标签改为“法律助手”，输入提示改为法律需求与资料。

仅修改六项中文文案；保留原组件、首次使用记忆、按钮行为和许可证。没有新增弹窗或模型请求。上游 npm 包将界面字典编译进 `lib/client.js`，因此补丁作用于该文件；升级上游版本时需重新核对补丁位置。

新建安装暂存目录时，`packaging/stage.py` 会复制当前已应用补丁的依赖。`refresh-stage.py` 仅刷新业务源码，不能单独用于依赖或补丁更新；复用旧暂存目录时必须同时更新这两个依赖的 `lib/client.js`。
