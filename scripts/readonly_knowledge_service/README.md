# 只读法律知识服务：开发试点

本目录交付独立服务源码和虚构测试，供工作台维护者复现“提问 → 检索法条/案例 → 打开原文引用”。服务与工作台是同机的两个进程，通过带令牌的回环 HTTP 通信。

Git 不包含法律数据库、案例语料、原书、图谱数据库、模型权重或服务凭据。数据须在授权环境另行准备；目录存在不代表数据已交付。`assets/` 仅是被 Git 忽略的本机数据位置，启动时建议显式传入全部四个数据参数。

## 运行条件

- 工作台使用项目已有 Python 3.12 环境；本服务仅使用 Python 标准库。
- 先按[仓库根README](../../README.md)完成工作台开发安装，或将仓库 `src` 的绝对路径加入 `PYTHONPATH`；仅激活空虚拟环境不足以运行 `python -m cn_contract...`。
- Python 的 SQLite 必须支持 FTS5 与 trigram tokenizer。
- 服务只监听 `127.0.0.1`，工作台客户端只接受回环 HTTP。当前代码不能直接改成跨机器知识服务或公网 API。
- 两进程须通过各自运行环境注入同一个 `KB_SERVICE_TOKEN`（至少16字符）。使用随机令牌，不把它提交到 Git、写进命令参数或输出到日志。

## 启动服务

在仓库根目录、已激活项目 Python 环境的终端中运行。将以下路径替换为授权数据的实际位置：

```sh
python scripts/readonly_knowledge_service/kb_service.py \
  --legal-db /path/to/legal.sqlite \
  --corpus /path/to/corpus.jsonl \
  --cases /path/to/cases.jsonl \
  --case-root /path/to/casebook-markdown \
  --port 8790
```

`legal.sqlite` 需要既有 `documents`、`units`、`units_fts` 结构；`corpus.jsonl`、`cases.jsonl` 及 Markdown 原文必须来自同一套已核验数据版本，保留案例锚点、行号、字符边界及 SHA-256。具体最小结构可查看 `tests/test_service.py` 的 `build_fixture()`。该函数只生成虚构数据，不能代替真实资料的授权、来源和法律核验。

服务启动会验证凭据、数据文件和只读写入阻断；失败时拒绝启动。不要修改只读限制来绕过失败。

## 连接工作台

在工作台进程的运行环境中设置相同令牌，以及：

```sh
export KB_SERVICE_URL=http://127.0.0.1:8790
export KB_SERVICE_TIMEOUT=5
python -m cn_contract.web.local_server start --directory /path/to/workbench-workspace --port 8767
```

以上 `export` 是 POSIX shell 示例；Windows 使用等价的进程环境设置。首次创建工作区仍按工作台原有流程交互设置本机账户。不要在命令行传真实账户密码。

登录后可从工作台检索页查看法条/案例，或在主对话中使用“检索法律资料”；保存的引用按检索时版本回读原文，版本变化须拒绝，不自动替换成新内容。

服务接口为 `GET /v1/status`、`POST /v1/search`、`GET /v1/sources/{source_id}`，每次请求均需 `X-KB-Token`。外部输入只能提供受控来源 ID，不能提供任意文件路径。

停用时移除工作台进程中的 `KB_SERVICE_URL`，重启工作台即可。未配置时知识入口隐藏，知识路由不注册；不把这种状态描述成已接通。

## 不需要真实资料的测试

以下命令在仓库根目录执行：

```sh
python -m unittest discover -s scripts/readonly_knowledge_service/tests -p 'test_*.py' -v
node scripts/readonly_knowledge_service/tests/workbench_ui_check.cjs
python -m pytest tests/unit/test_knowledge_service_adapter.py tests/unit/test_knowledge_library_integrity.py -q
```

服务测试生成临时虚构数据库和 Markdown，启动真实 HTTP 服务，检查鉴权、检索、原文、版本及边界；不会读取随项目外部保存的真实知识库。Node 检查引用切换、迟到响应和关闭后的回填行为，不等同于实际浏览器或真实用户验收。

`tests/e2e_workbench.py` 与 `tests/e2e_main_chat.py` 是可选的实际 HTTP 复验脚本，要求已经在隔离虚构环境启动两个服务，并配置专用虚构账户。工作台脚本固定检索“违约金过高 适当减少”；需准备能命中这些预期词项的虚构法条与案例，不能直接将服务单元测试中以质量减价为主题的最小案例夹具当成这两个脚本的完整数据集。不要指向真实生产账户或资料工作区；这些脚本会在测试工作区创建会话和检索记录。运行前查看 `--help` 并选择对应的测试账户和输出位置。

## 验收边界

当前在线路径使用 SQLite FTS5/BM25 与案例检索。模型训练产物、Qwen 重排器及图谱数据库没有因此自动进入在线链路；检索命中不代表法律适用性已核验。本交付不是公网部署、Windows原生验收、并发容量承诺或生产批准。

v4 开发依赖基线、旧锁保留和合并注意事项见 [交接说明](../../docs/plans/2026-11-03-readonly-knowledge-service-handoff.md)。
