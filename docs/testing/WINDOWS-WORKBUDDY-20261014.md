# Windows 本机基线与 WorkBuddy 实测记录

> 本文是 2026-10-14 的历史验收记录；后续连接、桌面安装与资料库进展见 [任务实际状态](../TASK_STATUS.md) 最新记录。

日期：2026年10月14日，显示时区 Asia/Shanghai，证据时间为UTC。当前环境是 Windows 10 专业版 10.0.19045 x64。工作目录 `D:\Documents\ChatGPT\律所项目`。本轮仅新增工程记录、研究笔记及测试产物，不修改业务源码或全局桥配置。

## 实际连接和任务结果

注册配置位于 `C:\Users\Administrator\.codex\config.toml` 的 `mcp_servers.workbuddy`。Python及脚本实际存在，脚本位于 `C:\Users\Administrator\Documents\Codex\2026-10-13\new-chat-2\outputs\codex-workbuddy-native-mcp\local_bridge.py`。使用既有绑定、既有模型和专用原生会话；本轮没有重装或重绑。

|检查|实际操作|结果|
|---|---|---|
|当前聊天工具|发现status/start/wait/cancel四工具|发现通过，cancel只发现未执行|
|本机连接|`workbuddy_status({})`|`connected=true`，本机127.0.0.1 ACP，串行并发1|
|当前聊天端到端|start指定项目内独立合成目录，wait取得终态|1任务完成，Read和Write事件完成；随机nonce及137+286=423落盘一致|
|实际注册入口|在桥目录运行下述既有脚本|3任务完成，退出0|
|文件读取及写入|随机输入→求和→result.json|Read/Write完成；脚本和父进程分别核对随机标识及总数|
|局部编辑|只把draft改为verified|Read/Edit完成，标识及总数保留|
|普通联网|搜索IANA并读取其官方example-domains页面|WebSearch/WebFetch完成；不是法律连接器测试|
|独立复核|重新读取report.json及输入/输出JSON|工具恰4个、任务恰3个、completed且error为空；无failed事件、全部内容断言通过，退出0|

完整脚本命令（运行目录为上述桥目录）：

```powershell
& '.\.venv\Scripts\python.exe' -X utf8 '.\integration_test.py' --registered
```

实际任务为 `wb-622a101c7fcf`、`wb-eaac7999ff62`、`wb-072bcd1127b6`。当前聊天探针为 `wb-b1ff7fbcfcd9`。连接验收合计4个任务；不是4个产品测试套件。已完成任务未重试。

原始报告位于桥目录 `work/integration-dd757d8f/report.json`，保留副本于本项目 `.local/workbuddy-probe-20261014/registered-integration-report.json`。本轮脚本、桥源码、报告SHA256及精简结果见[机器记录](WINDOWS-WORKBUDDY-20261014.json)。原生会话和权限详情留本机，不放进公开交付包。

本机README正文仍写版本0.1.0，并追加5.8.2修复说明；本轮以实际脚本SHA256识别受测代码，不把用户提供的远端0.1.1版本声明当作本地版本相等的证明。

桥权限按任务cwd约束收到的文件请求；其原生会话cwd与任务目录不同，不是OS沙箱。本次通过绝对路径限定合成文件并独立核对结果。不从成功推断任意目录都已受操作系统隔离。

## 仓库和数据库

用户随后明确授权Codex统筹WorkBuddy协作与复核，另启动`wb-aecf3684542b`，绝对cwd为本项目`.local/workbuddy-review-20261014`，仅可读取4份工程文档副本并写review.json。实际4个Read和1个Write事件完成，终态completed/error=null，返回findings为空。父进程另读回文件核对。该任务只审查文档自洽与声明边界，没有独立访问仓库、原始数据库或外部来源；不作为事实运行结果或法律质量的第二次证明。本轮合计5个WorkBuddy任务（连接4、文档复核1），新增依赖0。

合同HEAD与本地跟踪引用均为`27fd2bb63b1ac63e24b044e5770a8d227ad5465a`，开始时`git status --short`无输出，命令退出0；未执行fetch，因此该比较不声明远端此刻绝无新提交。家事本机HEAD为`65cabd5cf0641997fbed6441da47e63275e85b51`且工作树干净。持衡固定提交HANDOFF通过GitHub读取成功；本轮未找到或部署其本地checkout，不能标为本机三引擎已联通。

F盘目录实际可读，`2025`内13个CSV合计16,452,507,459字节。既有试点位于`D:\Documents\裁判文书数据库试点2025`。使用其独立环境及DuckDB `read_only=True`、`enable_external_access=False`读取统计，10,000来源记录、吉林字段86条、文书类型字面None408条。数据库大小和mtime前后一致，退出0。没有读取正文用于外部任务、导入新记录或重跑历史10,000条回查。

原文ID/URL缺失、完整性和中文全文检索的历史缺口仍保留；本轮统计不构成法律真实性审核。旧聊天《试点导入2025年裁判文书》的最近完成记录已通过本机聊天工具读取，与试点README和acceptance.json相互印证。

现有合同地址`http://127.0.0.1:8767/login`本轮请求得到URLError，未取得HTTP200。未因此重置账户、启动替代实例或改动真实工作区；不能引用10月13日HTTP200证明今天服务正在运行。

## 吉林公开来源入口

复用本项目Scrapling 0.4.15，TLS验证保持开启，certifi证书仅复制到ASCII临时路径，`retries=0`、单页timeout20秒。实际两页HTTP200：人大样例45,342字节、政府公报样例92,119字节，完整URL/UTC/SHA256保存在机器记录；原HTML和manifest只保存在`.local/workbuddy-probe-20261014/jilin-sources`。命令退出0。

只验证两个公开入口获取，不代表法规附件完整、历史版本齐全、现行有效或法库建成。未绕过登录、验证码或访问限制。未把取得的HTML送给WorkBuddy。

## 未验收项目与辅助读取问题

北大法宝、元典等商业法律MCP、取消任务、第二台电脑、Windows安装包、更新恢复、真实法律质量均未验收。合同业务回归、本轮OCR及Word渲染未运行；历史1723/159结果保留其原日期。

首次Word抽取因终端编码显示乱码，改用相同bundled Python的`-X utf8`重新抽取关键全文，退出0；原DOCX未变。首次memory_read的limit10000被工具拒绝，改为允许的6000后成功；一次GitHub持衡文件读取传输失败，后续只读重取成功。这些是辅助读取问题，不算功能失败测试，也未触发WorkBuddy自动重试。
