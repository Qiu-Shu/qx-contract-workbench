# 同伴前端合并验收

2026-10-30，按用户“拉取并且合并分支”“前端我们使用他的”要求，将 `dhb_law` 的 `4cef9e937024a188ef33f7976034f0c323a89d6f` 正常合入 `codex/contract-review-v2`。合并提交 `b0c4dafeef2dc2d4f6777db835ddc562e111bc0c`，另一父提交为 `7e69b1169a5608dffde33ff3b2d4e183d00c977b`。

## 结果

采用同伴的温情工作台、工作台/对话切换、共用输入和事项工具。保留既有本人微信入口、二维码、验证码、只读刷新、来源标记和权限。三个真实冲突按语义解决：页面退出同时执行 `viewMode.dispose()` 与 `personalWeixin.dispose()`；TODO、TASK_STATUS 同时保留新前端与较新 M6 状态，移除过时的“微信桌面待接”摘要。

同伴 CSS、视图控制器、底稿呈现和 PNG 与其分支一致。固定静态资源、PNG MIME、包数据与 qrcode 依赖共同保留。没有另做一版前端。

## 本轮实际检查

| 检查 | 命令或范围 | 实际结果 |
| --- | --- | --- |
| 前端与底稿 | `node --test scripts/test_assistant_*.mjs scripts/test_reception_worksheet.mjs scripts/test_evidence_worksheet.mjs scripts/test_followup_worksheet.mjs`，PowerShell 展开文件名 | 503通过，0失败/跳过，退出0 |
| 桌面 | `node --test desktop/tests/*.test.cjs` | 409通过，0失败/跳过，退出0 |
| 页面及资源 | `.venv/Scripts/python.exe -X utf8 -m pytest tests/integration/test_assistant_pages.py tests/integration/test_assistant_frontend.py -q --basetemp D:/qx-fm-py-1030` | 两完整文件36通过，20.69秒，退出0 |
| 四项开发门 | schema/defaults/development sources/development runtime dependencies | 均退出0；13来源保留未生产批准警告；56运行依赖+1构建依赖，网络0，原生构建未验证 |
| 恢复非界面 WIP 后 | 同一前端、桌面选择 | 分别503、409通过，不与上面重复累加 |
| Windows Chromium | 1440×900、390×844；真实本机 HTTP 和独立虚构工作区 | 图片加载、唯一 ID、两视图微信入口、输入节点/文字/选区保持、无横向溢出；页面异常0、外部请求0、模型请求0 |
| 保存中切换 | 暂挂真实草稿 PUT，切换两视图后释放 | 节点/文字/选区不变，保存200，后续 GET 原文一致 |
| 独立复核 | 固定合并提交及 WIP 恢复边界 | Spec、Quality 均通过，无需修复的合并回归 |

完整命令、输出、宽窄截图及报告保存在本机 `.superpowers/sdd/2026-10-28-personal-weixin-m6/frontend-merge-baseline/`。摘要见 [浏览器报告](browser-report.json)，[宽屏工作台](workbench-1440.png)、[窄屏对话](chat-390.png)。根代理已实际查看两图。浏览器中微信入口准确显示“仅桌面可连接”，没有伪造原生桥接或扫码。

## 本机改动保全

合并前251份未提交文件共27,259,913字节全部逐文件备份并校验 SHA256；命名 stash `bee78803d548df712076dbbf3bf3170f5a36ee92` 保留，未删除。197份非界面文件原样恢复；TASK_STATUS 两段原有模型记录按语义恢复；53份旧界面及配套测试/证据按用户选择暂存于备份，不重新覆盖同伴界面。独立复核再次核对全部备份与恢复文件摘要。原安装升级目录中的运行数据、缓存及完整备份均未加入本次提交。

本项是源码合并与组合界面验收，当前安装版0.5.1未更新。没有重跑全仓 Python，也没有调用真实模型或微信。M6 最终独审另确认的等待补附件、主合同/归属澄清、暂停恢复及排队发送撤权问题仍待下一修复片处理；本次合并不关闭这些问题，不代表业务、法律质量或生产验收完成。
