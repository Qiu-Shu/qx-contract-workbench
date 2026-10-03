# Scrapling 本地安装与验证

已于2026-10-02在本项目虚拟环境安装 `scrapling[fetchers]==0.4.15`，并完成四项本地合成页面验证。它目前是开发工具，尚未接入合同审查、法源库或企业查询流程。该安装按用户新增的明确要求执行；项目主依赖锁和来源批准状态另由T00维护。

2026-10-03另实际用Fetcher读取六页Microsoft Learn公开Word COM文档，六页HTTP200；这是开发参考采集，不是企查查或业务外查。[接口及命令记录](../superpowers/plans/2026-10-03-T09-word-reference.md)。Windows中文CA路径在UTF8进程中首尝试curl77失败；同certifi证书bytes复制到ASCII临时路径、通过`verify=<ca path>`保持TLS验证后成功。没有禁用TLS或修改第三方包，未用代理/stealth绕过访问限制。首次失败与成功分别保留；该结果不代表全部公网目标兼容。

| 项目 | 实际结果 |
|---|---|
| 项目目录 | `D:\Documents\ChatGPT\律所项目` |
| Python | `.venv\Scripts\python.exe`，3.12.14，Windows AMD64 |
| Scrapling | 0.4.15，安装 `fetchers` 扩展 |
| Playwright / Patchright | 均为1.63.0 |
| Chromium | 153.0.8010.12，revision 1243 |
| 浏览器目录 | `.local\scrapling\browsers` |
| Python依赖 | `pip check`退出0，未发现冲突 |
| 版本快照 | `requirements-scrapling.lock`，28个固定发行版，含既有pytest环境依赖 |
| Wheel证据 | `.audit-local/scrapling-wheel-sha256.json`，28个实际下载wheel的字节数与SHA-256 |

官方安装方式是先安装 `fetchers` 扩展，再执行 `scrapling install`。[官方README](https://github.com/D4Vinci/Scrapling#installation) 本次核对了已安装版本的 `.venv/Lib/site-packages/scrapling/cli.py`：安装命令调用同一虚拟环境Python的 `playwright install chromium`、`playwright install-deps chromium`，然后更新公共后缀表。浏览器下载路径由 `PLAYWRIGHT_BROWSERS_PATH`指定；安装阶段访问了Python包索引、Playwright下载站以及 `publicsuffix.org`的公开列表。

在项目根目录复用以下PowerShell命令：

```powershell
.\.venv\Scripts\python.exe -m pip install --report .audit-local/scrapling-install-report.json "scrapling[fetchers]==0.4.15"
$env:PLAYWRIGHT_BROWSERS_PATH = Join-Path (Get-Location) '.local\scrapling\browsers'
.\.venv\Scripts\scrapling.exe install
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe scripts/scrapling_smoke.py --output .audit-local/scrapling-smoke.json
```

验证脚本会自行使用项目浏览器目录，在随机端口启动 `127.0.0.1` HTTP服务，只提供自有虚构中文HTML，并在结束时关闭服务。动态页面使用内联JavaScript写入内容，浏览器页面路由仅放行该本地端口。脚本在没有安装浏览器或内容不符时返回非零退出码；`--skip-dynamic`会将动态项记为 `not_run`，不会算作完整通过。

本次实际执行结果为退出0、4/4通过：

| 检查 | 实证 |
|---|---|
| Parser CSS | 中文合同标题和自定义属性读取正确 |
| Parser XPath | 金额文本读取为`1200.00` |
| Fetcher HTTP | 本地页面HTTP 200，CSS/XPath正确，尚未执行动态脚本 |
| DynamicFetcher | 无头Chromium执行JavaScript，取得“本地动态内容已执行” |

测试服务仅收到2次 `/sample`请求，浏览器页面路由没有发现需阻断的请求，QCC调用为0；没有抓取真实业务页面。证据写入 `.audit-local/scrapling-smoke.json`。这验证本机安装和基本API可用，未测试公网目标、登录页面、代理、反机器人场景、Spider、MCP或真实业务集成。

版本快照来自本机 `pip freeze`，用于复现Windows Python3.12环境；它本身不含完整性哈希。wheel完整性证据单独保存在本地审计目录，不能把该快照当作项目生产依赖锁。安装报告包含22个新增包的来源和下载哈希，下载的28个wheel已再用SHA-256核对。后续更换Python平台、升级包或安装浏览器后应重新记录版本和运行验证。

父阶段新增`requirements-scrapling-windows-py312.lock`，包含28个实际wheel哈希和`fetchers`扩展标记；哈希元数据另存`sources/scrapling-wheel-hashes.json`。已运行pip的`--dry-run --ignore-installed --require-hashes --no-index`，从本地wheelhouse成功解析28个固定依赖，未将该验证称为完整重装或生产恢复。复现当前Windows AMD64/Python3.12工具环境可用：

```powershell
.\.venv\Scripts\python.exe -m pip install --require-hashes -r requirements-scrapling-windows-py312.lock
```

```powershell
.\.venv\Scripts\python.exe -m pip freeze | Set-Content -LiteralPath requirements-scrapling.lock -Encoding utf8
.\.venv\Scripts\python.exe -m pip download --only-binary=:all: --dest .audit-local/scrapling-wheelhouse --requirement requirements-scrapling.lock
```
