# CH-04H Native 独立复核

结论：所查原生授权与窗口隔离当前无未关闭阻断项。15 个不同独立探针全部通过（11 个 coordinator/main + 4 个 window）。发现的 1 项 P3 文案不一致已由根代理修改产品并复验关闭。

复核对象为本代理未编写的 model-session、model-approval、独立确认窗口及页面/preload、main/preload/package。费用来源、固定配置版本、真实 cookie 与保存草稿、完整范围/修订/摘要、模糊授权撤销或终止、迟到结果、窗口/frame/路由限制、共享 busy、纯文本显示与明确取消/同意均已核对。

## 已关闭观察项

N1 / P3：主页面曾声称可在确认窗口核对“当前范围”，但原生四字段契约只展示完整正文、接收方、模型、费用上限。后端完整 scope 核验已存在且通过，不是越权缺陷。根代理已把两处前端提示收窄为实际展示内容；本代理经授权仅同步一个 render 测试断言与名称。原生产品未由本代理修改。

窗口代理后续将三处默认 Cancel focus 改为 preventScroll:true，并移除 HTML autofocus，防止最小窗口打开即滚到底。独立窗口探针已覆盖正常读取、读取失败、确认拒绝三条焦点路径，均保持顶部且默认焦点为取消。实际像素位置仍以根代理 Windows 验收为准。

## 实际命令与证据

- `node --test .local/native-send-confirmation-20261019/review-native-boundaries.test.cjs .local/native-send-confirmation-20261019/review-native-main.test.cjs`：11/11 PASS，exit 0，review-native-initial.log。
- 初次独立窗口运行：4/4 PASS，exit 0，review-native-window.log。随后最后 HTML/JS 微调的最终证据如下。
- `node --test .local/native-send-confirmation-20261019/review-native-window.test.cjs scripts/test_assistant_generation_render.mjs`：18/18 PASS，exit 0，review-native-focus-wording-final.log。包含同一 4 个窗口探针和 14 项 render 回归；不额外累加到 15 个不同独立探针。

初审后只有 model-approval.html/js 的焦点改动；session/coordinator/main/preload/package 摘要与 11 项通过时一致。最终源码和探针 SHA-256 见 review-native.json。

## 范围与限制

独立探针使用真实源码/模块与合成回环 HTTP、Electron/DOM 边界，不冒称实际 Windows 或真实模型验收。根代理另行完成真实 Windows、冻结后端与视觉检查。未读取实际用户密钥或真实材料、未调用真实模型、未改安装版或法律库、未提交，也未重复全套历史测试。

批准后前端本地变化放弃 POST 的既定边界保留：原具体 grant 最多 120 秒，固定 request/fullscope/composer/hash，不自动触发；后续显式确认替换授权。本片不提供 renderer 撤权 API。
