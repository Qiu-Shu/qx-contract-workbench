# 群兴合同审查工作台

当前已完成 T00–T06 的来源、统一类型、权限、解析、事实、规则批准门及四类虚构合同审查闭环，以及 T07 固定 SDK 的本机 MCP 模拟发现、批准绑定和调用，并已安装 Scrapling 开发工具。**仅限虚构工程演示；不能上传真实材料、签发正式意见或作为生产软件使用。**

现有目录最初为空 Git 仓库；用户确认无其他代码。本次为增量初始化，没有整仓替换、删除用户文件或复制A包运行文本。

实测产物：

- [现状差距与阻断](docs/BASELINE_GAPS.md)
- [任务实测与下一任务](docs/TASK_STATUS.md)
- [来源锁](sources/upstream.lock.json) 与 [复用记录](docs/reuse/)
- [T00测试证据](docs/testing/T00.md)
- [T01模型与审阅](docs/testing/T01-domain.md) 与 [独立审阅](docs/testing/T01-review.md)
- [T02权限和事务](docs/testing/T02.md) 与 [独立安全审阅](docs/testing/T02-review.md)
- [T03解析和锚点](docs/testing/T03.md) 与 [独立攻击审阅](docs/testing/T03-review.md)
- [T04事实与计算](docs/testing/T04.md) 与 [独立信任根审阅](docs/testing/T04-review.md)
- [T05规则与政策](docs/testing/T05.md) 与 [独立攻击审阅](docs/testing/T05-review.md)
- [T06实际四案演示](docs/testing/T06-demo.md)、[父节点验收](docs/testing/T06-parent-checks.md)与[独立攻击审阅](docs/testing/T06-review.md)
- [T07本机SDK实测](docs/testing/T07.md)、[父节点验收](docs/testing/T07-parent-checks.md)与[独立攻击审阅](docs/testing/T07-review.md)
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

development模式核对实际文件和许可隔离，候选仍有生产警告。release目前必须返回非零：实际采用的G06 PDF解析组件、G10开发工具和G13 MCP SDK尚未完成生产使用范围/原生依赖/浏览器许可等审批，不能靠安装成功解除门禁。来源测试绿灯只表示门禁被测行为通过。

Scrapling安装在本项目 `.venv`，Chromium在 `.local/scrapling/browsers`，后续公开网页任务可复用。静态与动态抓取仅用本地虚构HTML验证，未接入QCC或合同审查。

T01 实测全套158项通过；覆盖领域/配置/CLI/来源门，尚不代表业务闭环。事实采用七类`{kind,value}`结构保持JSON往返类型；Decimal事实必须有单位。角色按规格四种命名，后续服务从数据库核对权限。

重建开发环境需Python3.12与Windows AMD64（其他平台另行生成锁）：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --require-hashes -r requirements.lock -r requirements-build.lock
.\.venv\Scripts\python.exe -m pip install --no-build-isolation --no-deps -e .
```

当前验证editable安装；应用/测试锁已扩展为51包，build1包单独锁，wheel hash及92份应用许可见[T07依赖审计](docs/reuse/T07-dependencies.md)。生产批准仍为空，独立wheel分发和部署未验收。Scrapling可按其专用锁另外安装，不要求审材料流程加载浏览器。

T02实际全套200项通过，包含42个新权限/事务用例；独立攻击审阅已关闭事务清理与缓存状态缺陷。HTTP测试保留1条上游TestClient/httpx弃用警告。基础服务用法见T02报告；正式签发仍阻断。

T03 最终实测全套269项通过；独立69目标及14攻击探针通过。DOCX未读对象和PDF扫描/注释/隐藏文字有明确缺口；文字层提取不代表视觉等价，OCR及PDF进程解码沙箱未部署。来源发布门仍阻断。

T04 全套345项通过；独立76目标/31攻击探针通过。事实确认/主体决定按版本追加并原子回滚；从只读原件重算解析，阻断伪造已存原文/完整性标记；计算不猜付款基数，不编造企业外查结果。

T05 全套431项通过；独立86目标/45攻击探针通过。法源证据精确绑定服务端取得bytes、正文及元信息hash；适用日期、例外、负责人权限和政策版本由后端核验。14卡仍全draft、9条法源索引pending，现实法律规则批准仍BLOCKED_RULE_APPROVAL。

T06全套511项通过；独立80目标/77攻击探针通过。四份独立虚构DOCX的实际CLI各输出18维、9个JSON文件和受保护SQLite证据；审查12次、确认前候选抽取4次mock调用均保留usage/raw hash，QCC为0。未批准法律规则的维度如实不足，mock不得正式签发；没有Word/PDF制品。

```powershell
.\.venv\Scripts\python.exe -X utf8 -m cn_contract.cli demo --fixture tests/fixtures/synthetic/sales_basic.docx --provider mock --qcc off
```

其余三个实际fixture为service_basic.docx、lease_basic.docx和nda_basic.docx。输出目录为本次实际生成的`.local/review-demo`子目录，不允许通过该演示入口处理其他材料。

T07全套557项通过、零警告；独立46目标/66攻击探针/17授权回归通过。固定mcp/mcp-types2.2.0及httpx2/httpcore2 2.13.1实际向独立本机127.0.0.1模拟服务器握手、发现、调用；调用前检查完整schema/价格/服务器批准，拒绝任意端点和外部schema引用，保留安全原始证据与未知状态。没有真实QCC请求或付费。

下一任务T08：原子预算、幂等及发送后超时恢复；随后T09原生修订。法律规则、真实账户、数据政策和上线批准分别登记。T08预算、T09 Word和T10 UI的计划/候选还未执行；原生修订及视觉验证未完成。
