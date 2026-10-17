# 对话历史分页与任务找回

2026-10-17；基线cfc380123feec043f7affb2829758761e59eb3bb。复用既有assistant表和权限服务，没有增加数据库、迁移、依赖或运行器。开发和实测均为独立合成材料，安装版及真实资料保持原状。

## 已实现

- 对话HTTP读取默认最多50条消息，向前加载使用属于同一对话的消息UUID游标；不先下载全部历史再切片。返回最近持久任务的身份、状态和事件序号摘要。
- 新增当前对话内按原请求ID查询任务的只读接口。刷新／重开可以找回旧请求；查询未找到不能作为换新幂等键重发的依据。
- HTTP创建重放及草稿保存也返回最多50条。原服务默认完整读取保持兼容，分页参数在任何写入前校验。
- 恢复副本允许精确的只读查询；旧会话仍失效、未完成任务保持blocked、写入仍拒绝。运行摘要不授权自动续跑，也不表示模型正在执行。

## 本轮实际验证

| 检查 | 结果 |
|---|---|
| 服务目标及原存储／控制回归 | 124通过，其中27项新增；53.60秒，exit0 |
| HTTP目标及原路由回归 | 15通过，其中5项新增；8.73秒，exit0 |
| 备份、恢复、旧库升级关联回归 | 79通过；111.70秒，exit0 |
| 独立Windows冻结后端 | 构建exit0；4组实际EXE检查通过 |
| schema／默认配置／来源／依赖开发门 | 四项均exit0 |
| 独立Spec／Standards复核 | 各0项确认问题，仅静态审查 |

三批JUnit逐项去重共218个不同测试，0失败／错误／跳过；新增32项包含其中，不另相加。未重新运行整个仓库全套；上轮2,042项仍是cfc3801的历史证据。

服务有效RED为缺接口／参数3失败，另24未选中。第一次夹具试图修改不可变时间戳失败，保留该日志但不算产品RED；改为插入时合成时钟后取得有效失败。HTTP有效RED5失败，分别暴露全史读取、缺参数校验、缺任务摘要及缺路由。修复后的实际结果见上表。

冻结验证在中文带空格独立目录中，实际提交51条HTTP消息、取消前50项，核对两页无重复遗漏；重启后找回原queued任务及未发送草稿，重放同键同内容仍是原任务且仅1个事件；创建并自检加密备份，恢复后原消息顺序不变、最近任务blocked及2个事件，旧会话401、额外路径和写请求409。这是后端EXE验收，未制作／更换安装器，也未验新首页界面。

## 复现与证据

原始记录在`.local/chat-history-20261017/`；[summary.json](summary.json)保存实际计数、退出码、原始字节摘要、候选EXE及加密归档摘要。核心命令使用现有`.venv/Scripts/python.exe`：

```text
-X utf8 -m pytest tests/integration/test_assistant_history.py tests/integration/test_assistant_storage.py tests/integration/test_assistant_control.py -q --tb=short --junitxml=.local/chat-history-20261017/service-green.xml
-X utf8 -m pytest tests/integration/test_assistant_history_routes.py tests/integration/test_assistant_routes.py -q --tb=short --junitxml=.local/chat-history-20261017/routes-green.xml
-X utf8 -m pytest tests/integration/test_assistant_backup.py tests/integration/test_workspace_upgrade.py tests/integration/test_workspace_backup.py tests/integration/test_backup_restore.py tests/integration/test_assisted_backup.py -q --tb=short --junitxml=.local/chat-history-20261017/related.xml
-m PyInstaller --noconfirm --distpath .local/chat-history-20261017/backend --workpath .local/chat-history-20261017/build desktop/backend.spec
-X utf8 .local/chat-history-20261017/frozen_history_probe.py
```

构建只在子命令期间将PYTHONPATH指向现有`.local/desktop-tools/python-build`，随后恢复；没有新增环境或依赖。构建保留现有可选tzdata等隐藏导入警告，实际中文路径启动／备份恢复已执行；构建退出成功不等于完整桌面安装验收。

## 限制与后续

WorkBuddy本轮实际连通并完成任务`wb-f32b9b6db083`的3文件只读复核；意见逐项核对见[review.md](review.md)。它读取的是实施前源码，不能称为最终实现验收。

内部rowid排序沿用现有不可变消息和文件备份路径。UUID每次重新解析，避免客户端依赖旧rowid数值；未来VACUUM、逻辑导入或跨库迁移仍需显式持久排序设计。[SQLite官方说明](https://www.sqlite.org/lang_vacuum.html)指出VACUUM可能改变没有INTEGER PRIMARY KEY表的rowid。本次不把文件备份实测扩大为云端迁移保证。最多物化51条消息也不等于数据库扫描时间恒定。

尚未完成聊天首页、建案前附件、主模型／Jev、自动档案或新的Windows安装包。下一步按[首页接线检查](../../../plans/2026-10-17-chat-home-readiness.md)实施页面及失败／切换状态。
