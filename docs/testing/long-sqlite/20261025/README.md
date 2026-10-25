# Windows SQLite精确只读路径与长路径快照 — 实测（2026-10-25）

基线`916d55bf47ffb513508b81c5ebf40a5482372a67`；实际Windows仓库`D:/Documents/ChatGPT/律所项目`。本片关闭上轮D2g5b实际复现的SQLite长路径失败，历史FAIL记录保留。独立的WinError5/WIN-PATH-02和原生访问冲突保持OPEN。

## 源码实现与已有测试

恢复后二次qxbak在SQLite只读URI丢失扩展路径命名空间；普通备份手拼URI会将字面`literal%23.db`误选为同目录`literal#.db`。共用helper对现有filesystem_path原生文件名百分号编码、固定mode=ro，接入8处只读调用。路径/权限/schema/integrity/identity/trusted_schema/硬链接/worker锁检查保留。

原例通过URI后又在_references数据库会话失败。直接扩展路径放入SQLAlchemy URL会将?误解析为查询；局部do_connect只在DBAPI边界替换文件名，逻辑URL、可迁移引用、中央Database及PRAGMA/事务监听保持。_references并非全部只读连接，既有事务语义未变。

| 文件、符号与本片行号 | 实际关联证据 |
|---|---|
| [ops/file_paths.py:30 sqlite_readonly_uri](../../../../src/cn_contract/ops/file_paths.py) | 新16例：Unicode/空格/%/#/查询字符、精确哨兵、263/317+路径、缺失不创建、只读拒写、源SHA不变；UNC仅构造 |
| [ops/backup.py:152 validate_raw_database](../../../../src/cn_contract/ops/backup.py) | 新文件/父目录两种%23与#碰撞、普通备份恢复 |
| [ops/workspace_backup.py:109 _validate_database、132 _references、253 create_workspace_backup](../../../../src/cn_contract/ops/workspace_backup.py) | 新300+快照、原未改长恢复再备份、原件及硬链接拒绝、凭据/TaskDraft/PDF/微信双代恢复 |
| [web/local_server.py:62 _open_workspace、101 _database](../../../../src/cn_contract/web/local_server.py) | 新300+精确身份读验证、本机30例；不代表所有本机长路径写入支持 |
| [web/workspace_upgrade.py:52 pending_matches](../../../../src/cn_contract/web/workspace_upgrade.py) | 升级58例，含备份/marker/DDL失败恢复、篡改和未知结构拒绝 |
| [library/catalog.py:90 connection](../../../../src/cn_contract/library/catalog.py)、[library/service.py:107 search](../../../../src/cn_contract/library/service.py) | 新特殊/深目录真实catalog拒写/检索，资料库72例；writable分支不变 |

新测试：[单元16](../../../../tests/unit/test_sqlite_readonly_paths.py)、[边界8](../../../../tests/integration/test_sqlite_readonly_boundaries.py)、[快照1](../../../../tests/integration/test_sqlite_native_snapshot.py)。原未改test_assistant_attachment_backup.py::test_long_parent_paths_create_restore_and_rebackup[long]与RED使用同87字符basetemp，没有缩短路径掩盖故障。

## 本轮实际验证

[机器回执](verification-summary.json)保留完整argv、UTC时间、退出码、不同case ID、输入前后SHA。根六组20模块共289不同Python全部PASS，0FAIL/ERROR/SKIP；新增25已包含，独立重复25/58及旧例单跑不叠加。以下是关联分组，未跑全仓单进程。

| 最终根运行 | 数量 | 实际结果 |
|---|---:|---|
| final-new |25 Python|PASS|
| final-materials |48 Python|PASS，1条既有record_property/xunit2兼容warning|
| final-backups |46 Python|PASS|
| final-native-verified |88 Python|PASS|
| final-library |72 Python|PASS|
| final-task |10 Python|PASS|
| node-frozen |233 Node，15既有脚本|PASS，脚本前后SHA一致；无新UI测试|
| schema/defaults/sources/dependencies |4开发门|exit0；仍含NOT_PRODUCTION_APPROVED提示，native_build_verified=false|

[独立复核](review.md)：同一独立审查者Spec/Standards两轴0遗留，独立实跑新25和修正后升级58。第二内部agent因thread limit未创建，不称两名独立审查者。AST核7产品文件只改helper、8URI、局部DBAPI和imports；根最终分组的读取与独立执行范围分别记录。

## RED、失败尝试与夹具更正

原旧例1FAIL；helper未实现16FAIL；独立实际边界6FAIL/2PASS；新快照1FAIL。URI修复暴露第二DBAPI断点，直接扩展URL方案失败；最终局部do_connect后原旧例1PASS并纳入最终48组。新测试一项错误负例期待合法相对引用副本被拒，已更正测试，产品引用校验未放宽。历史名称含green/final的失败仍按JUnit记FAIL，见机器回执earlier_attempts及各XML。

首轮final-native为30PASS/58setupERROR，旧fixture漏清理weixin_descriptor_generations；实际161项，冻结pre-intake157项，仅多1表+autoindex+2触发器。独立加载HEAD版本的7受改模块、核167实际导入模块SHA一致，冻结旧测试仍1ERROR；[基线回执](upgrade-fixture-baseline-red.json)及[复现脚本](upgrade-fixture-baseline-run.py)保留。仅在[旧夹具](../../../../tests/integration/test_workspace_upgrade.py)DROP tuple补此表，固定pre-intake断言不变。完整58独立PASS、根88最终PASS；未改变产品schema或冻结结构快照。

## 未实现与NOT_RUN

本片7产品文件、3新测试、1旧夹具；DTO/schema18/依赖/UI/安装包和微信运行guard保持。A—C和D离线/代际来源底座保留；按代际实际收件与分发、可信官方微信身份及E有限期许可仍待，当前代际运行暂停。

全仓单进程、POSIX实际运行、网络UNC I/O、浏览器/安装版0.4.1、WorkBuddy本轮、真实微信登录/轮询/下载/发送、真实合同/产品模型/付费调用均NOT_RUN。UNC只有URI构造无联网。普通长路径writer、WIN-PATH-02目录rename WinError5、原生长进程AV未据本片关闭。没有安装机器人、连接账号、签发意见或自动外发。

SQLite依据：[官方URI文档](https://www.sqlite.org/uri.html)；以本机合成实跑为准，未引入VFS切换/rw回退/immutable/nolock。GitHub正常推送后另附回执；用户AGENTS保持不暂存。

证据文本发布时统一LF，log/XML仅去掉pytest输出行尾空白以通过Git检查；本机原始捕获保留，机器回执分别记captured与published摘要，未改47份运行输入。探针/基线脚本为原.local执行文件的文本存档，复跑须置回对应.local目录，不能按其发布目录推算workspace。
