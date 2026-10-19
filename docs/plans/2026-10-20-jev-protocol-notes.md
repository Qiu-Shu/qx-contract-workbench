# CH-05 Jev 协议核对与最小提供器边界

核对日期：2026-10-20（北京时间）。范围：`chat-first-architecture-v2.1.md` 第 8 节及 CH-05；公开官方协议、SDK 固定源码和 Lawve 条目；现有生产依赖与主模型传输的只读结构查询。

这是实施参考，不是联网调用回执。本次没有读取密钥、调用付费模型、上传案件材料、安装 SDK、修改产品代码或运行产品测试。原始研究资料位于 `.local/jev-provider-20261020/research/`。父任务已完成开发预检；本研究未重复争用 WorkBuddy。

## 1. 可以直接据此实施的结论

采用独立的 `assistant/providers/jev.py` 薄 HTTP 提供器与纯路由函数，复用生产锁中已有的 `httpx2==2.13.1`。不要新增整个 TypeSafe SDK。新增业务 DTO 仍按仓库规则放在 `domain.py`；HTTP、模板、解析和选择逻辑不堆入 `app.py` 或 DTO。

当前官方最新 SDK release/tag 是 **v0.7.5**，发布时间 2026-10-14，tag 与本次 main 均为 **`f36e68549ceca3191e5791e5f99ea1baa1a258b5`**。MIT，Python >=3.10；除 httpx2 外还依赖 anyio、packaging、pydantic、pydantic-core、tenacity、truststore 和 typing-extensions。仅借鉴协议和实现，不把 SDK 默认重试、环境 base URL、日志正文或滚动模型别名带入产品。[固定源码](https://github.com/typesafe-ai/typesafe-sdk-python/tree/f36e68549ceca3191e5791e5f99ea1baa1a258b5)、[正式 release](https://github.com/typesafe-ai/typesafe-sdk-python/releases/tag/v0.7.5)

模型页目前列出 `jev-1.13.0` 与 `jev-1.14.0`；`jev-latest` 仍映射 1.13.0，`jev-preview` 映射 1.14.0。按已批准规格默认固定 **`jev-1.13.0`**，不用本轮“看到更新版本”作为自动升级依据。真实部署前再核对账号可用性；本次没有请求需要凭据的模型目录。官方中文质量说明不能替代本项目中文实测。[模型目录](https://docs.typesafe.ai/models)

后续实现的首个切片将以可独立测试的提供器和路由选择为目标。本次研究只明确协议与边界，尚未实现或测试这些组件，也不宣称网页、后台队列、预算账本或凭据设置页已接入 Jev。集成前仍需每次运行的权限、输入版本和费用前置检查。

## 2. 当前 HTTP 契约

| 项目 | 核对结果 / 本项目处理 |
|---|---|
| 请求 | `POST https://api.typesafe.ai/v1/systemone`；不是 OpenAI `/chat/completions` 格式 |
| 认证 | `Authorization: Bearer <secret>`，`Content-Type: application/json`；建议 `Accept: application/json` |
| JSON 顶层 | `model`、`state`、`questions`；`questions` 为应用固定问题 ID 到问题的映射 |
| Choice | `type: "choice"`，`instructions`，`criteria` 选项映射；答案为一个 `choice`，另有 `probabilities`、`confidence` |
| Noul | `type: "noul"`，`instructions`；可加 true/false criteria；答案只有 `type` 与 `noul`，不要求 confidence |
| 响应 | `model`、`answers`、`usage`；答案 ID 对应请求问题 ID |
| 追踪 | 响应头 `x-typesafe-request-id`；缺失时保留空，绝不能把本机 ID 伪装成该值 |
| 使用量 | `usage.input_tokens` / `output_tokens`；SDK 字段允许缺失或 null；不补零 |

协议来源：[HTTP 文档](https://docs.typesafe.ai/api)、[Choice](https://docs.typesafe.ai/primitives/choice)、[Noul](https://docs.typesafe.ai/primitives/noul)、[响应类型](https://docs.typesafe.ai/sdk/python/api/types/responses)。固定源码对应 `_core/endpoints.py`、`_core/constants.py`、`_core/response_types.py`、`_core/transport.py`。

补充边界：问题 ID 本身不参与推理，完整问题必须放在 instructions；`confidence` 是由分布得到的确定性指标，不是法律判断准确率。官方请求允许 32 MiB、64 层及最多 255 个 Choice 选项；这些不是本项目放大资料外发范围的理由。[问题结构](https://docs.typesafe.ai/primitives/choice)、[确定性说明](https://docs.typesafe.ai/confidence)

### 完全合成的请求与响应样例

以下文本和计数只用于回环测试，不是实际运行结果；中文问题由项目按本地规格编写，未复制 Lawve 法律规则。

```json
{
  "model": "jev-1.13.0",
  "state": {
    "latest_request": "请帮我回复这位虚构客户，说明首次接待需要准备什么；之后还要整理附件。",
    "selected_skill": null
  },
  "questions": {
    "primary_intent": {
      "type": "choice",
      "instructions": "仅根据 latest_request 建议第一个工作流程。复合需求仍全部保留；无法确定首个流程时选择 unknown。不要判断事实真伪或授予权限。",
      "criteria": {
        "client_reply": "准备给客户的回复和追问",
        "material_organize": "整理材料与资料草稿",
        "contract_review": "准备合同审查意见",
        "content_draft": "准备公开内容草稿",
        "legal_research": "查找法条案例或核对引用",
        "unknown": "没有适合项或无法确定首个流程"
      }
    }
  }
}
```

```json
{
  "model": "jev-1.13.0",
  "answers": {
    "primary_intent": {
      "type": "choice",
      "choice": "client_reply",
      "probabilities": {
        "client_reply": 0.6,
        "material_organize": 0.35,
        "contract_review": 0.0,
        "content_draft": 0.0,
        "legal_research": 0.0,
        "unknown": 0.05
      },
      "confidence": 0.4
    }
  },
  "usage": {"input_tokens": 200, "output_tokens": 40}
}
```

Noul 独立样例同样使用上述端点：

```json
{
  "model": "jev-1.13.0",
  "state": {"public_draft": "虚构推广稿：这项服务保证每位委托人胜诉。"},
  "questions": {
    "possible_result_guarantee": {
      "type": "noul",
      "instructions": "public_draft 是否出现向读者保证案件结果的表述？只给复核提示，不作合规结论。"
    }
  }
}
```

```json
{
  "model": "jev-1.13.0",
  "answers": {"possible_result_guarantee": {"type": "noul", "noul": 0.95}},
  "usage": {"input_tokens": null}
}
```

第二个响应中的两个计数都应归一为未知，不能变成“使用 0 tokens”。`material_kind` 则是另一固定 Choice 模板，选项为 `contract/chat/transfer/judgment/mixed/unknown`；该标签不直接选择工作流。

## 3. 薄适配的执行边界

### 配置与输入

1. 提供器接收后端构造、严格复验的配置和请求；调用方先验证用户会话、材料范围、Jev 独立外发许可、预算、输入版本及任务是否仍有效。用户或模型不能传入 URL、headers、API key、任意 question template 或批准标志。
2. 默认关闭；未配置、无预算、无独立数据许可、显式技能已确定、不需要辅助、输入已失效分别返回 `skipped` 和稳定原因码。判断跳过应在解析 secret、导入 httpx2、创建客户端之前；无必要时连凭据解析器也不调用。
3. 固定线上 HTTPS 端点。只允许测试装配入口注入严格匹配的 `http://127.0.0.1:<有效端口>/v1/systemone`；标记合成 transport。不得从环境、表单、数据库模型输出或资料内容覆写 base URL。
4. 请求只含必要短文本及固定模板。主模型之后使用的完整原始诉求仍留在调用方；不能把 Jev 的短片段当作下一阶段完整输入。输入、问题模板及模型/配置版本参与本机摘要；秘密与身份映射不参与对外正文。
5. 建议此切片采用更小的项目上限，例如总请求 UTF-8 64 KiB、响应 256 KiB、深度 32、有限 JSON 节点数；这些是实现选择，须写入配置及测试，并不是 TypeSafe 官方额度。超限不截断后悄悄发出。

### 传输与全局时限

复用现有 `assistant/providers/main.py` 已验证的传输设计：延迟导入 `httpx2`；`AsyncHTTPTransport(retries=0, trust_env=False)`；客户端 `trust_env=False`、`follow_redirects=False`；TLS 正常校验；只接受 JSON、请求 `Accept-Encoding: identity`，有界读取响应。不要让 Jev import 主模型适配器来取得其私有函数；必要时再抽取无业务的 JSON/日志工具，不建立供应商互相依赖。

`judge()` 一进入即用单调时钟确定 `deadline = start + 2.0`；前置处理、密钥解析、首次依赖载入、连接池等待、DNS、TLS、发送、接收、解码、校验与结果采用均计入同一截止。网络使用 `asyncio.timeout_at(deadline)`，各阶段 HTTP timeout 不大于剩余时间。同步操作前后检查 deadline，返回采用结果前再次检查；不得在收到完整 HTTP 数据后额外获得一个新的 2 秒预算。

所有 POST 自动重试为 0，包括 429/529、连接故障、读取失败；不执行 Retry-After 中的等待。SDK 默认每阶段 timeout 10 秒、额外重试 2 次、重试预算 30 秒，不能直接沿用。[固定常量](https://github.com/typesafe-ai/typesafe-sdk-python/blob/f36e68549ceca3191e5791e5f99ea1baa1a258b5/src/typesafe_sdk/constants.py)、[重试源码](https://github.com/typesafe-ai/typesafe-sdk-python/blob/f36e68549ceca3191e5791e5f99ea1baa1a258b5/src/typesafe_sdk/_core/retry.py)

Python 取消是协作式的：单独设置 `timeout=2` 不能证明端到端 2 秒。依赖首次载入、同步 JSON 解析或退出清理若阻塞，应以实测耗时记录失败，不宣传硬实时保证。不要用无法取消的后台线程包装整个同步 HTTP，也不要吞掉外层 `CancelledError` 后继续生成。回环用慢连接/慢响应/逐块慢读分别验证总截止，不只测试服务端一次性 sleep。

### 响应校验与信息边界

- 拒绝重复 JSON 键、非对象顶层、非法 UTF-8、过深/过大结构、NaN/Infinity/溢出数及 bool 冒充数值。
- 顶层 model 必须等于运行快照中的固定版本；answers 的 ID 集合与本次问题集合完全一致；每题 type 对应模板。
- Choice 的选项和 probabilities 键集合必须与 criteria 一致。每项为有限 `[0,1]`，总和建议采用显式 `abs(sum-1) <= 1e-6`；choice 必须属于最大概率选项之一。不要归一化修复错误或自算并替换 confidence；confidence 也必须是有限 `[0,1]`。
- Noul 只验证 `type` 与有限 `[0,1]` 的 `noul`。缺 confidence 合法；不把 noul 数值解释成确定事实、权限、合规认证或自动发布批准。
- 官方响应有 usage 对象；保留缺失/null 的计数为未知，存在的值要求非负整数且不能是 bool。整个 usage 缺失可作为无效 envelope；不得以“补零”挽救。业务答案无效时，仍可独立保留已安全验证的 request ID 和使用量供原调用记账。
- 对供应商 request ID 做长度、控制字符及 secret 反射检查；无效时丢弃追踪值，不把 headers 或 body 写入普通错误信息。常规日志仅记录本机 ID、状态、时长、稳定错误码与安全用量，不记录咨询正文、提示词、原始响应或密钥。复用已有日志隐私模式时验证并发上下文隔离。

## 4. 内部结果与纯路由契约

对外部协议与内部状态分别建模。`JudgeResult` 可包含 `status`、`reason_code`、`local_request_id`、`input_hash`、配置/模板版本、实际耗时、实际模型、经过验证的 answers、安全 provider_request_id、可空 usage。网络证据至少另有未发出/发出后结果未知/已收到；它不等于结果能否采用。

纯函数保留既定签名：

```python
choose_workflow(explicit_skill, judge_result, allowed_skills) -> RouteDecision
```

`allowed_skills` 是后端已经确定的本轮候选集合，只能收窄已注册能力；不是授予访问权的工具。函数不读 DB、不调用模型、不读环境变量、不构造权限结论、不改变主供应商。RouteDecision 最少表达可空 workflow、选择来源/原因、`preserve_original_request=True`；不返回权限、数据可见范围、法律批准或新 provider。

| 情况 | 固定行为 |
|---|---|
| 显式技能已注册且位于 allowed_skills | 总是优先选择；已有 Jev 结果也不能覆写。调用方通常直接跳过 Jev |
| 显式技能不支持或不可选 | 保留原请求，返回明确不可选原因；不能静默换成 Jev 推荐 |
| 无显式技能，ok 的 primary_intent 在可选集合 | 只建议首个工作流，保留原始全部诉求及附件 |
| unknown、无 primary_intent、结果异常/跳过/超时、推荐不可选 | `workflow=None`，表示沿调用方当前已授权主流程继续；不是默认授予 client_reply 或新能力 |
| material_kind=mixed/unknown | 仅保留材料类型提示；不能用该标签删除材料、分案、强制改技能或过滤复合诉求 |
| 相同摘要但版本或作用域已变 | 调用方拒绝采用；不跨案件或新消息复用旧判断 |

规格中 `primary_intent` 没有 `mixed` 选项，`mixed` 属于 material_kind。不要为通过“mixed/unknown”测试而默默扩大主意图选项；测试应覆盖混合材料及多诉求在路由前后仍完整。该三参数纯函数并不接收原始请求，因此“保留”由不可变调用快照与后续调用验证实现，不能只放一个布尔值就声称完成。

不新设未经校准的自动批准阈值。概率可显示不确定提示，不决定案件事实、是否可以发送数据或是否允许使用工具。若主流程本身没有权限，Jev 失败不能使它变成可运行。

## 5. 费用未知、取消和晚到响应

| 证据 | 业务状态 | 费用/使用量处理 |
|---|---|---|
| 本地门禁跳过，尚未请求 | skipped | not_sent；没有调用，不伪造供应商零用量回执 |
| HTTP 已尝试，超时/断开/取消 | timed_out 或外层取消 | 保守保留 sent_unknown；不认定供应商未收到，不自动再发 |
| 非 200（包括 401/429/529） | failed | 保存安全错误码；无明确回执时费用仍未知，不自动释放预留为零 |
| 收到但 JSON/问题/模型/概率不合格 | invalid | 不采用答案；独立保留可验证的用量，否则 unknown |
| 截止前获得合格返回 | ok | 用量只是供应商报告；没有本机价目/计费依据时金额未知 |
| 已过截止才拿到完整返回 | timed_out，不能改回 ok | 若获得可信回执，只能补原 attempt 的实际证据；不能改路由或档案 |

请求 ID 不是幂等键；公开文档与此 SDK 未给出本项目可据以重发 POST 的幂等保证。不得因没有使用量或网页价格写着某项免费就计零费用。金额如需计算必须沿用 Decimal、币种、价目版本和后端预算规则，不能复用 DeepSeek 的缓存 token 字段去猜 Jev 账单。

本切片无持久化接线时，提供器只返回这些状态，由调用方后续接入 attempt 账本；不得另建一个内存字典假装完成恢复。不要另开后台轮询来追晚到响应。取消后未收到回执就保持未知；确有后续可信回执时，只允许以原本机 attempt ID、输入/配置摘要更新原调用记账字段，已确定的路由保持终态。

## 6. 复用来源与独立验证范围

GitHub：用上述官方 MIT SDK 作为 wire contract 和错误/计数语义依据，不下载执行其脚本，不引入其默认资产抓取、环境 URL 或日志配置。

Lawve：本次搜索目录后，实际使用本机 Scrapling 静态读取 [jev-question-translator](https://lawve.ai/@seth-chandler/skill/jev-question-translator)，HTTP 200。公开页列作者 Seth Chandler、Apache 2.0，并说明将复杂法律任务拆为窄问题；此处仅借鉴“一题一事”的方法。未下载技能包，未审核其全部源码，也没有把境外法律要件、提示词或页面的安全审查标记当作本项目授权。快照保存在 `lawve-page.json`；页面没有固定 commit，不能写成固定源码已批准。

应由实施者执行的最小独立测试清单（本研究未执行）：

1. 完全未配置、无预算、无独立外发许可、显式技能确定、过期输入：无 httpx2 初始化、无凭据读取、无网络。
2. 本地回环核对一次 POST 的路径、Bearer、Content-Type、固定 model 和问题集合；非 200、重定向、断开不产生第二次 POST，也不跟到其他主机。
3. 正常 Choice/Noul；Noul 无 confidence；缺计数/null；概率缺键、额外键、非法选项、非最大值、bool、NaN、错误模型、缺/多问题、重复键、响应超限均分别覆盖。
4. 显式技能优先；不支持的显式技能不被偷换；unknown、mixed、多诉求不丢原始文字/附件；不改变已选供应商与后端权限。
5. 总时限涵盖慢连接、慢 headers、逐块读取和处理阶段；取消不重试；超过截止的答案不能被采用。记录冷启动与已载入依赖的实际耗时。
6. 合成秘密/咨询标记不出现在结果错误、异常字符串与普通 transport 日志；usage 未知与真实零、收到但不采用、发出未知能区分。

测试通过后的准确表述应为“Jev 提供器/路由的离线与本地回环通过”。真实供应商连通、真实中文效果、权限与预算持久化接线、前端可用、安装版兼容仍按实际阶段分别记录。
