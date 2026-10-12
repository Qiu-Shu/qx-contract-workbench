# 六工具本机安装与自动复用

日期：2026-10-09，Asia/Shanghai。用户要求：安装Windows-MCP、bb-browser、Scrapling、Ponytail、Impeccable、Taste，并按任务自动复用。

## 实际结果

|项目|安装与适配|实际验收|
|---|---|---|
|Windows-MCP|0.8.7；独立Python3.14.4/92包；全局STDIO配置；关闭遥测；中文环境排除App|独立协议握手、19工具发现、DisplayInventory返回1920×1080/96DPI；当前聊天新服务尚待刷新发现；点击/输入未测|
|bb-browser|0.14.2；独立pnpm目录/锁；14依赖包；CLI自动路由|本地合成页面打开、JS渲染、HTML读取并交Scrapling解析通过；MCP不支持见下|
|Scrapling|复用既有0.4.15+fetchers/Chromium；项目依赖不变|CSS、XPath、localhost HTTP、localhost动态页面4/4通过；与bb-browser联动通过|
|Ponytail|固定源技能安装；移除不兼容argument-hint元数据；MIT保留|技能校验通过，隐式选择开启|
|Impeccable|4.5.1源技能；Windows引擎0.1.12；Apache-2.0及NOTICE保留|技能校验、engine-probe、项目context通过；没有安装生命周期hook|
|Taste|固定源design-taste-frontend及redesign-existing-projects两技能；MIT保留|2个技能校验通过，隐式选择开启；新网站/已有工作台分别路由|

使用说明及本机证据：`C:/Users/Administrator/.codex/tools/reuse-suite/USAGE.md`、`evidence/install-manifest.json`。全局规则在`C:/Users/Administrator/.codex/AGENTS.md`，技能在`C:/Users/Administrator/.codex/skills`。无需手工点名；按任务相关性使用，不是持续后台操作。

业务源码、主依赖锁、原件、现有Obsidian hook均未修改。无真实模型/QCC/登录账号/真实合同/外部hub/付费/公开发布。工具安装不代表T00–T13或生产状态升级。本轮不重跑业务全套测试。

## 实际命令与结果

|命令/检查|退出码|结果|
|---|---|---|
|五个指定GitHub仓库git clone、rev-parse|0|固定五个源码提交；仅本机外部工具目录|
|pip --target bootstrap uv==0.11.8|0|独立工具目录安装|
|uv venv --python3.14；uv pip install windows-mcp==0.8.7|0|Python3.14.4；92包。启动时提示当前项目3.12约束，实际目标独立环境，项目环境未更改|
|pnpm --dir bb-runtime add首次|1|目标目录不存在；建立目录后重试|
|pnpm add --save-exact --ignore-scripts bb-browser@0.14.2|0|14个依赖包；固定版本及锁|
|官方install-skill-from-github.py固定ref安装|0|Ponytail、Impeccable、Taste主技能、Taste改造技能，共4目录|
|probe_mcp.py windows|0|MCP握手及19工具发现|
|probe_mcp.py windows DisplayInventory|0|只读显示信息调用，isError=false|
|probe_mcp.py bb|1|README --mcp只返回CLI帮助，非JSON-RPC；不注册此错误入口|
|windows-mcp --help；serve --help；bb-browser --help|0|本机可执行文件可用|
|impeccable.cmd engine-probe|0|impeccable-engine 0.1.12；下载经launcher SHA256 sidecar校验|
|impeccable.cmd context --help|0|实际执行context而非帮助；读取项目上下文，无业务编辑。准确记录此行为|
|python scripts/scrapling_smoke.py --output .audit-local/scrapling-smoke-20261009-reuse.json|0|4/4；2次localhost /sample请求，真实业务远程请求0|
|probe_browser.py首轮|1|上游get html要求ref；改用文档DOM outerHTML|
|probe_browser.py第二轮|1|验证脚本取错JSON字段value；核对源码后改result.result|
|probe_browser.py最终|0|浏览器渲染→HTML→Scrapling CSS断言；测试标签、浏览器、daemon关闭|
|quick_validate.py首次使用项目Python|1|无PyYAML；改用已有Windows工具独立环境，不改项目依赖|
|quick_validate.py Ponytail首次|1|argument-hint不支持；只移除此元数据，正文不改|
|quick_validate.py四技能最终|0|各自Skill is valid；4个技能|
|uv pip check windows-env；项目python -m pip check|0|两个环境无依赖冲突|
|codex mcp add/get windows-mcp|0|enabled=true；STDIO；遥测false；排除App|
|verify_install.py首次|1|发现新增MCP配置前后原node_repl.args丢失；未将变化冒称保全通过|
|只恢复备份node_repl.args；verify_install.py最终|0|去掉新增windows-mcp后，全局config与备份结构完整相等；原AGENTS正文前缀保留；4技能来源正文/许可证/隐式选择检查通过，生成manifest|

独立只读复核首轮发现上述配置差异及尚未写完的两份记录。配置已精确恢复，文档和manifest已补齐；未覆盖任何其他配置键，旧配置备份不输出到日志。初轮问题及后续补验分开记载。

独立末次补验：Critical 0 / Important 0 / Minor 0；实际核对原配置结构保全、原AGENTS保留、5个源提交、4技能SHA256和隐式选择、两份交付记录。审阅未重跑浏览器或桌面操作；当前聊天加载/真实应用点击/登录站点/设计质量仍未验。

## 固定来源与局限

- Windows-MCP源：https://github.com/CursorTouch/Windows-MCP ，commit `b455c2766c63599d466a6178641bac70787979a4`；实际运行PyPI0.8.7，不能把源码clone与发行wheel冒称字节相同。
- bb-browser：https://github.com/epiral/bb-browser ，commit `7975dc74b3f637d54906228e52f2ba9454874105`；实际npm0.14.2。
- Ponytail：https://github.com/DietrichGebert/ponytail ，commit `9cc65d03aa2da1db7121b912d03596409ee340b8`。
- Impeccable：https://github.com/pbakaus/impeccable ，commit `9dad388a41944a0d2b8d1fb547c8556d2ecb49e7`。
- Taste：https://github.com/Leonxlnx/taste-skill ，commit `18dfc928b135629e0eddfdd445a06400d04ed439`；主技能v2 experimental。
- Scrapling：https://github.com/D4Vinci/Scrapling ，复用本项目既有固定0.4.15；旧安装证据见[SCRAPLING.md](SCRAPLING.md)。
- Codex官方参考：[MCP配置](https://learn.chatgpt.com/docs/extend/mcp?surface=cli)、[技能隐式选择](https://learn.chatgpt.com/docs/build-skills)。

全局config及AGENTS原件已本机备份，不纳入Git。恢复应只撤销本轮新增块，避免覆盖用户后续变化。当前聊天工具列表未加载新Windows-MCP，须宿主刷新后核对；四技能本机已可读取，隐式加载仍由宿主决定。没有用模型调用测试自然语言选择率，没有将格式校验称为审美质量评测。


## 2026-10-09重启后当前聊天验收

用户确认重启后，本聊天工具清单已实际发现Windows-MCP全部19工具；原生调用DisplayInventory一次成功，isError=false，返回1920×1080、96 DPI、缩放1.0。Ponytail、Impeccable、design-taste-frontend、redesign-existing-projects四技能已出现在当前会话技能清单。上文“当前聊天加载待刷新/未加载”现为安装阶段历史状态，已由本次原生调用关闭。自动复用规则保留。未执行点击、键盘输入、真实登录网页或设计质量验收。
