# T07 MCP SDK 开发依赖实际合并与安装

2026-10-03；workspace `D:\Documents\ChatGPT\律所项目`。此记录替代候选的当前安装状态，但保留 `T07-dependencies-candidate.md` 的未安装历史及候选偏差。开发安装不代表许可使用/分发范围批准、供应链全面审核、QCC 官方兼容或生产完成。

正式闭包51包=冻结T03的35包+16候选包。旧35版本/wheel hash和独立build setuptools84.0.0/17份许可完全不变；新增16的32份许可/NOTICE和16份METADATA、16份逐版本registry JSON以原始 bytes保存于 sources。正式共92份许可、76有效条件依赖边。mcp/mcp-types2.2.0，httpx2/httpcore2 2.13.1，与旧httpx0.28.1独立保留。全部approved_by/at=null、approved_scope=[]，approved_for_production=false。

pywin32312的8个组件、15份许可/NOTICE、adodbapi两份LGPL2.1全文保持独立；License-Expression unknown不折叠成PSF，only/or-later/组件版本和源构建未确认。未手动执行 pywin32_postinstall.py；安装后的普通解释器启动实测 `pywin32_bootstrap` 已自动加载，不能继续说“startup hook从未运行”。候选 native_member_evidence 仅是历史静态审计，整个原生构建或每个 DLL 实际加载均未认证。后续pure依赖审计可用 -S 避免重复 startup hook。

|实际操作|退出码|实际数量/结果|
|---|---:|---|
|`.venv/Scripts/python.exe -X utf8 .audit-local/t07-dependencies/verify.py` 合并前|0|51 wheels、92许可、76条件边、旧35冻结、build1/17、53环境分发、5正式文件不变；仍非安装|
|合并辅助脚本初次|1|Windows Path字符串反斜杠使替换未命中，目标边界断言在任何证据复制前拒绝；已用as_posix纠正，不计应用RED|
|`pip install --no-index --find-links .audit-local/t07-dependencies/wheelhouse --only-binary=:all: --require-hashes --report .audit-local/t07-dependencies/formal-install.json -r requirements.lock` 初次|0|上述合并失败后的旧35锁全部already satisfied、实际安装0；保留原report/log，不冒称51完成|
|合并修正|0|51正式锁、复制新32许可/NOTICE+16METADATA+16registry；build原样；G13实际runtime_dependency、production审批仍null|
|同离线hash安装，report=`formal-install-51.json`|0|实际新增15分发；click8.5.0此前已有，旧35不升级、不重新下载；新15全部本机file:// wheel|
|`pip inspect --local` 安装后|0|68实际环境分发；51应用/测试METADATA与wheel逐byte一致，旧53分发版本不变|
|`pip check` 安装后|0|No broken requirements found|
|`pip install --no-index --no-deps --no-build-isolation -e .`|0|实际更新本项目editable元数据的mcp固定依赖；无下载、不变build版本|
|`pip inspect --local` editable更新后|0|68实际环境分发，qx-contract-workbench实际Requires-Dist含mcp==2.2.0|
|安装字节复核|0|mcp3选取SDK文件=安装byte=wheel byte=G13固定源；新32许可/NOTICE与wheel byte一致；51METADATA hash一致|

安装命令与UTC/退出码在 `.audit-local/t07-dependencies/commands.jsonl`；install report、inspect/check、SDK字节测量在同缓存。`sources/runtime-dependencies.lock.json`登记实际安装证据及保留候选/T03历史，不用旧T03 inspect冒充T07。未下载旧包、未网络安装、未手动postinstall、未账户/付费/协议接受/真实外查。

依赖阶段 formal manifest 的 BUSINESS_TEST_PENDING 是该阶段冻结的历史状态。后续实际安装版 initialize/list_tools/call_tool 已用独立本机 server 实测，作者最终两目标46 passed/必要受影响55 passed；详见 docs/testing/T07.md 与独立 T07-review.md。没有回写依赖冻结 hash 来冒充原先已运行协议。G13已登记开发runtime使用，但完整原生/传递使用范围、账户、地域、数据政策、价格和生产批准仍阻断。
