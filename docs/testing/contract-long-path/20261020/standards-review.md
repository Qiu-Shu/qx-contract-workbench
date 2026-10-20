# WIN-PATH-01 Standards 独立审查

基线 `7446a9ce47d9452568f7d2ea1cf53c92167d53f4` 至当前工作树；审查 persistence.py、两份新增测试及实施计划，并核对复用的 file_paths.py 与 ops 包初始化。输入摘要见 standards-evidence.json。

## 结论

待修硬违规 0，需采取的 smell 建议 0。未发现本片引入原件覆盖、清理所有权或权限退化。依据 AGENTS.md 原件/审计不可覆盖、后端核验，以及 CONTRIBUTING.md 复用现有机制与真实证据要求：

- persistence.py:26、:172–173 直接复用轻量路径 helper；ops/__init__.py 无运行导入，file_paths.py 仅依赖 os/pathlib，不产生 persistence→backup→persistence 循环。扩展前缀只进入 I/O，storage_root 仍为普通路径；storage_ref、DTO 与 SQLite URL 未改。
- :151–160、:315–366 保留根范围检查、非递归删除、独占创建、事务登记及既有回滚 hooks，仅统一 I/O 表示。UUID 冲突在目录创建时失败，未进入本次文件清理；已提交原件仍由旧事务拥有。未改变提交语义或引入第二套文件封装。
- :281–294 保留先授权、版本身份、根约束、符号链接、大小及 SHA 校验；resolve/read 的 OSError 转固定 VERSION_CONFLICT，不回传路径。备份硬链接拒绝沿用 checked_file，不能称 read_original 新增了同等全部文件安全检查。
- 新测试使用独立合成合同，真正创建超过 260 字符父目录，覆盖失败与事务生命周期；计划明确 qxbak、UNC、SQLite 路径及安装包的不同边界，未扩大验收陈述。

## 独立实测

Windows / Python 3.12.14，短 D 盘新临时根：嵌套回滚、UUID 冲突、原件缺失固定错误、合同 qxbak→长路径恢复→HTTP 下载→再备份恢复，共 4 passed / 11.93s / exit 0。1 个既有 record_property/xunit2 警告。原件父目录 280 字符、恢复后 281；DB 路径 209，内容 SHA 与相对引用保持。命令/日志/XML/摘要均为 standards-*。

首次命令因 PowerShell 参数拼接把 --basetemp 拆成空参数，pytest 在收集前 exit 4；失败原样保留，修正调用后才得到上述结果，非产品失败。

未广跑或验真实资料、模型、安装器、实际 UNC、任意长 cnbak 目标、超长 SQLite 数据库。旧深目录缺陷与本片修复分开；本审查不宣称 Windows 所有路径问题均解决。
