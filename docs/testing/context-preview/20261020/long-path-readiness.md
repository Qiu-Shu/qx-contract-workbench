# WIN-PATH-01：旧合同原件长路径接续说明

**状态：只读接续准备，未实施、未新增测试执行，不纳入 CH-06B2b1 预览交付。**

依据当前源码和已保存的 `path-diagnosis.md`：本机旧合同 `create_version()` 在259字符的目标目录调用 mkdir 时触发 WinError 206；同一合成样本短路径完成解析、事实确认和mock。这里不把深目录问题说成本片回归，也不认为短basetemp规避就是应用已修复。

## 直接复用的现有实现

- `src/cn_contract/ops/file_paths.py:6` 的 `filesystem_path()`：只在文件I/O处把绝对Windows路径转为扩展路径，已支持现有扩展前缀和UNC；非Windows直接返回普通路径。
- 同文件 `application_path()`：把扩展命名空间前缀还原成应用路径，避免前缀进入数据库逻辑引用、JSON、用户显示和SQLite URL。
- `ops/backup.py:74` 的 `redirected()`，`:83` 的 `checked_root()`，`:94` 的 `checked_file()`：在I/O处使用上述helper，同时保留目录分量reparse/junction检查、根目录约束、单硬链接/普通文件检查、打开前后身份与大小检查。
- `assistant/attachment_files.py` 已完整覆盖 `stage → publish → read_checked → remove_uncommitted`：临时目录和真正文件句柄使用filesystem路径，发布不覆盖已有原件，清理仅操作本次创建的文件。
- `ops/workspace_backup.py` 已在清单扫描、文件reader、解包目标创建、密文发布、恢复发布、只读chmod及部分清理处复用helper。SQL连接、恢复返回值和逻辑relocation仍保持应用路径。

这些是现成能力，不建议写另一套Windows前缀拼装器，不修改系统注册表，也不把整个项目所有Path全局替换成 `\\?\`。

## 必须共同闭合的合同路径

| 位置 | 后续必须覆盖的实际操作 | 不可破坏的约束 |
| --- | --- | --- |
| `persistence.py:169`，`Database.__init__()` | 根路径abspath/resolve及mkdir；把逻辑根与I/O表示明确区分 | 不把扩展前缀传播进SQLAlchemy URL、JSON、storage_ref；不放宽根目录/junction检查 |
| `persistence.py:294`，`create_version()` | containment检查、UUID父目录mkdir、独占open、写入/flush/fsync、只读chmod、失败清理 | 身份与upload授权仍先行；`storage_ref`继续相对 `matter_uuid/version_uuid/original.bin`；不得覆盖原件或重算历史路径 |
| `persistence.py:278`，`read_original()` | resolve、is_symlink及read_bytes；可复用已有checked读取规则，适配位置留在底层 | 案件授权、版本身份、大小及SHA核对都保留；正常读和恢复HTTP都要实际覆盖 |
| `persistence.py:150`，`_remove_created()` | resolve/contains、exists、chmod、unlink、iterdir、rmdir全部使用一致I/O表示 | 仅删除该事务新建文件及已空的UUID目录；禁止递归删除；不得因前缀不同误判越界，也不得在检查失败后猜路径删除 |
| `persistence.py:213–239`，事务所有权hooks | `_remember_original`登记的path/root与 `_transaction_ended`清理所用形式保持一致 | root回滚、nested回滚、nested提交后outer回滚、Session.close均正确；旧已提交原件不能被清理 |
| `documents/ingest.py:83` 和 `parse_document()` | 继续通过修正后的create/read seam，不在上层另写路径分支 | MIME、基线、上传预算、原件不可变与解析锚点不变 |
| `web/recovery.py:85` | 恢复副本的原件下载实际调用 `persistence.read_original` | 不能只证明backup.checked_file能读，而恢复HTTP仍沿旧失败路径 |
| `ops/backup.py::_collect_files/_file_references`，`workspace_backup` 的 `_inventory/_references/_unpack/_fence` | 同一份合同原件跨备份、恢复、再备份的逻辑引用与真实文件一致；所有原件检查、chmod与恢复位置验证覆盖长路径 | 格式、加密、schema/fence与manifest原规则不变；不因long-path放宽hardlink/reparse/相对引用约束 |

`create_version` 的 mkdir 当前在其 try/cleanup 区域之前；后续需一并检查目录创建失败/部分创建后的所有权与清理语义，不应只把一处 mkdir 加前缀而留下后续 open/read/chmod/rollback 失败。亦不要顺手改变既有事务提交语义。

优先复用轻量 `ops/file_paths.py`。`ops/backup.py` 本身依赖persistence；若进一步复用checked读取，须避免在persistence模块顶层直接引入backup造成导入环，可保留现有局部导入或提取真正共享的轻量文件检查实现，但不要为此复制一套备份逻辑。

当前qxbak链已有多处适配；旧cnbak的写出/解包仍有直接 `Path.open/chmod` 调用，需要在WIN-PATH-01明确其支持范围与验证，不能凭qxbak测试宣称全部备份格式都支持任意长路径。SQLite的数据库路径和URL单独沿现有应用路径规则处理，不粗暴添加Windows命名空间前缀。

## 既有测试可复用，但尚不足以证明合同修复

`tests/integration/test_assistant_attachment_backup.py:126::test_long_parent_paths_create_restore_and_rebackup` 已覆盖附件原件父目录超过260字符、附件读取、qxbak恢复到长目录、再次备份恢复，以及扩展路径下拒绝硬链接。其输入走的是 `assistant/attachment_files.py`，**没有覆盖旧合同create_version/read_original**，因此不能以该用例存在宣称合同问题解决。

后续最小验证应扩展现有公开seam：

1. 复用 `tests/unit/test_versions.py` 的原件创建、读取与回滚场景，加入中文长根路径，实际目标父目录超过260字符；保存并读取同一字节，逻辑storage_ref不带前缀。
2. 将已有 `test_stream_failure_and_transaction_rollback_remove_only_new_file`、Session.close清理、`test_nested_commit_does_not_skip_outer_rollback_cleanup`、`test_nested_rollback_removes_only_child_original_and_parent_commits` 在长路径条件下运行。故障覆盖写入/flush/chmod/审计/最终commit，确认原件、计数、审计和事务所有权一致，旧文件不删。
3. 复用 `test_workspace_backup.py` 的合同原件qxbak流程：长路径导入 → 备份 → 长路径恢复 → HTTP原件下载 → 再备份恢复；每段字节/哈希/相对引用一致，恢复仍只读。
4. 正常路径/UNC表示或已扩展表示的无回归检查；保留hardlink、symlink/junction、越界、缺失原件和目的地别名拒绝。UNC网络共享若本机无真实条件，应记录未验证，不能以字符串单测冒充共享实测。
5. 再运行本次最小深/短路径诊断和受影响目标回归。无需为该任务重复法律数据导入或启用真实模型。

本轮仅读取上述实现、调用关系和测试源码，未改src/tests、未修改系统设置、未再运行测试。WIN-PATH-01应作为独立后续修复，和“预览代码通过关联验证”分开记录。
