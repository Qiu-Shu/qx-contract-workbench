Standards：硬违规0项，改进建议0项。
基线c0f9ae466344e5d585c04d6a9e3ff959a2b7b798；仅审4个暂存文件，新增提交为空。

- ingest.py:74、96保留静态导入及原验证、授权、持久化顺序，符合AGENTS.md后端核验与原件保护规则；两处import不值得增加代理层，符合ponytail最小改动原则。
- tests/integration/test_document_lazy_loading.py:23–82用隔离进程及合成材料验证加载和拒绝路径，符合AGENTS.md虚构测试要求。
- desktop/package.json:21和desktop/README.md:56使用现有构建配置并界定后续候选状态，符合执行计划Task3及AGENTS.md不得冒称完成规则。

未改代码、未运行测试或验证安装产物；打包与性能仍须实测。
