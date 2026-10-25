# 恢复发布诊断：工具完成，WIN-PATH-02 仍开放

基线 `1defbed1a9f86bd0026d57bd78b7cb19cb55290f`，分支 `codex/contract-review-v2`。实际目录 `D:/Documents/ChatGPT/律所项目`，日期按北京时间 2026-10-25。本片只新增开发诊断工具、独立合成测试和证据，`src/`、schema17、恢复发布行为及微信暂停规则没有改动。前一执行段因代理额度限制中断，后续夜间 heartbeat 没有新增已核验提交；本次继续完成复验和收尾，不把这些心跳算作已完成切片。公开文本证据副本仅规范LF和行尾空白；原始字节及报告原始SHA对应的文件保留在本机忽略目录。

## 交付及调用

现有独立合成浏览器脚本可显式启用观察器，输出目录必须是新目录：

```powershell
.venv/Scripts/python.exe -B -X utf8 scripts/validate_weixin_authorization_browser.py --output .local/restore-publication-new --restore-diagnostics
```

默认不开启；同一脚本不带开关的完整流程也已重新验证。观察器仅包装指定 parent 内 `.qx-restore-*/workspace` 的解包、引用校验、升级、恢复隔离、数据库校验和最终 rename。事件记录本进程的相对 stage 文件句柄、阶段、采样状态、CWD 是否在 stage、异常类型及 errno/winerror；不记录 SQL、异常正文、凭证或文件内容。扫描失败标 `ERROR`，保留原返回值和原异常对象；退出时还原所有包装，拒绝嵌套，不启动恢复、不重试、不延迟、不强制 GC。发布后清理异常仍保留此前的 `publish:success`，不得据调用抛错就断言未发布。

