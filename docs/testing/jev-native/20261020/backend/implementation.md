# CH-05C Python 原生 Jev 配置生命周期

基线 `29564821ce02210426261b9d562e624d93cdf094`。本分工产品与测试已冻结，待父任务独立复核及整体验收；未提交、构建或推送。

## 实现与接口

- `domain.NativeJudgeConfigure` 仅含固定 `JevConfig` 与 16–512 位无空白可打印 ASCII secret（repr=False）；拒绝额外端点、模型、超界截止、隐式布尔转换和无效密钥。
- `NativeJudgeControl(runtime, provider_factory=None)` 的同步 `configure(payload)` / `disable()` 绑定现有 JudgeRuntime 的应用事件循环。配置成功只返回 configured/config_sha256/新 UUID config_version；每次成功重配清旧 policy，失败保留旧身份。停用返回 disabled，释放当前 provider；不创建授权、HTTP 客户端或额外队列。
- `desktop_control.NativeControlHandler(main, judge)` 固定连接 Main 原四操作及 `configure_judge`/`disable_judge`，同用 `qx-model-control-v1` 的 nonce、sequence、长度和安全 ACK 白名单。内部 `disable_all` 不接受管道调用；单独停用互不影响，关闭/EOF/坏帧/不可信 ACK/意外处理异常清两者；Main 清理失败仍尝试 Judge 清理。旧 Main-only trusted handler 保留固定 disable fallback。
- `desktop_entry` 只装配空 JudgeRuntime，不接 web runtime；ready 新增 `judge_control_protocol:'qx-judge-control-v1'`。配置不代表已连接、费用验证或已同意发送。

## 实际验证

最终命令与完整 stdout/退出码/JUnit 在 `backend-final.json/.log/.exit/.xml`：**119 passed，exit 0，52.60s**；其中新增 33 项包含在总数，不能重复相加。7 个分工输入运行前后哈希一致；报告生成时再次核对一致。`git diff --check` exit 0。

| 测试文件 | 实际数量 |
|---|---:|
| `tests.unit.test_native_judge_control` | 19 |
| `tests.unit.test_desktop_control_protocol` | 29 |
| `tests.integration.test_desktop_runtime` | 8 |
| `tests.integration.test_native_control_process` | 2 |
| `tests.integration.test_native_model_control` | 49 |
| `tests.integration.test_native_model_lifetime` | 12 |

服务覆盖新版本/无授权、坏输入保留原配置与权限、同 key/换 key 重配清权、旧 provider 可回收、关闭幂等、无 loop/错 loop/错线程拒绝、factory 错误固定化、DTO 隐秘字段不回显、冷路径不加载 httpx2。协议覆盖固定新增操作、单服务隔离、两者清理、拒绝新 grant 操作/公开 disable_all/新 frame protocol、非空 disable 无副作用、EOF/坏帧/坏 ACK/异常清理。真实子进程覆盖 ready、同 pipe 配置/停用/重配、认证重启/正常 EOF；原 Main 配置授权与意图生命周期全部纳入目标回归。

先失败证据均保留：service-red 1 failed、protocol-red 2 failed、lifecycle-red 5 failed、entry-red 1 failed（均 exit 1，无收集错误）。`protocol-green-initial` 的 5 failed/17 passed 是合成 Main handler 漏原 authorize/revoke 方法，已仅修夹具；后续 protocol-green 22 passed、protocol-boundaries 29 passed，最终组合仍通过。旧中间记录未覆盖。

## 冻结摘要

| 文件 | SHA-256 |
|---|---|
| `src/cn_contract/domain.py` | `66ba71ea2845d459cba03964b226e36a5946fbe5195783b4d0f62660dd00a795` |
| `src/cn_contract/desktop_control.py` | `35e998f0e6891c54fd073c7cd054687ebfafdf041bb223ef2e58745090023728` |
| `src/cn_contract/desktop_entry.py` | `805d4c02cf23c515c2323d9f1b049e85e552a22a191c42c7e361e86692e2df15` |
| `src/cn_contract/assistant/native_judge_control.py` | `8e9522aaedcae537d84809c1014c635e90b961541ab695677226e619b4a006fb` |
| `tests/unit/test_native_judge_control.py` | `99c1d3c3d3fd43fd114399e9fec2d56a3fc1f653a118279238977a14c63e91d7` |
| `tests/unit/test_desktop_control_protocol.py` | `e15fbca1b6c744a4b7de4c8af94df47954136eadb15af6f91575464c926b96fb` |
| `tests/integration/test_desktop_runtime.py` | `7ab5875b7dd52d0571545a672329b43bd10405567597d0f02e0e6a28e5d884aa` |

仅使用合成资料；未读取真实密钥或调用远程供应商。本代理未做进程全网抓包、Windows UI 或冻结二进制验收；未改 Node、schema、状态文档或安装。授权、发送、主流程前置留给后续切片；Python 字符串释放不等于安全擦除。
