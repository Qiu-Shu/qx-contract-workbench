# 只读知识服务提交前验证

日期：2026-11-03。环境：Mac、Python 3.12，独立虚构测试数据；无付费模型请求、无部署。本记录仅描述待提交试点分支，不代表与后续主线合并后的验证。

## 本轮实跑

|检查|实际结果|
|---|---|
|知识适配、引用完整性、预算、依赖与发布限制、工作台页面、只读边界|213通过，0失败/错误，47.20秒，exit0|
|历史schema、上下文/法库迁移、工作区升级及微信历史保留|144通过，10项Windows跳过，0失败/错误，50.63秒，exit0|
|独立知识服务合成语料与真实HTTP测试|26通过，5.65秒，exit0|
|既有前端脚本|483通过，0失败/跳过，exit0|
|知识引用最小DOM交互检查|6通过，0失败；覆盖迟到响应、引用切换、版本变化和关闭后回填|

两组Python检查共357通过、10跳过；服务和前端检查单列，不重复计入该数。独立服务测试为本轮新增打包目录的实际运行；Node最小DOM检查不等同于实际浏览器或用户操作验收。本轮没有重新运行完整7423节点或使用真实资料重跑主对话HTTP贯通。

首次213项检查采用相对 `PYTHONPATH=src`，其中4个切换工作目录的子进程无法加载 `cn_contract.acceptance.pytest_evidence`，结果为209通过/4失败。保留该失败日志；随后使用当前仓库 `src` 的绝对路径，213项全绿。此修正只涉及测试进程环境，没有据此改变产品或断言。

## 可复制的命令

先使用项目Python 3.12环境，并将仓库 `src` 的绝对路径写入 `PYTHONPATH`，确保测试启动的子进程切换目录后仍能加载插件。

```sh
python -X utf8 -m pytest \
  tests/unit/test_knowledge_service_adapter.py \
  tests/unit/test_knowledge_library_integrity.py \
  tests/unit/test_library_budget_guard.py \
  tests/unit/test_runtime_dependencies.py \
  tests/unit/test_release_manifest.py \
  tests/unit/test_acceptance_evidence.py \
  tests/unit/test_mcp_bound_entry.py \
  tests/integration/test_assistant_pages.py \
  tests/integration/test_assistant_frontend.py \
  tests/integration/test_sqlite_readonly_boundaries.py \
  tests/acceptance/test_live_guards.py -q -p no:cacheprovider --tb=short

python -X utf8 -m pytest \
  tests/integration/test_assistant_library_schema.py \
  tests/integration/test_assistant_context_schema.py \
  tests/integration/test_workspace_upgrade.py \
  tests/integration/test_workspace_upgrade_semantic_preflight.py \
  tests/integration/test_weixin_personal_runtime.py::test_runtime_has_exact_successor_schema \
  tests/integration/test_weixin_personal_runtime.py::test_exact_successor_migration_preserves_every_predecessor_object \
  tests/integration/test_weixin_personal_runtime.py::test_runtime_history_survives_backup_but_restore_has_no_authority \
  tests/unit/test_windows_ocr_cleanup.py -q -p no:cacheprovider --tb=short

python -m unittest discover -s scripts/readonly_knowledge_service/tests -p 'test_*.py' -v
node scripts/readonly_knowledge_service/tests/workbench_ui_check.cjs
node --test scripts/test_*.mjs
```

## 历史全量证据的对应关系

2026-11-02全量记录为7378通过、45跳过、0失败/错误。提交整理前后，历史清单的1450个文件均逐个重算SHA-256，无缺失、无改变；其映射摘要仍为 `3ae1212d57bdad5cf9ea933c2616d4ff81b65a3724c56c83a5c8c550482581c7`。新增服务目录和交接文档不继承这次历史全量结论，分别验证与审阅。

活动依赖锁仍为 `f0f2793c945c207d16dc13e7d6ebef67f8320a07b69661fd62a9b288cbc7ce25`，旧锁按字节封存。生产门禁、Windows原生环境、真实模型/图谱接入和法律适用性不在本次提交前通过结论中。

## 暂存内容检查

暂存区312个文件不含真实知识数据库、案例语料、原书、模型权重或运行凭据。活动锁、构建锁及两个冻结计算回放输入的Git暂存blob与已复核磁盘字节完全一致。

项目原生 `scan_staged` 检查312项，报告3项，原始结论为不通过，未修改扫描器或增加白名单：FastAPI的 `oauth2.py` 命中变量 `client_secret` 传参；MCP的两个认证模块命中同名变量传参及类docstring中的公开示例，均经AST/文本分类，不是本项目运行凭据。cryptography wheel的 `_rust.pyd` 为9,897,472字节，超过扫描器8MiB单成员上限；该wheel与活动锁大小/SHA一致，全部120成员解压总量约10.5MB，压缩比无异常。对该扩展另做未执行的原始字节模式检查，四类原生秘密正则均0命中。

以上是固定官方依赖的误报分类和扫描上限补查，不把原生扫描报告改写成PASS，也不等同于原生扩展内容安全、供应链或生产批准。
