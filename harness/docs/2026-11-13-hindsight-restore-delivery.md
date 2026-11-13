# 真实 Hindsight 的同版本恢复验证

2026-11-13，接续 `69590054d0f82a26dfac988ac339f428c6d0d2fb` 和[本轮计划](2026-11-13-hindsight-restore-plan.md)。新增真实 Hindsight 1.2.0、PostgreSQL 18.1、pg0 0.15.2、restic 0.19.1 与本机来源账本的可重复集成验证。现有产品实现无需修改；本轮改动为测试、合成夹具及交付记录。未构建安装包或更新安装版。

## 实测范围

- 从空 Hindsight 数据库实际执行迁移；数据库 `alembic_version` 为 `c7e2f9a4d1b8`，与固定 wheel 的迁移头一致。源库重启、恢复副本及副本再次重启后的迁移版本和集群身份均一致。这是同版本冷备恢复，不是跨 Hindsight 版本升级实验。
- 通过真实 `CaseMemoryStore` 创建两个合成案件，各选择一条中文来源记录，经真实 Hindsight retain 接口保存。查询故意使用原文不含的词，强制断言 `mode=hindsight`、原记忆及来源完整一致，避免把关键词兜底当成成功。
- 正常停库后通过现有加密备份及新目录恢复入口操作；恢复交付目录保留审核标记，普通运行入口仍拒绝。仅复制业务账本和数据库到明确命名的合成启用夹具，验证未来启用的前提。
- 原库、恢复副本和再次重启的副本具有相同 bank、记忆、文档及来源标识，两个案件仍隔离。恢复后的读取和 `sync` 没有增加模型抽取次数，无需重建索引。
- 副本新增后有 3 条记忆，原库仍为 2 条，原有来源可再次读回。每次运行只管理本轮随机创建的实例登记，停止后删除这些登记与合成目录。

Hindsight HTTP 服务、数据库、迁移和应用适配器都使用真实实现；仅外部 LLM 和 embedding 接口为本机固定合成响应。正常目标运行包含 4 次合成抽取和 14 次合成 embedding 请求，真实付费模型请求为 0。常量 384 维向量不能证明语义排序、中文理解或模型质量，也没有验证生产 ONNX 模型资源的加载与换机迁移。

测试 Python 进程通过单独 `sitecustomize` 审计钩子拒绝非本机网络，另有明确外网域名被拒绝的检查；这不是系统级防火墙或整个 pg0 子进程树的网络隔离声明。原生 PostgreSQL 使用既有固定缓存，产品的网络规则没有被改写。

## 环境与验证记录

独立环境位于 `harness/.local/hindsight-restore-runtime/venv`，从现有 `packaging/case-memory-requirements.lock` 以摘要校验安装，无依赖升级。准备命令需清空继承的 `PYTHONPATH`，并用 `--ignore-installed --no-deps --require-hashes --only-binary=:all:`；完成后 `pip check` 退出 0。原始安装曾因开发路径中的包被视为已安装而缺少组件，已保留失败检查与重装日志，未将其算作产品缺陷。

原生测试初期还修正了测试钩子对 bytes 形式本机地址的误判，以及 Windows 换行断言；保留原失败日志。真实恢复流程随后通过，没有由这些夹具失败推导出产品修复。

目标命令 `node --test desktop/hindsight-restore.test.cjs` 实跑 2 项通过、0 跳过、退出 0。最终完整 `npm test` 退出 0：Node 464 通过、2 跳过；Python 472 通过、1 跳过及 36 子测试。目标用例已包含在完整回归，不重复相加。详细命令、源码/证据摘要及最终状态见[验证记录](checks/hindsight-restore-20261113.json)；原日志位于 `D:/CodexChecks/AI-Shixiong-hindsight-restore-20261113`。

Spec 独立原生复跑 2 项通过，发现 0；Standards 发现测试清理 P2：首个停止失败会跳过其他实例清理。现已逐实例/逐登记收集失败，继续清理健康实例，保留未确认停机的目录，最后汇总报错；原故障探针复验退出 0，Standards 未解决 0。最终完整回归在该修复后运行；Spec 对清理增量另作静态复核，未将此前原生运行冒充最终文件重跑。

三个早期失败的合成临时目录因自动审批返回 `blocked by policy` 而未删除，没有改用其他方式删除；具体路径在验证记录中。后续正常测试已清理自身合成业务目录与实例登记，独立测试环境保留供下一阶段复用。

重跑前加载 `.local/audit-0216/build/test-env.ps1`，另设 `QX_TEST_HINDSIGHT_PYTHON` 指向上述隔离解释器，`QX_TEST_PG_TOOLS` 指向已校验的 PostgreSQL 18.1 目录，`QX_TEST_RESTIC` 指向固定 restic。完整回归还设置 `QX_TEST_PG0_MODULE` 以运行上一轮 pg0 原生用例。缺少这些前提时原生测试明确跳过，不能据普通离线通过称已验收真实 Hindsight。

实现依据为固定 wheel 自带的 `hindsight_api/config.py`、API、迁移及模型接口代码；[官方配置文档](https://hindsight.vectorize.io/developer/configuration)仅作参数入口参考，未用滚动文档替换固定版本源码。

## 下一步

恢复副本仍是未启用状态，`applicationComplete:false`；本轮测试不会自动移除具体副本的审核阻断。接下来处理设置实际应用、凭据重新授权、待办处置及明确人工激活与桌面入口。真实 ONNX/模型语义、断电、磁盘写满、大数据及跨机验收仍待；安装包继续暂缓。
