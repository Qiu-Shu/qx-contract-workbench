# 群兴合同审查工作台

当前已完成 T00 的仓库/附件审计、13项来源登记、来源与许可门验证，并按用户要求安装 Scrapling 开发工具。**合同审查应用尚未实现，不能上传真实材料、签发正式意见或作为生产软件使用。**

现有目录最初为空 Git 仓库；用户确认无其他代码。本次为增量初始化，没有整仓替换、删除用户文件或复制A包运行文本。

实测产物：

- [现状差距与阻断](docs/BASELINE_GAPS.md)
- [任务实测与下一任务](docs/TASK_STATUS.md)
- [来源锁](sources/upstream.lock.json) 与 [复用记录](docs/reuse/)
- [T00测试证据](docs/testing/T00.md)
- [Scrapling安装与使用](docs/tools/SCRAPLING.md)

在当前 Windows 项目目录运行：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/test_sources.py -q
.\.venv\Scripts\python.exe scripts/verify_sources.py --mode development
.\.venv\Scripts\python.exe scripts/verify_sources.py --mode release
.\.venv\Scripts\python.exe scripts/scrapling_smoke.py
```

development模式核对实际文件和许可隔离，候选仍有生产警告。release目前必须返回非零：已安装的G10开发工具尚未完成传递依赖/浏览器许可及生产批准，不能靠安装成功解除门禁。来源测试绿灯只表示门禁被测行为通过。

Scrapling安装在本项目 `.venv`，Chromium在 `.local/scrapling/browsers`，后续公开网页任务可复用。静态与动态抓取仅用本地虚构HTML验证，未接入QCC或合同审查。

下一任务T01：统一类型、默认配置、schema和CLI；后续先完成四类虚构合同、关闭QCC的审查闭环，再实现受控外查和批准版本的修订。法律规则、真实账户、数据政策和上线批准分别登记。
