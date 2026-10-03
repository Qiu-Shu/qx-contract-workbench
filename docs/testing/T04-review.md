# T04 独立安全审阅

审阅者只读业务实现和正式测试，读取 AGENTS、TASK_STATUS、v2.0 §5/6/T04、ADR 0002、T04 detail plan、预检与 T01–T03 实际实现。使用 verification-before-completion 工作流，作者总结不替代独立运行结果。独立攻击探针只在被 Git 忽略的 `.audit-local/t04-review/test_attack_probes.py`；没有安装、真实合同、外查、QCC、付费、私人笔记加载、外发、业务修改或提交。

## 已实际执行

| 命令 | 退出码 | 实际数量及范围 |
| --- | ---: | --- |
| `.venv/Scripts/python.exe -X utf8 -m pytest .audit-local/t04-review/test_attack_probes.py -q --tb=short --junitxml=.audit-local/t04-review/preliminary.xml` | 0 | 首批独立 26 passed；1 条故意伪造 `model_copy` 值的 Pydantic serializer warning，4.99s |
| `.venv/Scripts/python.exe -X utf8 -m pytest tests/unit/test_facts.py tests/unit/test_calculate.py tests/unit/test_party.py -q --tb=short --junitxml=.audit-local/t04-review/final-target.xml` 初次 | 0 | 正式目标 71 passed，0 warnings，12.62s；随后作者新增上下文隔离测试，本行不是最终分母 |
| 独立探针 `-k poisoned --junitxml=.audit-local/t04-review/poisoned-parse-red.xml` | 1 | 2 failed / 26 deselected；存储解析污染的 extract / confirm 两入口未拒绝，1.04s |
| 同探针改用实际 assistant 会话，`-k poisoned --junitxml=.audit-local/t04-review/assistant-poison-red.xml` | 1 | 2 failed / 26 deselected；不依赖伪造客户端 roles，1.05s |
| 修复后独立探针 `-k completeness --junitxml=.audit-local/t04-review/completeness-red.xml` | 0 | 1 passed / 28 deselected，0.83s；文件名保留原执行名，此运行是 GREEN，不能当作 RED |
| `.venv/Scripts/python.exe -X utf8 -m pytest .audit-local/t04-review/test_attack_probes.py -q --tb=short --junitxml=.audit-local/t04-review/final-probes.xml` | 0 | 最终独立 31 passed，0 warnings，5.70s；原 quote 两攻击断言及新增 DOCX/PDF 完整性攻击均保留 |
| `.venv/Scripts/python.exe -X utf8 -m pytest tests/unit/test_facts.py tests/unit/test_calculate.py tests/unit/test_party.py -q --tb=short --junitxml=.audit-local/t04-review/final-target-stable.xml` | 0 | 最终正式目标 76 passed，0 warnings，10.73s |
| `.venv/Scripts/python.exe -X utf8 -m pytest tests/unit/test_domain.py tests/unit/test_state.py tests/unit/test_versions.py tests/security -q --tb=short --junitxml=.audit-local/t04-review/final-core-regression.xml` | 0 | 受影响领域、状态、版本、安全回归 181 passed，1 条既有 Starlette/httpx 弃用警告，12.84s |

所有命令的 UTC 开始/结束时间、实际退出码和文本输出分别保存于 `.audit-local/t04-review/*-command.json`、`*.log`，实际用例分母保存在相应 JUnit XML。不能把这些分母相加称作 84 项规格验收。

## P2 原文解析信任根污染（已实际修复与关闭）

独立构造有效 DOCX，其原文为 `Independent original payment 12.34 CNY`，通过 T03 安全摄取和实际解析取得真实 document version、anchor UUID 与位置。随后实际 assistant 会话调用既有公开授权服务 `save_parse_result` 追加相同版本、UUID 和位置，但 quote 改为 `FORGED independent payment 999 CNY`，并令 quote hash/end 自洽。原件字节始终没有变化。

初版 T04 `build_fact_candidates` 仅与最新 stored ParseResult 比较，`confirm_facts` 仅核其 anchor IDs；两者均接受伪造原文来源。真实 assistant 具有 upload/candidate_facts 权限，因此存储解析 DTO 不能单独充当原文信任根。独立两入口攻击实际失败，不是 import/语法/收集错误；向 root 与唯一作者报告后由作者修复。

最终 `storage.trusted_parse` 通过 T02 的实际授权 `read_version` / `read_original` 重取不可变原件，复用 T03 pure `_parse` 重构完整 ParseResult 并全等比较；`build` 与 `confirm` 均调用。它同时核 anchors、quote/hash/定位、parts/pages、unsupported 与 quality，不只验证被引用 UUID。不会调用 `parse_document` 写入新的解析记录来覆盖污染证据。正式 fixture 已改为真实虚构 DOCX，未保留无效原件搭配手造解析来绕过信任根。

