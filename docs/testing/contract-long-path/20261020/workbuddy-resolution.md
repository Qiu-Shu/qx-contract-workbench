# WorkBuddy 本轮连接与意见核对

本轮 `workbuddy_status` 显示 connected=true，端点为本机 `127.0.0.1:58176`；随后任务 `wb-b9aff7ba1c57` 实际 completed/end_turn。权限回执显示恰好成功 Read 3 个文件：前片长路径准备说明、修复前 persistence.py、现有 file_paths.py；未改写、执行或联网。见 [完整回执](workbuddy-review.json)。这是本轮静态方案复核，不冒充修复后的运行验收。

| 意见 | 主代理核对与处置 |
| --- | --- |
| mkdir 在 try 前可能留下目录，建议必须先修 | 保留独占目录创建在所有权登记之前。创建失败尚无原件、配额或审计写入；外层事务仍负责回滚，并非“try 外就没有回滚”。将整个 mkdir 移入无条件删除分支会误删预先存在的 UUID 目录。可能剩余的空案件父目录不是原件或有效业务记录，本片不递归清理共享父目录。新测试覆盖目录创建失败和 UUID 碰撞；独立 Spec 另验预存 marker 不被清理。 |
| 登记与回滚的前缀表示需一致 | `_remove_created` 入口把 path/root 都归一为 filesystem_path；原事务所有权及嵌套移交不改。写、flush、fsync、chmod、审计、最终 commit、nested、close 故障均实测。 |
| storage_root 初始化及原件 read 需要一起适配 | 构造使用 filesystem_path 做实际 mkdir，application_path 保留应用根；create/read/cleanup 均复用同一轻量 helper。read 的路径检查 OSError 继续返回固定 VERSION_CONFLICT。无 schema、DTO 或 SQLite URL 改动。 |
| Windows resolve 与前缀需实际验证 | 新单测包含普通与已扩展输入、原件根自身超过 285 字符，以及双端包含关系。qxbak 实际恢复下载和独立探针补验；实际 UNC 网络共享仍未验证，不以字符串往返代替。 |

没有据这次意见改写已有备份算法或新增另一套前缀实现。最终判断以合成实测、独立 Spec/Standards 和当前源码为依据。
