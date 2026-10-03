# 群兴合同审查工作台

当前已完成 T00 来源与许可门、T01 统一领域类型/schema/CLI、T02 案件权限/不可变版本/追加审计、T03 安全 DOCX/PDF 读取和锚点，并已安装 Scrapling 开发工具。**四类合同审查闭环正在建设，不能上传真实材料、签发正式意见或作为生产软件使用。**

现有目录最初为空 Git 仓库；用户确认无其他代码。本次为增量初始化，没有整仓替换、删除用户文件或复制A包运行文本。

实测产物：

- [现状差距与阻断](docs/BASELINE_GAPS.md)
- [任务实测与下一任务](docs/TASK_STATUS.md)
- [来源锁](sources/upstream.lock.json) 与 [复用记录](docs/reuse/)
- [T00测试证据](docs/testing/T00.md)
- [T01模型与审阅](docs/testing/T01-domain.md) 与 [独立审阅](docs/testing/T01-review.md)
- [T02权限和事务](docs/testing/T02.md) 与 [独立安全审阅](docs/testing/T02-review.md)
- [T03解析和锚点](docs/testing/T03.md) 与 [独立攻击审阅](docs/testing/T03-review.md)
- [Scrapling安装与使用](docs/tools/SCRAPLING.md)

在当前 Windows 项目目录运行：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/test_sources.py -q
.\.venv\Scripts\python.exe scripts/verify_defaults.py --file config/defaults.json
.\.venv\Scripts\python.exe -m cn_contract.cli config-validate
.\.venv\Scripts\python.exe -m cn_contract.cli schema --check
.\.venv\Scripts\cn-contract.exe --help
.\.venv\Scripts\python.exe scripts/verify_sources.py --mode development
.\.venv\Scripts\python.exe scripts/verify_sources.py --mode release
.\.venv\Scripts\python.exe scripts/scrapling_smoke.py
```

development模式核对实际文件和许可隔离，候选仍有生产警告。release目前必须返回非零：实际采用的G06 PDF解析组件及G10开发工具尚未完成生产使用范围/原生依赖/浏览器许可等审批，不能靠安装成功解除门禁。来源测试绿灯只表示门禁被测行为通过。

Scrapling安装在本项目 `.venv`，Chromium在 `.local/scrapling/browsers`，后续公开网页任务可复用。静态与动态抓取仅用本地虚构HTML验证，未接入QCC或合同审查。

T01 实测全套158项通过；覆盖领域/配置/CLI/来源门，尚不代表业务闭环。事实采用七类`{kind,value}`结构保持JSON往返类型；Decimal事实必须有单位。角色按规格四种命名，后续服务从数据库核对权限。

重建开发环境需Python3.12与Windows AMD64（其他平台另行生成锁）：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --require-hashes -r requirements.lock -r requirements-build.lock
.\.venv\Scripts\python.exe -m pip install --no-build-isolation --no-deps -e .
```

当前验证editable安装；应用/测试锁已扩展为35包，build1包单独锁，wheel hash及许可见[T03依赖审计](docs/reuse/T03-dependencies.md)。生产批准仍为空，独立wheel分发和部署未验收。Scrapling可按其专用锁另外安装，不要求审材料流程加载浏览器。

T02实际全套200项通过，包含42个新权限/事务用例；独立攻击审阅已关闭事务清理与缓存状态缺陷。HTTP测试保留1条上游TestClient/httpx弃用警告。基础服务用法见T02报告；正式签发仍阻断。

T03 最终实测全套269项通过；独立69目标及14攻击探针通过。DOCX未读对象和PDF扫描/注释/隐藏文字有明确缺口；文字层提取不代表视觉等价，OCR及PDF进程解码沙箱未部署。来源发布门仍阻断。

下一任务T04：事实人工确认、Decimal计算和主体歧义；先完成四类虚构合同、关闭QCC的审查闭环，再实现受控外查和批准版本的修订。法律规则、真实账户、数据政策和上线批准分别登记。
