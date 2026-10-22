# Desktop boundary fixture diagnosis

根因是测试夹具前提失效：全套使用项目 `.local` 下的独立 basetemp，`tmp_path` 因而已在默认允许目录内。产品 `_workspace_path` 按设计放行；旧用例却仍预期拒绝。

只修改 `tests/integration/test_desktop_runtime.py`：参照既有 `test_local_workbench` 夹具，用 monkeypatch 建立独立合成安装根；增加错误显式父目录拒绝断言。`local_server.py` 前后 SHA256 一致，没有放宽产品守卫或改用户配置。

- RED：原用例在全新项目内 basetemp 复现，1 failed，exit 1，症状为 DID NOT RAISE。原始日志为 GB18030，UTF-8 转读副本另存；首次打印日志的解码错误与 pytest 失败分别记录。
- 原因验证：同一路径只改变可信父目录上下文，6 项探针符合预期。
- GREEN：桌面运行测试全文件 8 项＋既有默认 `.local` 重启 1 项，共 9 passed，0 failed，exit 0，pytest 22.87 秒。覆盖默认内目录允许、显式外部父目录允许、错误父目录及穿越拒绝。
- `git diff --check`：exit 0。

完整命令、退出码、数量与哈希见 diagnosis.json、red.json、green.json；原全套结果未覆盖。本次未重跑全套，未触碰活动桌面或真实资料，未提交／推送；交主代理独立复核。
