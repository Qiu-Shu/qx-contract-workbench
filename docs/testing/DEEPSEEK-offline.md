# DeepSeek 首批离线契约验证

2026-10-03；workspace：`D:\Documents\ChatGPT\律所项目`。本批仅实现请求数据构造、人工响应解析及显式合成 USD 估算。状态为 `OFFLINE_ONLY`，不证明供应商连通、模型效果、实际费用、律师验收、真实试点或生产完成。独立审阅与父节点完整回归另行登记，不用历史 T13 的 815 项结果替代本批测试。

## 实现范围

业务 DTO 仅新增于 `src/cn_contract/domain.py`：`DeepSeekOfflineUsage`、`DeepSeekOfflineReply`、`DeepSeekSyntheticRates`。纯函数位于 `src/cn_contract/review/deepseek_codec.py`：

- `build_chat_request(request, *, model, max_tokens)` 返回请求字典。固定候选 ID 为 `deepseek-flash`、`deepseek-v4-pro`，仅三项已有 operation；模型 ID 是公开文档快照，不宣称固定权重。明确 `stream=false`、`response_format=json_object`、`thinking.type=disabled`，本地固定提示明确要求 JSON。
- `decode_chat_response(raw, request, *, model, max_tokens)` 返回 `DeepSeekOfflineReply`，恒为 `OFFLINE_ONLY`、`protocol_only`。只解析人工提供的原始 JSON，不发送请求。即使 payload 声称 GO、PASS 或批准，仍只是未执行数据，不能进入已有模型注册门。
- `price_offline_reply(reply, rates, *, max_cost, unit)` 只产生 `estimated_synthetic` 估算，不生成 `ModelResponse` 或实际账单。显式合成价和预算必须同为 USD，不读取公开峰谷价、账户价、余额、汇率或账单。

输入只投影 `x-input.anchors` 的规范 UUID 和原文 quote；完整 `ReviewContext`、规则、身份、存储路径、预算批准、schema、`x-system`、repair、端点和模型元数据不会进入消息。合同注入内容保留为 user 数据，不能替换 system 提示。完整 x-input 限制 UTF-8 16 KiB、深度16、节点2048、1–32个不同锚点；空文本或非法形状拒绝。请求 max_tokens 必须精确整数并排除 bool，限1–1024并服从更小请求输出 cap；报告输入 token 上限为4096并服从更小请求 cap。字节上限用于资源约束，不能充当供应商真实 token 计量。

外层及 content 均复用既有 `strict_json`，拒绝重复键、非有限数字、数组根、深层或超量原始文本。外层身份、字段白名单、唯一 index0 choice、assistant、非空 content、stop finish、精确 model 都须通过；工具、函数、refusal、非空 reasoning、未知字段和不完整结果拒绝。五项 usage 必须精确非负整数，满足 prompt=cache-hit+cache-miss、total=prompt+completion；可选 cached 必须等于 cache-hit，reasoning 不超过 completion，并检查本次 token cap。缺 usage、缺必需计数、null details 或不一致不会补0。

未经计价的 usage 为 `cost=None`、`unit=USD`、`pricing_status=unknown`。合成价仅接受精确 str/int/Decimal，排除 float/bool，限制文本80字符、有效数位30、指数−18到6及数值0到1000000。估算按 cache-hit、cache-miss、completion 各自每百万 token 单价相加，使用独立120位 Decimal Context；调用者的精度和 traps 不改变结果。费用超显式 USD 预算即拒绝；测试显式全零合成价仍标估算，不把未知费用默认成0。Malformed Decimal 和绕过 DTO 验证构造的错误请求形状均以 ValueError 拒绝。

旧 `ModelProvider`、MockProvider、workflow、registry、defaults、CLI、web、QCC、出站与签发代码没有修改。未新增 HTTP 客户端、SDK、transport、provider 注册、密钥配置、网络调用或外部项目。现有真实调用所需批准、账户、数据政策和持久模型费用账本继续缺失；本批不解除这些阻断。

## 作者实际测试

每轮通过本项目 `.venv/Scripts/python.exe -X utf8 .audit-local/deepseek-author/run_tests.py <phase> <targets...>` 执行；记录位于各轮 `actual-evidence.json`、`results.xml`、`safe-output.log`。记录包含展开后的完整 actual argv、UTC 开始/结束、退出码、JUnit 实际计数以及四个交付文件运行前后 SHA。所有输入为独立虚构材料，没有读取真实合同或密钥。证据目录不覆盖。

|轮次|目标与实际结果|归因|
|---|---|---|
|01-core-red|8 failed，0 errors；exit1|八项 test function 内的功能缺失断言；不是 import/collection/fixture error|
|02-core-green|8 passed；exit0，零警告|最小纯 codec 实现|
|03-boundary-red|106 passed、5 failed、2 errors；exit1|一项数字 UUID.upper() 测例失误；大文本默认参数 ID 导致 Windows pytest 环境变量超过32767，产生 setup/teardown errors。这些不计有效功能 RED；原日志保留|
|04-boundary-valid-red|108 passed、4 failed、0 errors；exit1|修正短参数 ID/字母 UUID 后，实际复现 malformed Decimal 异常和三种绕过 DTO 的错误 shape；这些才计补强功能 RED|
|05-boundary-green|112 passed；exit0，零警告|有限 Decimal 输入、错误形状和输入资源约束闭合|
|06-target-green|120 passed、1 failed、0 errors；exit1|名称虽为 green，实际没有通过：强化哨兵抓到每次 TypeAdapter 构造会读取 PYDANTIC_DISABLE_PLUGINS；不是网络或密钥读取，不能据名字标 PASS|
|07-target-green|121 passed；exit0，零警告|复用 domain 纯 Decimal 校验，消除该定价路径环境读取|
|08-associated-green|308 passed；exit0，零警告，24.54秒|本批121项加原模型 JSON、domain、defaults、review flow；全部关联目标通过|

最终关联命令为 `.venv/Scripts/python.exe -X utf8 -m pytest -q --tb=short --junitxml=.audit-local/deepseek-author/08-associated-green/results.xml tests/unit/test_deepseek_codec.py tests/unit/test_model_schema.py tests/unit/test_domain.py tests/unit/test_defaults.py tests/integration/test_review_flow.py`，退出0，308项通过。实际 argv 的绝对路径以该轮 JSON 为准。

正式测试包含两模型/三 operation、仅必要文本投影、所有计数字段类型与总量、响应身份及字段限制、严格原始 JSON、边界资源、Decimal 超预算/币种/恶意 context、未知成本与显式合成0、DTO 篡改和注册门。哨兵覆盖 codec 重载及三函数的环境读取、网络连接、进程启动、本地资料读取；失败和成功路径均受哨兵保护。实际未执行 payload 指令，不把 JSON 模式通过冒作群兴法律 schema、原文锚点或批准通过。

作者自审检查新增 Python 文件 AST 可解析、各文件单个末尾换行、旧 domain EOF 保留。source/tests/doc 冻结 SHA 和实际证据清单见私有 `.audit-local/deepseek-author/FREEZE.json`；完整回归、原84项能力门和独立审阅由父节点记录，本文不预填结果。
