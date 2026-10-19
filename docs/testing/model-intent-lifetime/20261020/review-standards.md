# CH-04I 独立 Standards 审阅

结论：**无 P0–P3 产品问题；硬性标准违规 0，需修复的 smell 0。** 本报告只覆盖 Standards 轴，不替代独立 Spec 审阅。

基线：`921ba306014ccd39d535e32cfb3cd0e7e4c95834`。审查开始时 HEAD 等于基线，因此 three-dot diff 与提交列表为空；按根任务明确要求，实际审阅 `git diff 921ba30 -- <两个产品文件>` 的工作区差异。标准来源为仓库 `AGENTS.md`、`sources/specification-v2.0.md` 0.4/0.6、Ponytail full，以及 code-review 的 12 项 Fowler smell baseline；没有另行要求远端 issue 或额外委派。

## 源码判断

- `native_model_control.py:119–134`：重复审批只委托 registry 校验，意图保存 `fingerprint, token`，不保存 lease、provider、actor 或完整 policy。校验仍在认证、归属、当前配置、首次指纹、已登记 run、完整草稿范围与内容检查之后；没有新增 HTTP 入口或模型派发。
- `registry.py:106–120`：两接口与注册表的代次职责内聚，复用 `_check_loop`、`_identity` 和 `_current_config`。令牌仅由配置代次和 grant nonce 的普通 `object()` 组成，无对象出边；严格 tuple/长度/对象身份比较，不执行输入的自定义相等逻辑。
- `registry.py:69–104`：每次有效配置清 grant 并换代次；撤权再授同 policy 仍换 nonce；同一当前 grant 可幂等。新接口没有放宽这些不变量。失败配置保留当前有效状态。
- `registry.py:131–207`：在途任务原有固定 lease 和发送前校验未改。保留该 lease 时旧 provider 有意继续存活；配置变更后旧 lease 拒绝派发，释放 lease 后可回收。
- 新内部元组不是跨层业务 DTO；没有新增金额/时间表示、依赖、抽象层或例外权限。两文件的最小改动符合仓库现有风格，未发现须为风格而增加类型或包装层的理由。

## 独立实测

运行 `review-standards-command.json` 中的实际命令：**14 passed，退出码 0，2.36s**；证据为 `review-standards.log/.exit/.xml`。覆盖 12 轮引用释放、在途 lease、4 种代次变化、4 种已授权身份隔离、事件循环、畸形令牌/失败配置/配置漂移、到期不续期、空授权/停用状态。

12 个请求墓碑保留时，**12 个旧 provider、12 个密钥 resolver、12 个完整 policy 均已回收**；provider generate 调用为 0。探针禁止外部 socket/DNS；仅允许 Windows asyncio 自身的回环 self-pipe。原首轮误把 self-pipe 禁止，导致 14 个 harness 失败并伴随日志编码错误；原始证据保存在 `review-standards-harness-initial.*`。仅修正 `.local` harness，产品未改。

前后 SHA-256 相同：

| 产品文件 | SHA-256 |
|---|---|
| `src/cn_contract/assistant/native_model_control.py` | `0a6ea8b9eac612e9fe334ba7f4562d717c1b039c2e4de3a20168c29a0b21dbc4` |
| `src/cn_contract/assistant/providers/registry.py` | `a8e99983a1623359bcf28d5e4bb513bcb7ac4e913138685436f45f61768f16ad` |

范围限制：未重跑历史全套、真实模型或 Windows 冻结验收。墓碑仍按请求数增长是防重放所需的既定边界；引用回收不证明 RSS、安装体积或启动时间下降。未修改产品、作者测试、项目状态或提交。
