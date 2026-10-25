# Windows SQLite只读长路径修复计划（2026-10-25）

基线916d55bf47ffb513508b81c5ebf40a5482372a67，实际workspace D:/Documents/ChatGPT/律所项目。沿用已批准无人值守、最小充分修复、TDD和正常推送，不扩大真实微信/模型/合同授权；用户AGENTS不纳入提交。复用Ponytail、systematic-debugging、TDD、verification-before-completion及diagnosing-bugs，现有需求/授权不重复访谈。

## 已有诊断与范围

- 本轮原失败用例实跑1FAIL，精确在恢复后二次qxbak的_validate_database(snapshot) SQLite只读打开；上轮冻结基线已复现。当前普通as_uri对长Windows路径失败，扩展Path.as_uri把?前缀变为非法authority；独立探针已比较原生路径整体百分号编码，保持mode=ro成功。
- 普通backup手拼URI还把literal%23.db误读为literal#.db；同一个I/O编码问题，应共享修复。计划在ops/file_paths.py追加sqlite_readonly_uri，以filesystem_path保留Windows长路径命名空间，再对原生路径编码；不解析/跟随symlink、不改存储引用、不增加rw回退/immutable/nolock/VFS切换。
- 产品8处只读URI入口（6调用文件）接共用helper：ops/workspace_backup两处，ops/backup一处，web/local_server两处，web/workspace_upgrade一处，library/catalog和library/service各一处。保留各自权限、路径/硬链接、schema/integrity、worker lock和trusted_schema检查原位。
- 原用例通过URI验证后，又在_references的SQLAlchemy连接处暴露相同长路径问题。直接把扩展路径放入URL会将?误解析为查询；以局部do_connect在DBAPI边界补回原生命名空间，保留逻辑URL、中央Database类和其PRAGMA/事务监听。不修改中央普通SQLite读写引擎、数据库结构/DTO/依赖/安装包/UI；不能把本片修复称为所有Windows长路径支持。旧WIN-PATH-02的WinError5与原生长进程崩溃保持独立OPEN。

## 执行与验收

- [x] 读AGENTS/TODO/TASK_STATUS/最近证据/来源规格、当前Git/远端；复用知识库与CodeGraph，保留用户AGENTS。
- [x] 原旧测试在87字符basetemp实际RED；独立合成SQLite路径/编码/只读探针。
- [x] 新helper16FAIL，独立边界6FAIL/2PASS，新增快照1FAIL；最小共享URI与局部DBAPI修复后新增25不同用例根/独立两次全PASS，不叠加计数。保留中间失败与一项相对引用测试预期更正。
- [x] 原长路径旧例实际GREEN，中文/百分号/#/长路径只读、禁止写入、缺失不创建、源字节不变、普通/原生两种备份与恢复隔离；关联本机升级/资料库回归。
- [x] 独立Spec/Standards复核；记录命令、退出码、不同用例与输入SHA；未跑NOT_RUN。
- [ ] 更新状态与实际证据，扫描授权文件，正常fetch/commit/push核远端SHA/tree。
- [ ] 同一脱敏摘要完成HumanLayer/Obsidian收尾；TencentDB正常Stop待提炼。旧同步文本接近Windowsargv限制，必要时保留pending且准确说明，不能修改别的聊天/恢复五分钟任务。

## 一手依据

SQLite URI的mode=ro、百分号编码和authority规则：https://www.sqlite.org/uri.html 。只凭当前运行时实测确定本机行为；不因官方VFS另有长路径选项而引入额外配置。

实际最终证据：[20模块289不同Python/233Node/四开发门，含夹具RED及单处修正](../testing/long-sqlite/20261025/README.md)。按代际运行与可信微信/E仍待。