两个辅助模块仅供此开发验证进程使用，不能装配进产品服务器。[Microsoft 文档](https://learn.microsoft.com/en-us/windows/win32/api/winternl/nf-winternl-ntqueryinformationprocess)说明 NtQueryInformationProcess 及其结构属于可变化的内部接口；本机使用的 class51 布局不作为稳定平台合同。实现动态加载、限制缓冲区并核对返回长度；non-disk/unknown 类型跳过，已识别磁盘句柄无法解析则扫描报错。快照不是原子的，只观察自身进程，不能排除外部锁；`OK` 仅表示采样结束，空列表不证明系统没有锁。Windows 当前环境已验，Linux 为 `NOT_RUN`。

## 原缺陷诊断结果

历史失败仍保留在 [原长路径记录](../../profile-persistence/20261023/path-diagnostic-review.json) 与 [D2f 浏览器失败记录](../../weixin-generations/20261024/README.md)。按优先级核查游标残留、池连接未释放、外部锁、目录句柄；本轮没有捕获自然发生的原始 WinError5，故没有修改产品代码或归因于杀软、路径长度、ACL、GC。

| 本轮实验 | 实际结果 | 可以说明什么 |
| --- | --- | --- |
| 修改前原完整浏览器流程，最多3次 | 3/3 PASS，exit0 | 本轮未复现；不是修复 |
| 精简真实 restore，普通3次＋深中文1次 | 4/4 PASS，exit0 | 能秒级反馈，不能关闭历史失败 |
| 旧失败合成归档，阶段观察3次＋关闭GC对照3次＋弱游标跟踪3次 | 9/9 PASS，exit0 | 发布前观察句柄0；upgrade时确实看到worker.lock，fence前释放 |
| 故意保留未耗尽SQLite cursor，connection.close已返回 | 原生rename得到WinError5 | 机制校准，不能证明产品存在此cursor |
| 最终观察器的相同held-cursor校准 | 原异常对象、WinError5与stage-relative workbench.db均捕获，包装还原 | 工具能观察这类失败；原缺陷仍未修复 |

[阶段汇总](lifecycle-summary.json)、[独立校准最终记录](observer-independent-control-fixed.json)、[根代理校准](root-native-control.json)。诊断初始归档、数据库、完整探针和截图保留在忽略目录 `.local/restore-publish-20261025`，不上传。阶段汇总的 `command` 来自探针 argv，解释器统一为本项目 `.venv/Scripts/python.exe -B -X utf8`；早期仅连接身份数受Python id复用影响，不等同连接总数。关闭GC仅是隔离进程里的诊断变量，未进入交付工具或运行方案。

## RED 与最终验证

新增CLI开关缺失的首次命令 exit2，缺模块断言首次1 failed/exit1，属于接口 RED。根首次边界测试真实出现1 failed/23 passed，定位目标 parent 过滤遗漏后修补。独立实际 held-cursor 检查发现工具把 GetFileType 的非文件返回0也当扫描故障，exit1；改为只对磁盘句柄解析路径后相同校准 exit0，并补实际默认scanner打开/关闭文件的永久测试。三个问题均为新诊断工具问题，不冒充 WIN-PATH-02 的 RED→GREEN。中间失败证据保留为 `browser-probe-interface-red.*`、`observer-first-red.*`、`root-observer.*`、`observer-independent-control.json`；中间24通过不重复累计。

根代理最终JUnit去重 **4模块70个不同Python case**，0 failure/error/skip；[汇总、实际完整argv与源码SHA](verification-summary.json)。每条pytest命令使用 `-q --tb=short --junitxml=<本片目录对应XML>`，独立D盘 basetemp，退出码见同名JSON：

| 根代理命令选择范围 | 数量 | 进程耗时 | exit |
| --- | ---: | ---: | ---: |
| `-m pytest tests/unit/test_restore_publish_diagnostics.py` | 25 | 1.703s | 0 |
| `-m pytest tests/integration/test_workspace_backup.py tests/integration/test_assistant_attachment_backup.py` | 42 | 80.328s | 0 |
| `-m pytest tests/integration/test_contract_long_path_backup.py` | 3 | 11.078s | 0 |

长路径组有1条既有 `record_property`/xunit2 警告，不隐藏为零警告。独立作者和复核者的25项是上述25项子集，不另加；恢复45项保持产品源码相同。并非单次全仓运行，不与此前310、814、925等不同模块范围相加。

最终原浏览器流程默认模式7.218s/exit0，诊断模式7.859s/exit0：[默认报告](root-browser-default-report.json)、[诊断报告](root-browser-diagnostic-report.json)。两者均grant2/POST2、实际丢ACK后只查询、真实合成qxbak恢复GET200/POST409，外部浏览器请求和页面错误0、model_attempt/run/review_run0。诊断模式捕获14事件、全scan OK，upgrade维护锁可见、发布前句柄0；默认报告没有诊断字段。二者及本机原生校准的执行源码前后SHA一致。

四开发门均exit0：`-m cn_contract.cli schema --check`、`scripts/verify_defaults.py`、`scripts/verify_sources.py --mode development`、`scripts/verify_runtime_dependencies.py --mode development`。来源13仍为 `NOT_PRODUCTION_APPROVED`；依赖55 runtime＋1 build，`native_build_verified=false`、network_calls0，不能当生产批准。

## 尚未完成

WIN-PATH-02 与独立原生访问冲突继续 **OPEN**；需要原失败路径的可归因RED、修补及同路径验证才可关。观察会改变时序，既有PASS不能替代原故障证据。Node回归、全仓、Linux、安装版Electron、新安装包、真实微信/产品模型/真实合同外发、付费、签发为 `NOT_RUN`；安装版0.4.1不变。

D2g1之后的按代际接收/分发、明确HTTP与桌面操作、可信微信身份/账号资格和E限期模型许可继续待办。本片没有启动产品worker/provider、安装机器人或解除恢复隔离。[独立复核及WorkBuddy意见裁决](review.md)保留实际原生字段校准，未盲采与本机证据冲突的建议。
