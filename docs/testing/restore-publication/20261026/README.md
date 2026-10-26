# WIN-PATH-02：捕获自然失败，尚未定位拒绝来源

2026-10-26，基线 `498c0c978ee58f2856d741a2e62e9025bcbee73f`。本轮将原间歇恢复发布故障缩小为复用一份独立合成备份的秒级恢复循环，捕获 **6次首次rename自然失败**；其中5次原样抛错，1次仅在隔离实验中立即再次rename成功。**没有产品修复，WIN-PATH-02仍OPEN。** 未修改 `src/`、`tests/`、`scripts/`，644份前轮冻结输入逐项SHA仍一致。原生AV是另一开放项，本轮未诊断或关闭。

## 实际结果及计数

| 命令/实验 | 实际结果 | 解释 |
|---|---|---|
| 原 awaiting_facts 用例 | 1 PASS，exit0 | 单独通过，不能关闭故障 |
| 原 migration 模块 | 74 PASS，exit0 | 与下一组重叠 |
| 原 recovery 三模块顺序 | 76 PASS，exit0 | pytest按ID去重总计76，不是151；前两组独立进程运行有时间重叠 |
| 同一合成备份、深目录首次恢复 | 0 PASS / 1 FAIL | 0.782秒出现原发布rename WinError5 |
| 五种父目录长度，每种3次 | 14 PASS / 1 FAIL | 父目录176字符出现一次失败，206字符三次成功；不支持固定长度阈值解释 |
| 现有完整阶段观察器 | 40 PASS / 0 FAIL | 会改变时序，不能将与其他组差异解释为因果 |
| 仅失败后扫描自身句柄/游标 | 39 PASS / 1 FAIL | 失败后扫描成功，stage句柄空、存活SQLite cursor空 |
| 仅失败后加Restart Manager查询 | 15 PASS / 1 FAIL | 失败后3个stage文件查询成功、未捕获占用进程 |
| 仅失败后加原生文件/目录PID查询 | 23 PASS / 1 FAIL | stage及所有6个后代查询成功、未捕获PID |
| 只在隔离探针中立即再rename一次 | 80次调用返回成功，但有1次首次失败 | 首次WinError5、last NTSTATUS `0xc0000022`；相同rename约0.167毫秒后成功，无sleep、GC或ACL修改 |

前六个恢复实验共136次：131成功、5失败；最后80次实验改变了异常后的执行路径，必须单列，不能把80次返回成功说成原产品80次通过。诊断脚本捕获异常写JSON后正常退出0，**进程exit0不等于恢复PASS**，以每条`runs/status`及`events`为准。机器记录见 [verification.json](verification.json)；原样失败保存在 [stress](stress.json)、[路径对照](path-matrix.json)、[失败时句柄](failure-probe.json)、[RM](rm-probe.json)、[文件PID](native-probe.json)。

## 当前可以与不能断定的事项

- 真实恢复路径的发布rename再次失败，并非只用人为占用模拟错误；服务代码和原始加密备份均未改，所有实验核对备份SHA不变。
- 至少一次拒绝在立即再次调用时已不持续，支持“暂态拒绝”的线索；不能据一次结果规定重试次数，或断言已找到根因。
- 失败后的自身句柄、游标、RM及文件PID查询均有采样时差和覆盖限制；空结果不证明失败瞬间无占用，不能据此归因杀软、索引器、ACL或内核过滤器。
- 自身句柄观察器沿用仓库已验证实现。RM和原生文件PID探针先用独立合成子进程持有文件校准，均能识别实际子PID，释放后列表为空。原生查询使用内部class47，平台实现可能变化，只保留为实验材料，不进入应用、默认测试或后台监控。未停止、重启、提权或修改其他程序。
- 原生错误码取自第一次异常后立即调用`RtlGetLastNtStatus`，属于辅助观测，不代替直接I/O事件链。公开记录仅含合成路径、PID及状态，无真实合同、SQL内容、密钥或运行数据库。

## 复现与探针

在新目录生成同类合成归档：

```powershell
.venv/Scripts/python.exe -m pytest 'tests/integration/test_task_drafts_migration.py::test_restore_blocks_each_pending_execution_and_all_task_writes[awaiting_facts]' -q --tb=short --basetemp=.local/wp2-repro01xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

上述目录若已存在，应使用新的名称并在探针内对应修改；不要复用basetemp覆盖前轮证据。本轮实际测试的完整选择范围/命令约定为：单用例、`tests/integration/test_task_drafts_migration.py`、以及按顺序 `test_task_pdf_backup.py test_task_drafts_completed_backup.py test_task_drafts_migration.py`，均使用`-q --tb=short`、各自独立`--basetemp`和`--junitxml`，原始日志/JUnit保留于 `.audit-local/win-path-02-20261026/`。

低扰动复现入口是 [failure_probe.py](probes/failure_probe.py)，调用 `.venv/Scripts/python.exe -u docs/testing/restore-publication/20261026/probes/failure_probe.py`；读取上面已生成的合成归档，在新的`.local/wp2-failure01/...`中最多60次恢复，首个失败即保存并停止。父目录已存在时会拒绝运行。其他探针各有独立目录和次数上限；[immediate_probe.py](probes/immediate_probe.py) **会在实验中尝试第二次rename，不能作产品回归入口**。

随仓副本只改仓库根发现方式以适应证据目录位置，已做AST解析，未将“解析成功”说成再次执行实验；已执行原脚本和副本SHA均见verification。完整临时归档/数据库留在本机忽略目录，不上传。探针初始一次缺tests导入、一次错误比较venv启动器PID，以及一次复制命令引号错误均已如实记录；它们不算产品失败。包装时直接比较Git规范化JSON与CRLF工作树曾失败，改为核对前轮644份实际字节SHA后通过，不改任何夹具。

## 下一步与边界

下一步需要在失败的实际I/O时间窗捕获目录rename的拒绝来源（包括可能的目录句柄/内核层事件），以当前低扰动反例驱动；若取得可归因RED，再做最小修补与同路径回归。当前证据不足以修改权限、关闭保护软件、强制GC或加入产品自动重试。本轮不再重复完整阶段观察器和大套件来以PASS冲淡自然失败。

本片四开发门/Node/全仓长进程/安装版/真实微信或模型均NOT_RUN，产品未改变，不沿用前轮成绩冒充重跑。安装版仍0.4.1；用户AGENTS.md原改动保留。证据a02049e已普通推送，SHA/tree及6133项一致，见[同步回执](github-sync.md)。

独立[Spec](spec-review.md)和[Standards](standards-review.md)复核均0项发现：分别核对原JUnit、实验JSON、原始/随仓脚本摘要及644输入，不重复运行循环；认可计数与开放状态，不代表故障根因已定位。

API参考：Microsoft [RmGetList](https://learn.microsoft.com/en-us/windows/win32/api/restartmanager/nf-restartmanager-rmgetlist)、[RmRegisterResources](https://learn.microsoft.com/en-us/windows/win32/api/restartmanager/nf-restartmanager-rmregisterresources)、[NtQueryInformationFile](https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/ntifs/nf-ntifs-ntqueryinformationfile)；内部class47布局仅参考[原维护者头文件](https://github.com/winsiderss/phnt/blob/master/ntioapi.h)，不是稳定公开API承诺。
