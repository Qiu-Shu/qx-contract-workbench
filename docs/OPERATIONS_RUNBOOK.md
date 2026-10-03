# 本机运维说明（T12）

只支持 Windows 上本机单实例、独立虚构数据和显式 worker 的开发演示。生产 host、HTTPS、OS 沙箱、真实 provider、法律 gold 及密钥托管未具备，不能按此说明宣称已上线。

## 启动与停止

使用本项目 `.venv/Scripts/python.exe`。演示入口为 `python -m cn_contract.cli demo-server --port 8765 --directory <本项目.local内全新目录>`。绑定固定 `127.0.0.1`；目录必须是新目录，不能覆盖旧案库。虚构经办、复核、助理及管理员采用演示初始化的本机身份；该初始化不能代替真实律师批准。不要同时启动第二个 worker。

外查默认关闭。测试用的显式 loopback 注册只用于工程联调，不能启用真实 QCC。停止服务使用启动 terminal 的正常中断；真实工具的中断退出码要如实记录。退出后不自动重发 running 任务，unknown 费用通过已有账本对账。回滚仅选择已保存代码提交和新的受控数据库目录，不覆盖历史数据库或原件。

## 备份与验证

受保护服务器 API：`backup_and_verify(config, database=..., actor=..., key_resolver=..., restore_parent=...)`。`config` 的 `storage_ref` 是受控归档目录，`key_ref` 由显式服务器 key resolver 解析，`retention_days` 是工程配置并非法律保留期限。当前 resolver 仅接受明显虚构测试材料，生产不可使用公开测试密钥。没有自动按期删除功能。

备份要求实际管理员会话，完整当前 SQLite schema 和注册的独立虚构原件 hash。通过 `BEGIN IMMEDIATE` 写屏障与 SQLite native backup 固定数据库和被数据库引用的不可变文件；不复制运行中的主 DB 文件，也不把未引用缓存打包。AES-GCM 认证版本/归档身份/header，随机 nonce；归档不存密钥。得到完整 manifest 后逐个核验表摘要和原件、报告、修订文件的 byte size/hash。

恢复入口 `restore_backup(backup_ref, key_resolver=..., restore_parent=..., settings=...)`，或使用上一个已验证报告 `open_restored_database(report, settings=...)`。解密、类型、ZIP allowlist、相对路径、大小/数量/压缩比、schema/FK/触发器/表摘要及记录与文件对应关系先验。成功安全变更与文件核验完成后才把 staging 目录作为新恢复 root 发布；中途失败清理仅本次新 staging，原库和归档保留。

恢复后旧会话全部失效，需要重新登录。所有待执行任务隔离，unknown 积分/call_count 不归零，任何新发送仍 BLOCKED。普通读原件及授权历史对账可用；当前修订/导出须先完成真实最新高水位核对与批准，本轮没有自动解隔离。恢复后重开一个新 Database 并用普通 worker/Factory 接口核验零发送，不能依赖某个 Python 对象临时 flag。

实际演练至少检查：原件和每种 audience 的历史制品在源目录不可用时仍从新 root 读出；原不可变行 hash 不变；unknown15/预算20 仍余额5；再申请15返回实际 `BUDGET_EXCEEDED`；queued/running 隔离和零重发；旧 session 无效；完整 SQLite integrity/FK/不可变触发器保留。归档存在或单独可解密不算恢复通过。仅独立虚构 fixture 和受控临时目录可进行故障注入或暂时改名，绝不操作用户真实材料。

## 发布清单

`python -m cn_contract.cli release-manifest --mode development --output .local/<新文件名>.json` 绑定服务器固定 source lock/config 和实际提供的本机规则、测试、部署证据 bytes。可重复提供 `--rule-evidence`、`--test-evidence`、`--deployment-evidence`。普通 JSON 中的 `approved`/`GO` 不能授权；这些引用只证明当时 bytes，不证明律师批准或与当前源相同。旧 T11 报告的日期、hash、源范围保留为历史证据，不能刷新原报告。

`--mode production` 在缺真实许可/法律样本/host/OS/TLS/数据政策/密钥管理/当前测试证据时实际非零并不输出生产清单。source release 和 runtime release 是分别执行的真实门禁；安装成功与开发 manifest 都不是生产批准。保存实际 argv、退出码、UTC、报告/JUnit hash 和 source 范围，保留首次失败与后续修复证据。
