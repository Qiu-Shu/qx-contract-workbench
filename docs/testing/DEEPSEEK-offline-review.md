# DeepSeek 离线契约独立审阅实际结果

2026-10-03，独立审阅者 deepseek_preflight。仅审用户批准的 pure 离线契约；没有实现或调用真实 transport、读取 key、登录/付费/接受协议、真实材料上传，也没有修改产品/正式 tests/Git/Vault。真实供应商、账本、法律验收、插件运行与生产仍分别阻断。

## 当前冻结版本结论

当前私有独立探针实际 **138 PASS，0 failed/errors/skipped，0警告**。无新的有效独审 P2。当前新增契约范围通过；结果仅为 `OFFLINE_ONLY / protocol_only`，供应商 API 和真实合同法律质量未验证。

|实际命令|UTC与退出码|实际结果|
|---|---|---|
|`.venv/Scripts/python.exe -X utf8 -m pytest --collect-only -q .audit-local/deepseek-review/test_codec_probe.py`|11:01:03.929702–11:01:04.938280，exit0|138 literal nodeids|
|同私有文件 `pytest -q --tb=short --junitxml=.audit-local/deepseek-review/final/results.xml`|11:01:04.938280–11:01:06.030383，exit0|138 PASS；控制台0.65秒；collection nodeid集合与native JUnit逐项相等、无重复|

实际包装器起止 UTC11:01:03.929702–11:01:06.125771。JUnit SHA-256 `eff9b4aa9248c055f97ebc8cb5b122bd4aa06bf92e3d01992f8e59966b9cbbbf`，执行日志 SHA `edec57150dc4940a65ac3dbac39783ac5c099ca22d7f9e0be0e272aef8edbb99`。私有 `final/result.json` 保存实际 argv、两个原始退出码、native testcase、literal collection和源文件前后 hash。

运行前后观察452个实际文件（src/tests/scripts/config/schemas/sources、必要项目声明及两私有脚本），差异0。该452项是此探针声明输入，不声称完整上游wheel或所有私有历史证据。作者独立 `FREEZE.json` 的四交付当前核验另存于审阅封证；本轮 source/domain与正式目标对应hash分别为：domain `c118ff19479fa4cc56aa393740234fd8f78df4a81815a8fde2048dbf535609fc`，codec `1691a927aac4c4b0676536f19e2887538278a4d9a32e29d27e823084438ef362`，正式 tests `406b7eb3d3c4017788d021dd74796245fd58723ea426b78e5564b1c9df512f55`。

## 实际独立边界

- 三固定 operation、两明确 model ID；request拒别名/空格/未知模型，response.model须精确相等；JSON mode/固定本地 JSON prompt/非stream/明确关闭thinking，未提供tools、端点、密钥或文件能力。
- 只投影 anchors.id/quote：不含完整context、内部目标/元数据、x-system/schema或批准UUID；QUOTE前后空白实际保留。32锚点及完整x-input16KiB精确边界通过，第33项/多1字节、重复及不规范UUID拒绝；忽略字段里的深度、节点数量和非有限数亦受界限控制。
- 单choice/index0/assistant/stop/非空对象JSON；截断/拒绝/工具/模型漂移/多choice/缺字段失败，外层及content重复key、非有限数、深层、过量文本失败。错误envelope不回显指定原始canary。
- token数精确非负int，排除bool/字符串/float；prompt=hit+miss、total=prompt+completion；cache细节存在时一致，reasoning存在时不超过completion；request较小cap和本地4096输入/1024输出cap不能被调用方放大。缺可选细节保存未知子计数，不补伪0；缺usage拒绝。
- 费用默认 None/unknown/USD。只有显式合成 rates 得到 Decimal `estimated_synthetic`，正好budget边界通过、下一最小差额拒绝；CNY/mock_credit等币种不会静默换算。低Decimal precision和Inexact/Rounded traps下合成计算仍精确；非有限/float/负价格及预算、毒化reply.model_copy被拒绝。它不是实际供应商费用或已批准价格。
- 实际build/decode调用在socket/DNS、getenv、Path/builtins/io读哨兵下通过；当前price另在环境get/getenv、socket/DNS与文件哨兵下通过。只观察这些函数窗口，不是完整操作系统/浏览器/进程网络抓包。原始model返回的shell/endpoint/approved/synthetic字段仅保留为数据，无执行/批准效力。
- 当前默认model=mock、QCC关闭实读一致；旧MockProvider的sent_unknown状态保留，DeepSeekOfflineReply仍被原registry/dispatch拒绝。正式签发完整流程由父回归另验，本独审不把这一registry断言称正式签发通过。

## 如实保留的历史与修复归属

私有首轮UTC10:56:05.676622–10:56:07.949620，exit1，123 PASS及2个setup/teardown ERROR。原因是审阅者把300KB文本直接作pytest参数ID，Windows的 `PYTEST_CURRENT_TEST` 超过32767字符；不是codec业务断言RED。该轮native125条包含额外teardown error，与collection124不相等，保留原logs/JUnit，不宣称它完成124项或功能失败。

仅修私有参数短ID后，同探针124参数于UTC10:56:26.768345–10:56:28.875987退出0，124 PASS/0 errors，源码零漂移；该初版只覆盖build/decode的IO钩子，没有测试price的环境读取。其JUnit SHA `67fd410608046e2ea071e6bbfde26544ae164857b85cb1f939b1add68e15561a`。最终在同探针上增加14个必要边界及价格IO核验，得当前138 PASS。

作者而非独审发现并关闭了构造DTO/Decimal/资源边界及 TypeAdapter 环境读取问题。作者正式 `06-target-green` 名称不代表通过：实际exit1、120 PASS/1 FAIL，TypeAdapter读 `PYDANTIC_DISABLE_PLUGINS`；改复用domain纯Decimal校验后同正式121目标 `07-target-green` 实际exit0。当前私有price哨兵也实测通过。该RED→GREEN证据归作者记录，不能冒称本独审曾执行该RED或供应商发生了实际隐私泄露。

完整回归及材料脚本尚由父执行，本文件不预先给其结果标PASS。第一批纯协议解析不检验群兴完整法律schema消费者、原文/法源正确性、tokenizer、模型供应商账户/地域/retention、真实费用ledger/价格审批/汇率、HTTPS/OS出站或ChatGPT插件托管连接。这些未来范围NI/BLOCKED。

证据目录为 `.audit-local/deepseek-review/{first,harness-corrected,final}`，只读封证为 `.audit-local/deepseek-review/review-freeze.json`；边界矩阵与实际封证保留私有，不覆盖任何旧阶段历史。
