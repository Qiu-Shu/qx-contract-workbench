# CH-08 首片：对话成果复制与 Word 导出

2026-10-25，北京时间。源码基线 `4325711`，开发分支 `dhb_law`；集成主分支仍为 `codex/contract-review-v2`。完成本地源码、定向回归、独立审阅、实际浏览器与 Word 样本检查。未提交、推送、创建 PR、更新服务器或替换 0.4.1 安装器。

## 使用入口

1. 对话页顶部点击 **成果与导出**。
2. 选择一份已保存回答或某一版档案。档案按版本倒序分页，再接历史模型回答，每页最多 20 份。
3. 选择客户版或内部版，点击 **预览所选版本**，核对后复制或导出 Word。

客户版只含该档案版本单独保存的 `client_reply` 字段。没有客户回复时，先在“档案草稿”中填写并保存；有多个未解决候选时不猜选。人工保护值优先，明确清空后不回退到旧候选。现有模型回答只提供内部版。内部档案版包含该版本已保存字段，冲突字段提示待处理，不拼接候选正文。

复制、下载基于服务器重新读取的固定来源及预览摘要，不接受客户端自由正文，不从页面 DOM 抽取整页内容。复制含标题、来源、待核说明和正文；Word 使用同一受众投影。不会调用模型或自动向客户发送。

## 实现边界

DTO 集中在 domain.py；assistant/outputs.py 复用既有身份、案件权限、保存回答和档案修订。来源、版本、受众和内容共同决定摘要及输出 ID。Web 路由在正文前后及 Word 渲染后核对当前权限；绑定变化拒绝，明确旧版本不被新修订替换。Word 使用现有固定 python-docx 依赖新建干净包；客户正文、标题和文档属性均不带内部字段/成本/原始聊天 JSON。

前端复用原侧栏。换受众/来源必须重新预览；关闭、换对话、撤权和退出清除正文、丢弃迟到结果。复制使用同步 copy 事件，在写入时核活动会话，不支持时保留预览供手动复制。没有新增表、迁移、依赖、模型许可或备份格式；投影由既有不可变来源重新构造，不新增独立文书编辑器。恢复副本保留来源，但阻断本片新投影和导出。

## 实际验证

| 范围 | 实际结果 | 证据 |
|---|---|---|
| CH-08 后端最终整组 | 22 passed，含真实 qxbak 往返及恢复 HTTP 隔离 | [日志](backend-final.log) |
| 关联 Python | 121 passed；该组早于新增备份测试，备份另 1 passed | [关联](related-final.log)、[备份](backup-roundtrip.log) |
| 全部 assistant 前端脚本 | 321 passed，含本片 9 项 | [日志](frontend-final.log) |
| 桌面 Node 逻辑 | TMPDIR=/private/tmp 下 369 passed | [日志](desktop-final.log) |
| 独立审阅 | 两项 P2 均已修复，复核无确认遗留；独立分页/隔离探针 6 passed | [审阅](independent-review.md)、[探针](independent-pagination-probes.py) |
| 实际浏览器 | Chromium + 真实 loopback FastAPI；客户复制、两类 Word、旧档案、空会话、关闭清理与 390px 无横向溢出通过；页面错误/外部请求均 0 | [回执](browser-report.json)、[宽屏](client-1280.png)、[窄屏](internal-390.png) |
| 实际 Word | 实际 HTTP 下载后扫描完整 XML/关系/属性包；客户没有内部正文/标题哨兵，内部保留；两份各 1 页，已目视检查 | [摘要](artifact-check.json)、[客户样本](client.docx)、[内部样本](internal.docx)、[客户渲染](client-render/page-1.png)、[内部渲染](internal-render/page-1.png) |
| 开发门 | schema/defaults/sources 退出 0；runtime dependencies 退出 1 | [逐命令结果](gates.json) |
| 基线保护 | 独立保存 87 份原本地文件；除明确接线/状态文档的 7 份外，其余 80 份逐字节一致 | [核对](baseline-preservation.json) |

所有业务数据、账号、Word 样本均为独立虚构数据。没有真实客户合同、真实模型、QCC 或生产环境。各组数字有交集，不累计为独立验收总数；不是全仓 Python 或 Windows Electron/安装器验收。

## 失败及修正

- [后端首轮](backend-initial-red.log)12 项失败，新路由/模块尚不存在；首个实现阶段 11 通过、1 个测试夹具错误导入不存在的 fence，[原记录](backend-first-green-fixture-error.log)保留。改用既有 RestoreFenceRow 后通过。[前端首轮](frontend-initial-red.log)8 项因 binder 尚不存在失败。
- 独审发现历史档案没有产品入口；改为完整版本分页，加 22 修订 HTTP 回归。独立 19/20/21/40/41 修订后接模型的边界检查无丢失/重复。[原历史探针](independent-history-discovery.py)保留修复前发现断言，不冒充最终回归。
- [原剪贴板探针](independent-clipboard-discovery.mjs)复现挂起异步适配器换会话后的旧正文复制；移除异步路径后，同步事件内活动核查、监听器 finally 清理、Node 与最终 Chromium 复制均通过。
- [桌面首轮](desktop-symlink-temp-first.log)因系统临时目录符号链接触发原安全拒绝，319 通过、33 失败、17 取消；改用真实 /private/tmp 后整组 369 通过，没有修改桌面产品保护。
- 浏览器初次 fixture 口令超既有上限，在页面启动前被拒；仅修正虚构夹具。最终[fixture](browser-fixture.py)与[脚本](browser-validation.cjs)保留。
- 默认捆绑 LibreOffice 的中文字体发现不足，首次 PDF 文本可提取但像素缺字；以临时 [fontconfig 映射](render-fonts.conf)重渲染同一 DOCX 后逐页检查通过。仅命令环境 FONTCONFIG_FILE，不改系统配置或产品字体。[客户日志](render-client.log)、[内部日志](render-internal.log)。
- [运行依赖门](gate-4.log)为 MANIFEST_INVALID:FileNotFoundError；没有修改固定清单或把已安装测试依赖当缺失证据。

仍开放：Windows 原生安装器/字体/剪贴板、WIN-PATH-02 和原生进程崩溃根因、服务器/安装包、真实法律质量/律师接受。更广技能/附件成果及独立文书编辑留待后续切片。
