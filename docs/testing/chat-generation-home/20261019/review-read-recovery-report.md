# 能力读取失败恢复：独立核对及最终浏览器复验

2026-10-19。本复核者没有修改产品或正式测试。本次对应主代理补充发现的第二项 P2：首次能力 GET 失败且尚无任务时，页面提示刷新，但按钮或其父层隐藏，用户无法执行提示的恢复操作。

## 原始证据核对

- read-recovery-red.log / .exit：exit 1，失败点为 #refresh-run 不可见，按钮带 hidden。
- read-recovery-green.log / .exit：虽名为 green，实际仍是 exit 1；按钮自身已无 hidden，但父层被原 CSS `:has(#run-status:empty)` 隐藏。该中间失败没有计为通过。
- read-recovery-final/report.json / .exit：修复展示条件和父层 CSS 后，主代理原探针 3 个断言通过，exit 0。
- read-recovery-render-green.log：新增单元覆盖后的 renderer 12 项通过；本独立复核只核对原始结果，没有重跑这组。

## 独立复验

原 read_recovery_probe.py 未改断言，输出到 review-read-recovery：3 个断言通过，exit 0。确认首次任务前恢复按钮实际可见，失败读取不自动循环，手动刷新恢复发送可用、保留原文字且模型 POST 为 0。命令与退出码见 review-read-recovery-command.json，12 个产品输入前后摘要一致。

随后按主代理授权，原完整浏览器探针在 browser-verified 独立目录运行：11 组全部通过，exit 0，6 次本机回环合成 POST，0 外部浏览器请求/CSP/pageerror，fixture errors 为空，12 个产品输入前后摘要一致。包含两个能力缓存反例，不与旧 9/11 组重复相加。

## 改动范围与结论

review-read-recovery-analysis.json 使用字节回推核对：assistant-render.mjs 只增补刷新按钮在 generation.phase=error 时可见的条件；assistant.css 只增补“刷新按钮也隐藏”时才隐藏空任务面板的条件。分别把这一行还原后，SHA-256 精确等于 browser-final 原文件；其余 10 个产品输入摘要相同。

该修复提供读取恢复入口，没有增加模型发送、自动重试或权限能力。独立复验未发现新问题，第二项 P2 已由上述实证关闭。本轮没有截图，没有修改安装版、真实材料或法库，不属于安装或生产验收。先前只读展示审阅未发现此缺陷的记录保留，不回写为当时已经发现或覆盖。
