# 具体工具名称中文显示

日期：2026-11-12。基线：审核分支提交 `dab11f2b`；实施分支 `codex/tool-labels-zh`。用户明确要求调用时的具体工具名称显示中文，并授权通知“整理2.16版本审核”纳入正在验收的版本。

## 已实现

- 新增 `config/tool-labels.zh-CN.json`，171 条对应名称，覆盖八份随包 MCP 目录的全部 153 个工具，以及知识整理、新媒体、微信文件等常用入口。
- 在固定 Harness `0.2.2-alpha.2` 的通用工具卡片上显示具体中文标题。例如 `mcp__qx_materials__read_material` 为“读取材料正文”，`mcp__qx_legal__generate_litigation_document` 为“生成诉讼文书”。不再在摘要重复显示英文工具编号。
- 准备、运行、完成、失败、中断以及历史记录使用同一映射。工具原始 ID、调用路由、参数、输出、错误、检查入口和专用卡片保留。未知外部工具显示原名，不根据相似名称猜译。
- 开发入口使用受管 pnpm 补丁；安装包入口复用同一转换，将目录及生成文件摘要纳入 source manifest。重复转换可更新名称；上游结构不匹配时明确失败。

## 验证

使用官方本机安装基线中的真实 `dsh-client-ui-tool/lib/client.js`，在隔离环境加载其真实模型与通用卡片函数。测试只使用合成文件名和正文，无模型请求。

| 检查 | 实际结果 |
| --- | --- |
| RED：具体工具标题仍为 `tool.title.generic` | 两条中文标题断言真实失败；早期测试夹具接口错误另行修正，不计产品缺陷 |
| `node --test harness/scripts/tool-labels.test.cjs harness/packaging/stage.test.cjs harness/packaging/verify-stage.test.cjs` | 最终 10 passed / 0 failed / 0 skipped，退出 0 |
| 工具目录覆盖 | 153 个 MCP ID 全部有中文标题，并保留原始 ID |
| 已打完整补丁的依赖环境重测 | 初次发现测试将已登记 `read_file` 当未知工具；修正为原生 `pwsh` 后 5/5 通过，退出 0；后增补的目录/锁一致性检查包含于最终 10 项 |
| 独立审阅 | 原始 bootstrap 与完整映射环境各 4/4 定向检查通过；无未解决 P1/P2 |
| `git apply --check` | 新补丁适用固定原始依赖，退出 0 |
| `node --check`（转换脚本、stage）与 `git diff --cached --check` | 退出 0；`.gitattributes` 对新增补丁文件保留行尾/文件尾检查，排除统一差异格式所要求的“上下文空格+原始Tab”误报；产品源码规则未变 |
| `pnpm install --offline --lockfile-only --frozen-lockfile --ignore-scripts` | 退出 1：本机 pnpm 11 缺 registry 离线元数据，`ERR_PNPM_NO_OFFLINE_META`；未称依赖安装通过。新增检查核对补丁 SHA-256、锁的三个引用、开发补丁目录与安装包目录一致 |

首次运行打包回归时缺 `QX_BUILD_MODULES`，3 项依赖加载失败；补上现有已安装构建依赖路径后原测试完整通过，不改断言。

## 合入与验收

将本分支提交合入审核分支，在该分支的新安装暂存目录执行已有打包流程。`stage.cjs` 只增加转换调用及 generated 清单条目，应同时保留审核分支对 bootstrap、版本和安装验收的改动。

本轮未修改正在运行的安装版，未重启应用，未构建/发布完整安装包，未运行真实模型，也未进行真实桌面视觉验收。正式安装包中的显示效果与最终更新由审核聊天继续验收，不把源码通过记为用户已升级。
