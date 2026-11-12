# Harness 合成工作流基线

开发工具，默认使用不调用真实模型的脚本适配器。真实执行现有 `dsh-agent-loop`、工具执行器、文件技能发现/加载、交付保护，以及 Python MCP 材料与案件工具。脚本模型只发出受控调用，不能用该结果宣称模型法律质量达标。

2026-11-12 候选准入复核发现：固定 Promptfoo 0.125.1 即使设置关闭遥测，仍会尝试发送一次关闭遥测事件。因此“脚本模型离线”不等于整个评测进程零外连；当前入口尚无进程级出站阻断，不应当作严格离线入口。对该要求，须先完成出站限制与失败测试，再运行完整评测。此次复核仅在内存拦截器中证明请求意图，未实际发送，也不能倒推历史运行已成功发送。见 [候选方法与评测核验](../../docs/research/2026-11-12-candidates-methods-eval.md)。

## 复现

本轮固定 Node 24、Windows x64；Python 复用现有产品的 MCP、python-docx 和解析依赖。主项目 Node 依赖须可解析，可以通过已有 `NODE_PATH` 指向经核验的程序依赖。

```powershell
# harness/evals/quality-baseline 内，仅安装隔离开发依赖
npm ci --omit=optional
# harness 根目录，配置既有 QX_TEST_PYTHON / NODE_PATH 后
npm run eval:workflow
```

Promptfoo 固定 `0.125.1`，Hono `4.13.18`，其 Windows SQLite 绑定 `@libsql/win32-x64-msvc 0.5.29`。独立锁文件固定完整依赖；安装脚本关闭，不安装无关云服务可选依赖。此开发包的原生绑定只面向 Windows x64；其他平台须选择与 libsql 版本一致的本机绑定再验证，不能把本轮结果算作跨平台验证。主 `package.json` 不依赖 Promptfoo，打包器源目录白名单不含 `evals`、`experiments`。

每次创建 `.local/quality-baseline/<新runId>/`，不复用缓存、既有结果或真实工作区。入口设置禁用遥测、更新检查及远端生成变量，不调用共享评测入口；遥测变量的已知局限见上。结果含 Promptfoo 报告、源码/输入/方法哈希清单、每案会话事件、真实工具回执、原件摘要、保存记录、DOCX 文本与字节摘要。断言重新读取实际文件，不能只靠 manifest 自述。

## 24 案的边界

- 11 个研究样例覆盖四方法、事实日/研究日/地域、旧新版本和材料自述核验状态。共同证据规范通过受限 `read_method_reference` 工具真实读取并记录 SHA-256；这个评测专用读取器仅开放该单一文件。所有法源均虚构，研究稿明确“真实法源未核验”，不将材料自述 `verified` 当成法律效力。
- 2 个串案、2 个十进制金额、2 个日期、2 个错误引用摘要。
- 重复保存保持一条记录；另一个样例通过新启动的 MCP 进程回读已存记录，验证持久化，未模拟整机断电恢复。
- 客户版导出失败而内部稿成功、模型调用中断前没有文件、原件不可读取但保留历史关联，共 3 案。

统一检查实际技能成功加载、共同规范读取、材料工具调用、持久化、DOCX 实物、原件不变和已知错误状态。金额和日期使用真实计算工具；日期只算自然日，不自动认定法定期限。坏输出测试覆盖丢文件、错 hash、空回答、串案泄露、未选方法、混合否定中的错误确定表述、夸大交付等。

中文断言只覆盖已列出的确定性反例，不能证明任意自然语言无幻觉。离线成功是流程/证据基线；律师质量、真实法源检索、长材料泛化仍标 `qualityStatus: not_reviewed`。现有 Word 批注失败、旧备份归属保护继续由统一回归测试覆盖，本组不替代这些专项。

## 真实模型入口

只在用户另行明确预算与合成评测范围后运行 `npm run eval:workflow -- --live`。同时要求 `QX_REAL_MODEL_TEST=1`、`QX_EVAL_BUDGET_CNY`（大于0.5且不超过20元）和 `DEEPSEEK_API_KEY`；正常入口生成共享 runId。直接 provider 不带共享 runId 会拒绝。完整一轮共享既有预算账本，逐请求保守预留、使用量结算；互斥锁遇并发或遗留锁时拒绝新请求，不能每案重置预算。

仅固定 `deepseek-flash` 的非思考 Chat Completions；复用项目预算费率（2026-11-12 官方中文价：输入2元/百万、输出8元/百万，忽略折扣）。调用同一 Harness/工具链；参考答案、脚本模型和隐藏断言不传给真实模型。仅有合成工作区工具，不提供网络搜索、任意读写、shell 或外部发送工具。真实请求结果与离线结果分目录，仍需人工审阅；本次未调用真实模型。

## 来源

- [Promptfoo 0.125.1](https://github.com/promptfoo/promptfoo/releases/tag/0.125.1)，固定目标提交 `8569e72ed6cf7737082a6042be8d925e40f9739d`；[MIT 许可](LICENSE.promptfoo.txt)从安装的同版本包保留。
- [Custom API provider](https://www.promptfoo.dev/docs/providers/custom-api/)、[JavaScript assertions](https://www.promptfoo.dev/docs/configuration/expected-outputs/javascript/)、[遥测设置](https://www.promptfoo.dev/docs/configuration/telemetry/)。Windows 绝对盘符在该版本断言加载器中被误当导出名分隔符，因此断言使用相对 `file://assertions.js`。
- [DeepSeek 官方价格](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)。以后运行前需核对费率，价格核对本身不构成付费授权。