独立最终 31 项里，原两条真实 assistant quote 污染攻击通过；新增真实 DOCX 的 thumbnail 未读缺口清空、混合 PDF 第 2 页 quality/manual/unsupported 清空攻击也通过，两个场景保留第 1 页/正文的真实 anchor 不变。这验证了完整 ParseResult 的信任根，未通过降低原断言关闭缺陷。该组 P2 已关闭。

## 其他独立攻击范围

首批 26 项实测涵盖：双律师全量快照的原顺序/hash与历史 confirmer/time 保留、旧 expected version 冲突；confirmed/rejected 不得改值；绕 build 直接 T02 保存未知/缺少文档 anchor 与未支持 receipt 后确认；伪造 model_copy 浮点决定与伪造 roles；实际 0 付款和确认期间，绑定 ratio 显式乘 100 转 percent 及错误 relabel 拒绝；0.05/0.3 与负数的真实步长舍入；未知 AST、浮点/NaN、非整数/越界/零幂与假 fact IDs、CNY/USD 混加；同代码不同名称主体保留歧义、候选内容篡改、首次直接决定与跨案 party ID 拒绝；protected reason 保留在决定表且不泄漏统一 audit、3 张新表真实 SQL UPDATE/DELETE 阻断；注入内部决定/审计写入异常，调用者捕获后继续提交仍无部分快照/状态/失效记录；同 expected version 两线程仅一次追加。

最终另验证付款 helper 返回金额与期间两原始已确认 Fact，数值 0 不等于缺失；数据库重启后服务在显式 initializer 前阻断，重复初始化后恰有 6 个新表 UPDATE/DELETE 触发器，没有导入时隐式默认数据库。首轮恶意 `model_copy` 引起的 serializer warning 在最终探针中用 `pytest.warns` 明确断言，同时仍要求值重校验失败，未将其作为业务警告隐藏。

## 最终源码与范围结论

实读最终 6 个 facts 模块、2 个窄 core 集成文件及 3 个正式测试文件共 11 个文件，其 SHA-256 保存在 `.audit-local/t04-review/final-source-hashes.json`。所有业务 DTO 仍来自唯一 domain.py，没有 schema 改动。审计只增加 `party_changed`/`party`；持久化只增加窄授权失效包装，仍复用既有 stale/superseded/awaiting_fact_confirmation 机制。181 项受影响回归通过，并未把 T02 历史 200 项分母改写成当前选取分母。

最终数学实现只遍历白名单 AST，入口重校验伪造 model_copy，使用独立 Decimal Context，不继承调用者的 precision/rounding/traps；节点 128、深度 32、输入位数/指数 128、工作精度 512、整数幂 [-100,100] 有明确限制。最终真步长舍入；中间达到有限精度有 assumptions。绑定事实核本案、所指定实际快照、确认状态、Decimal 值与单位，并保留快照 hash。纯数学输入无伪造 fact IDs，未绑定限制明确；percent 仅支持已明确的数学转换（ratio 在根式乘 100、percent 除 100），直接 relabel 拒绝，其他单位不会自动换算。

主体只有当前已存候选的显式真实律师决定能 confirmed；同名或同代码冲突不合并、不排名猜。候选 UUID 始终不当作 entity_id。技术 revision、protected 决定、hash、UTC 时间与 append-only 触发器实际有效；事实与主体写入采用保存点，同批版本/决定/统一 audit/批准失效在内部异常被捕获后仍整体回滚。

结论：最终 T04 **独立工程审阅通过**，没有未修复 P2 及以上发现。独立实跑分母是正式目标 76、独立攻击 31、受影响回归 181；根节点负责最终全套与来源/default/schema 检查，本审阅者没有将根节点运行记为自己运行。未执行的检查未标 PASS。

该结论限于当前离线服务与虚构材料。候选抽取不等于法律判断；原文真实性核对不证明抽取值和商业口径本身正确，仍须律师人工决定。复利/续约观察不提供统一法律阈值或完整风险排序；未知法域、劳动、科技专项与审查逻辑继续交后续 T05/T06 处理。外部 receipt 存储、QCC、真实模型、真实律师金标准、正式签发、试点批准、许可及数据政策、生产部署/恢复均未验收，不据此声称生产完成。Obsidian 摘要由 root 按用户新要求统一处理，本审阅未读取私人笔记或把其作为本项目事实。
