# CH-07C2b1 schema/迁移实现子任务

基线：`e133d5c39475388c6f8763d488cbbf3808e6855e`。工作目录：`D:\Documents\ChatGPT\律所项目`。只使用独立合成数据库；未接触活动桌面库、真实资料、模型、网络服务、registry/native/runner/HTTP。无提交或推送。

## 已实现

- 新版本 `assistant-profile-model-v1`；固定 13 条语句重建 attempts 的格式 CHECK，并新增 `assistant_profile_handlers` 及不可变 UPDATE/DELETE 触发器。旧 STATEMENTS 未改。
- handler 固定 `profile.save/1`，事件复合键、attempt/output 唯一、profile receipt 复合外键与唯一关系；applied/unchanged 与 blocked 的空值关系闭合，basis 摘要要求 64 字节小写 ASCII hex，拒绝 NUL 尾缀及 BLOB。
- 复用三条通道：隔离 database-only upgrade、原生 workspace_upgrade、初始化；新增版本登记 FK OFF 重建窗口，提交前 FK 校验，失败完整回滚并恢复 FK ON。原生产品迁移代码未改。
- 旧 model/context/rounds/rounds_v2 initializer 精确识别新后继结构；新 initializer 同时验证完整 model/context/profile/handler family，不修补缺损家族。
- 修改前冻结 11 版本 × native/普通 × 原始/规范化共 44 个摘要于 `tests/fixtures/profile_model_schema_predecessors.json`。
- 原生测试 legacy 夹具移除新 handler 表；新 target 加入 marker 中断、DDL 失败和 pending 篡改矩阵。五个 integrity 文件由 root 独立负责，本子任务没有修改。

## 运行证据

1. `red.log`：`test_upgrade_opens_profile_format_but_not_unknown_formats`，exit 1，1 failed；旧 CHECK 实际拒绝 profile-text-v1，属于有效 RED。
2. `nul-red.log`：NUL 尾缀摘要反例，exit 1，1 failed；SQLite 文本 length/GLOB 截断导致 DID NOT RAISE。
3. `nul-green.log`：增加 BLOB 字节长度检查后，同一反例 exit 0，1 passed / 6.26s。
4. `green1.log`、`green1.xml`：新 schema、既有 profile schema、storage bootstrap 三文件，exit 0，176 passed / 326.13s。此为开发运行：开始后追加了 NUL 反例及 5 个 FK/initializer 探针，产品也修过 NUL，因此**不能作为最终固定输入运行**。本轮没有重跑同批，由 root 的统一最终回归覆盖当前文件。
5. `fk.log`、`fk.xml`：新增 initializer 中途/完成后 DDL 故障、initializer 与 staging 的 dangling FK 回滚，exit 0，5 passed / 105 deselected / 20.62s。
6. 所属文件 `git diff --check` exit 0。最终冻结 13 文件 SHA 保存在 `owned-inputs.json`；root 已收到冻结通知。当前新 schema 文件共 110 项测试。

目标运行命令均采用项目 `.venv/Scripts/python.exe -m pytest`，具体选择分别为新测试单例、NUL 单例、上述三文件，以及新文件 `-k 'initializer_failure or staging_upgrade_rolls_back'`；`--basetemp`、日志、JUnit 均在本目录的不同独立子路径。测试进程均已结束。

## 限制与交接

新格式与非空新 handler 的 fail-closed 历史验收由 root 负责实现与验证；本子任务没有自动保存、授权或外发路径。新表的跨 attempt/output/event/profile 同一次执行语义由后续完整 validator 承担，此时不得把 SQLite 外键自洽当成已审核归档。root 的统一回归、独立审阅及提交仍待其完成。未运行全套，不代表 WIN-PATH-02、安装器或真实供应商验收。
