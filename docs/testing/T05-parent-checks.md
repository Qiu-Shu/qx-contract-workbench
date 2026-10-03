# T05 父节点最终核验

记录日期：2026-10-03，Asia/Shanghai。保留T00–T04实现；唯一domain/schema/defaults/CLI/正式依赖不变。只有独立虚构材料、离线SQLite；真实模型/QCC调用0，没有费用、真实上传或推送。

| 实际命令 | 退出码 | 实际结果 |
| --- | ---: | --- |
| `.venv/Scripts/python.exe -X utf8 -m pytest -q --tb=short --junitxml=docs/testing/T05-results.xml` | 0 | 431 passed；345既有+86 T05；1条既有Starlette/httpx弃用警告，46.16秒 |
| `.venv/Scripts/python.exe -X utf8 scripts/verify_defaults.py --file config/defaults.json` | 0 | 规范hash为0e4acba46c67b731cd9662d7b118217ddc55047ab69315961c7f78dfcfa9c887 |
| `.venv/Scripts/python.exe -X utf8 -m cn_contract.cli schema --check` | 0 | 当前唯一ReviewRun schema与保存版一致 |
| `.venv/Scripts/python.exe -m pip check` | 0 | No broken requirements found |
| `.venv/Scripts/python.exe -X utf8 scripts/verify_sources.py --mode development` | 0 | 13来源，errors=[]；13条NOT_PRODUCTION_APPROVED警告 |
| `.venv/Scripts/python.exe -X utf8 scripts/verify_sources.py --mode release` | 1 | G06/G10 DEPENDENCY_REVIEW_PENDING与PRODUCTION_APPROVAL_MISSING，真实预期阻断 |
| Python独立重算 `.audit-local/t05-implementation-hashes.json` 的所有文件 | 0 | 17/17 SHA256匹配冻结实现/测试/数据/作者报告 |
| `git diff --check` | 0 | 跟踪变更无空白错误；暂存后另查新文件 |
| `git diff --cached --check` 初次 | 1 | 新T05-review.md末尾多1空行；仅文档尾空白修正，不改业务/测试 |
| `git diff --cached --check` 修正并重暂存后 | 0 | 29份T05及明确规划文件无空白错误；T07候选/T06审阅预读未暂存 |

独立86目标/45探针/124核心回归、三组P2及构造错误边界见T05-review.md；作者86目标/152受影响回归、初50RED和版本重叠RED见T05.md。分母分开记录，84规格编号不是84测试PASS。父节点全套仅在作者冻结/独立最终复验后运行。

来源证据只收精确bytes并绑定server UUID，不能让provenance_ref成为任意本机读取入口；所有basis引用都核验，重复适用版本要求复核。政策内容hash与policy_runtime_sha256绑定的批准依赖分开；T06选择context完整，模型context仅applied。默认14draft和9pending，不是法律批准。原件/审计保留，服务无hidden DB/commit。

T07/T08/T09新增规划明确PLANNING_ONLY；依赖候选/Word注册存在不算SDK、预算、报告或视觉PASS。已授权本机Obsidian摘要在阶段提交后另存成功并读回才报告；没有memory_record工具，不冒称结构化API成功。T06实际四类离线闭环、法律金标准、真实外查/费用/地域许可、正式签发与生产门继续独立登记。

父节点更新阶段文档时第一次apply_patch因总体计划行不匹配退出错误，未落盘；读回确认后按实际行修正。该辅助编辑错误不算业务功能RED。
