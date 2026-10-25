# D2g5e 新 HTTP 测试修正独审

同一名未编写本片产品、也未编写这些新增 HTTP 测试的独立审阅者 `/root/next_slice_review`。只静态比较测试修正与原有安全实现，并核对已经产生的 XML/JSON/log；**本次复核未重跑任何产品测试**。

结论：peer 顺序修正与 root ACL 审计 oracle 修正均保留正确安全断言。独审发现审计测试引入局部 `payload` 遮蔽，原第三轮确为测试错误；父代理随后仅改 4 行局部变量引用为 `audit_payload`，现静态闭合，产品无需修改。**1 个确认测试问题已修正，0 个未解决产品/测试问题**。最终完整组是否通过由实际回执决定，不能拿3项精准通过替代64项。

## 逐次差异与实际失败

| 输入 / 轮次 | SHA256 / 实际结果 | 独审判断 |
|---|---|---|
| `http-test-before-peer-fixture.py` | `0b4f53f5422f4cc52c680c8f45cafa838495ea39991b70c2b63a5d7106b664d7` | peer 修正前快照 |
| `http-test-before-audit-oracle.py` | `d8e09461b24d37ad531fde82373098522783994b152307e34bc77a30285a6d78` | peer 修正后、审计 oracle 修正前 |
| `http-test-before-shadow-fix.py` | `0337d1cbbc0a8d0c811e855c5b70c1be6f60e2b8ea56520350a4d931185effe7` | 审计 oracle 已补但局部变量遮蔽 |
| 当前 `tests/integration/test_weixin_generation_dispatch_routes.py` | `7b15fd34d8530f4282c320372d9116f9de1d817d42682b1f4e78205735dda05f` | 4 行变量引用修正后 |
| `final-services` | exit1；61PASS/3FAIL；before/after仅新HTTP测试漂移 | 不可作为稳定最终验收。初轮还有三ACL夹具修正期间漂移；原XML中的`ownership`旧名称与后续`acl`名称须按实际记录，不能掩盖。 |
| `final-services-fixed` | exit1；63PASS/1FAIL；输入稳定 | root ACL 拒绝返回403正确，但测试误要求 audit_events 也零写。 |
| `final-services-verified` | exit1；61PASS/3FAIL；输入稳定 | 独审实证三种 position 均在调用代际 helper 前触发 `UnboundLocalError: payload`，尚未执行新增审计断言。 |
| `audit-oracle-check` | exit0；3PASS/43deselected；输入稳定 | 本轮修正后实际精准回执；不是全64，不累计重复。 |
| `final-services-complete` | exit0；64PASS；输入稳定；新测试SHA为当前7b15fd34 | 独立读取实际回执核算，无测试重跑。 |

## Peer fixture 修正

AST/diff 表明从第一快照到第二快照仅修改 `setup` 与 `test_cid_cannot_choose_another_peer_or_account_descriptor` 两个函数。新增可选参数使同账号第二 peer 在该账号第一条 generation 之前创建，符合既有 `bind_synthetic_peer` 的 active/account generation 暂停守卫；没有放松产品。独立账号仍使用自己的新账号、peer、generation 和真实代际收件。两种情况都继续以真实持久 descriptor 调用 HTTP，保留 POST403、GET403 及完整状态不变，未改成仅测试夹具创建失败。

## Root ACL oracle 修正

从第二快照到第三快照仅增加标准库 hashlib/json import，并修改一个 ACL 测试函数。`security.py:111–126` 明确先 rollback 被拒业务，再独立提交 denial audit；`audit.py:22–29` 只保存 reason_sha256。因此不能要求 root HTTP 外层 `authorize` 拒绝后整个 audit_events 表零写。

新断言保持：所有表集合一致；除 audit_events 外每一表行均逐字节相同；旧审计行完整 prefix 不变，只增加恰好一条；新增 payload 的 reason_sha256 必须为固定 CROSS_MATTER_DENIED 摘要，原 reason 不存在；仅在核实摘要后重构该固定 reason 进行严格 `AuditEvent` 验证。action、真实 actor、响应 correlation_id、before/after hash均None、entity/matter一致、存储4字段头、实际投影目标 matter 均核验。固定 target 拒绝及 later target 不相关两分支仍要求所有状态完全不变。不是简单忽略 audit 表，也未放宽错误码、正则或权限要求。

## 独审发现的测试遮蔽及修复

第三快照在该函数前部仍调用模块 helper `payload(...)`，后部却赋值 `payload = json.loads(...)`。Python 会把整个函数中的 payload 判定为局部名，故三种 position 都未进入目标 ACL 测试半段。该错误与产品和审计语义无关，已直接反馈父代理，不修改产品。

第三快照到当前最终测试的 diff 恰好4行：赋值目标及对应 pop、reason absence、模型验证引用改为 audit_payload。前部 helper 调用保留，全部断言原样。AST核对可将后部这4个 Name 置换还原，与原预期审计逻辑一致；当前函数局部赋值集合不再含 payload。新增3项精准回执已实际到达并通过审计/固定目标/后代目标三个分支。

## 旧关联组无需因该新模块重复运行

六个旧关联组为 schema163、integrity169、history129、dispatch75、HTTP87、backup14，共 **637** 不同用例，各 exit0、before=after。所有组四产品SHA都与原独审冻结点一致。XML模块列表均不包含新 `test_weixin_generation_dispatch_routes`，各 argv 显式选择旧模块；对整个 src/tests 文本检索没有发现其他文件引用这个新模块名，未找到导入它的旧 helper/test。修正限于新模块，旧模块/共享 helper未改；故这些已完成旧组不需要因新测试修正重跑。

这不是“所有完整测试树在跨组都同一哈希”的声明：旧637的输入摘要包括当时未执行的新HTTP文件旧哈希；当前该文件确实变化。证据应明确唯一未使用输入差异，并以最终完整64在当前哈希实跑补齐，而不是把旧组摘要改写为当前哈希。

四产品始终保持：domain `f8f64176edbc9866887ade894680492769ae46b8ddd4bc3c6bc107632b89fe2e`；conversation `025fe5960dcfb967fdcf871d3589f068e10094717b6ac54ea09a11f538ca1c14`；generation_dispatch `a1f22dc3c7813f9a28a050acb46f3880ad9316ad3b98e83bb260e04a8f9df361`；HTTP `0f5b0756a1f3ba85d2776e681db3ef0da3d2e66088b4ee034623c99358a4d45f`。完整机器范围、差异、回执和文件摘要见 `test-correction-review.json`。

本次只静态复核、没有再次执行 pytest/Git/浏览器/真实能力，也未改 src/tests/docs/配置/依赖/产品库/记忆。现已独立读取最终完整64的实际XML/JSON：64PASS、exit0、全部输入before=after、当前7b15fd34测试SHA，四产品不变。结合六旧组，7组23模块恰701不同ID，无重复；新增64，另5独立探针及3精准repeat不累计。此处为实际回执核算，没有重跑测试；公开证据发布声明和规范化字节仍待下一次单独只读核查。
