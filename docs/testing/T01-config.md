# T01 配置与CLI实测

2026-10-02，Windows CPython3.12.14，Pydantic2.13.5。

RED实际命令：`.venv/Scripts/python.exe -m pytest tests/unit/test_defaults.py tests/unit/test_cli.py -q --tb=short`；退出1，14 failed。配置为实现缺失断言，CLI为不存在模块；没有语法或收集错误。

首次实现后同命令退出0，14 passed。独立审阅指出默认校验脚本忽略规范`--file`；新增实际子进程断言，先退出1（3 failed、4 passed），修复参数读取及错误处理后CLI/配置17 passed、退出0。不存在/损坏文件返回CONFIG_INVALID，合法但偏离基线的配置返回DEFAULTS_HASH_MISMATCH；错误不打印文件内容。

保存schema过期检查及当前schema一致性为另外两项验证，CLI目标9 passed，退出0；`--check`不会覆盖过期文件。schema实际生成/检查命令均退出0。领域审阅修正前全套108 passed只是当时过程证据，最终分母见T01-results.xml与T01-review.md。

基线hash独立重算为`0e4acba46c67b731cd9662d7b118217ddc55047ab69315961c7f78dfcfa9c887`。实际editable安装`pip install --no-build-isolation --no-deps -e .`成功；已安装控制台`cn-contract --help`和`config-validate`退出0，`pip check`退出0。应用/测试11包及build1包分别执行本地wheelhouse `--dry-run --ignore-installed --require-hashes --no-index`成功，这不是完整生产恢复演练。

单一默认JSON按规格原数值落盘；严格设置禁止未批准真实服务、自动对外发出、文件或类型范围扩张。更低资源限额允许并产生新哈希；管理员批准配置更新审计在后续任务实现，本阶段不伪造批准。
