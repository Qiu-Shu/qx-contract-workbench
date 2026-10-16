# 本机完整备份与恢复核对 — 2026-10-16

基线 42ffddc，沿 codex/contract-review-v2。0.4.0 已实际安装，目标仍为 Windows 本机工程验证。新增备份覆盖完整本机案件截面，不放宽既有 synthetic-only 备份门禁；仅用独立合成材料验收，没有处理真实案件或上传资料。

## 实现与边界

原生维护入口暂停自身后台，持有既有工作区锁，SQLite backup 保存包含已提交 WAL 的数据库截面。验证精确结构/身份/外键/完整性，收集全部 protected 文件，核对原件和导出引用、文件数量、长度及 SHA256。接待历史、审计及授权记录保留在数据库中。独立法库、运行锁、浏览器缓存、日志、旧升级快照排除。

备份使用固定 scrypt 参数和 AES-256-GCM，口令经 stdin，未存设置或参数。临时明文在源工作区内；目标目录只收到密文，跨卷复制核验后原子无覆盖发布。正常或受控失败清理自身临时文件；进程强制终止可能留下未完成 staging，不能冒充成功备份。容量门为总量2 GiB/单文件512 MiB/20,000文件；本轮没有接近2 GiB的性能验收。当前发布使用硬链接，需要目标文件系统支持；NTFS C/D跨卷已验证，FAT/exFAT未验证。

恢复只新建唯一目录，先核对归档截面，再撤销历史会话、阻断未完成任务和当前批准、追加文件映射，不重写原件或历史 payload。恢复页面支持原件、历史 Word、接待各版核对；当前审查等接口被阻断。返回原工作区继续处理。恢复账户/成员代表备份时历史，不冒称备份后撤权和外部账单已同步；没有自动解除隔离、可写灾备切换或生产密钥托管。

## 实际验证

- 新引擎15项通过（engine-final2.xml），包括本机模式的独立合成 DOCX、接待、旧会话撤销、恢复HTTP只读、错误口令/头部/密文/tag/截断、现有文件不覆盖、工作区占用、缺原件、未知结构、硬链接、WAL、加密失败及明文临时位置。
- 较早目标组合52项通过（targeted.xml），包含既有 synthetic backup、桌面进程、升级和新引擎当时11项；另19项桌面组合与5项查询诊断通过。重叠不相加。
- Node 4项通过；默认/schema、13来源开发门、55运行包/1构建包及155文件绑定检查通过。13条生产来源批准警告保留；无新增业务依赖。
- 开发版原合同链14项、最终备份恢复10项通过。安装版相同14/10项通过，法库连接与异常生命周期8项再验通过。包括实际Word下载、恢复Word与备份前内容摘要相同、只读写入拒绝、错误密码无已发布副本、已有归档不覆盖、返回原工作区。
- 安装版0.4.0的8份桌面文件及14份网页资产与源码字节相同；Impeccable检测[]；界面截图核对可读，窄窗口150%应用缩放无整页横向溢出。未验实际系统DPI、中文Windows账户或干净第二台电脑。

完整回归实际退出0：收集1,825项，1,823通过、2跳过、0失败/错误，终端耗时1,502.29秒（JUnit suite为1,502.097秒）。初次未指定 `QX_PILOT_PYTHON`，2个旧试点适配测试跳过；随后复用原试点独立 DuckDB 1.5.6 环境，仅用临时合成资料补跑，2项通过（pilot-supplement.xml，终端1.88秒），未改原一万条数据库。

完整回归开始后补入1项明文临时位置测试及最后发布调整；该引擎最终15项另行通过（engine-final2.xml）。完整回归与补验按class/name去重，1,826个不同用例全部通过，与当前收集清单逐项相等，无遗漏。不能将分段结果说成单次1,826通过。最终再验Node4、defaults/schema、sources/dependencies开发门和源绑定，退出均0。

安装包 `dist/desktop/Qunxing-Workbench-0.4.0-Setup.exe`，154,448,183字节，SHA256 `90838d532a0c9947ecf93bab38319bbc15207248ce42cf8f8b73a812df2fa506`，NotSigned，安装退出0。使用默认Electron图标。

## 失败与独立审查

初始功能RED10项（red.xml）。引擎初次9过1失败由测试cookie域重复造成，修正测试后11过；不是产品会话失效。当前审查API隔离新增有效RED1项（recovery-api-red.xml）；明文临时目录新增有效RED1项（staging-red.xml），均修复并在最终目标通过。

开发第一次备份旅程在错误提示出现后立即点下一菜单超时：维护子进程尚未退出，busy仍在；已调整为进程关闭后展示结果，第二次及安装版均通过。原失败现场保留。

Standards：1个P2，维护菜单先停后台后被未保存页面拦截；修复后独立实机3项证实文字保留、后台可保存、保存后可进维护。独立11项既有测试、6项异常归档/再备份探针通过。最后明文位置/跨卷发布变更另4项探针通过，覆盖复制失败、目标竞争、摘要错误和无关文件保留；初次长短路径比较是探针错误，规范化后通过。

Spec：2个P2，返回原工作区的设置失败缺少提示、恢复GET仍显示审查处置为current。均修复独立复验；22条GET前后数据库表摘要一致，历史Word/旧会话/跨账户与角色6项通过。全部3个审查问题关闭，另父节点明文临时位置修正已补审，无开放问题。

完整回归日志一度长时间停留3%，实际只读栈采样显示在逐份重验DOCX的功能测试，并非模拟查询卡死；单独5个查询测试6.63秒通过。仅为诊断在 `.local/desktop-tools/py-spy` 安装 py-spy 0.4.1，未加入应用或业务环境。没有为日志停留修改业务逻辑。

## 证据

公开无材料正文的结果保存在 `workspace-backup-20261016`。独立合成原始记录在 `.local/desktop-acceptance/备份开发 01`（失败）、`备份开发 02`、`备份安装 01`；两路复核在 `.local/review-backup-spec-20261016` 和 `.local/review-backup-standards-20261016`，不进入Git/安装包。首次返回原工作区故障RED从原工具输出转录另存并标明，修复后的实测报告独立保留。

WorkBuddy本轮再次只读检测仍无专用会话活动端点，未提交任务、未称已重连。既有全量法律库和源F盘资料不变。后续为跨模块材料交接、其余业务/账户/更新与阿里云，1985—2024仍待下载。

## 可复核入口

完整：`.venv/Scripts/python.exe -X utf8 -m pytest -q --tb=short --junitxml=docs/testing/workspace-backup-20261016/full.xml`，退出0；最终引擎：同解释器运行 `tests/integration/test_workspace_backup.py`，15通过；试点：仅设置 `QX_PILOT_PYTHON=D:/Documents/裁判文书数据库试点2025/.venv/Scripts/python.exe` 后运行 `tests/integration/test_library_pilot.py`，2通过。原始完整日志在 `.local/desktop-tools/backup-full-tests.log`。

桌面：`node --test desktop/tests/*.test.cjs`，4通过；实际冻结、安装与安装版三个脚本 `acceptance.cjs`、`backup.cjs`、`library-lifecycle.cjs` 均退出0，报告保留完整检查名。开发检查为 `scripts/verify_defaults.py`、`-m cn_contract.cli schema --check`、`scripts/verify_sources.py --mode development`、`scripts/verify_runtime_dependencies.py --mode development` 和绝对路径 `src/cn_contract/mcp/bound_entry.py --check`，均退出0；后三项原始结果位于本批证据目录。
