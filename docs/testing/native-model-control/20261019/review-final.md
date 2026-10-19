# CH-04F 独立最终审查

日期：2026-10-19。工作目录：`D:\Documents\ChatGPT\律所项目`。审查者：`generation_ui_state`。仅写本目录 `review-*` 文件；未改产品、正式测试、公共记录或提交。

## 结论

当前审查范围没有尚未解决的阻断项。独立探针最终 **Python 11 PASS，Node→Python 真实父子管道 2 PASS**；原报告后根代理发现的维护退出问题已经修复，本审查者追加实际进程目标复验 **2 PASS**（见文末补充）。本轮独立发现的两个具体问题已有产品修复，并使用同一独立反例复验通过。初始 RED 记录保留，未计入通过数量。

这里的 Node 交叉测试使用生产 `Backend`、`ModelControl`、Python `ParentControlChannel` 与引导解析/输出函数，但处理器是独立、无模型调用的测试处理器。Python 授权测试使用临时合成数据库和合成 provider。本报告不把这些称为真实密钥、真实供应商或日常发送 UI 已接通；根代理的 Electron/回环与冻结 EXE 验收是另组证据，未由本审查者重复运行。

## 已关闭的发现

1. **文本 readline 的字符限额不等于 UTF-8 字节限额。** 原实现读入约 36 KB 中文 JSON 且无末尾换行时，超过 32768 字节仍等待换行或 EOF。独立真实 `os.pipe()` 初测 `1 failed / 5 passed`，exit 1，见 `review-pipe-initial.log` / `.xml` / `.exit`。产品修复从 boot 起共用二进制 stdin buffer，避免 TextIOWrapper 预读丢帧，控制读取在字节边界返回并拒绝；探针随正式二进制接口改用 binary pipe，最终通过。它不是无限分配漏洞，但原行为不满足约定字节限制。
2. **能力展示未核对单次批准 basis。** 批准 A 的文本后，B 保存相同文本，或 A 重新保存相同文本使 composer revision 前进，能力仍返回 ready，提交则正确拒绝，0 attempt。独立初测 `2 failed / 3 passed`，exit 1，见 `review-basis-initial.log` / `.xml` / `.exit`。产品增加只读 `check_draft` 并在 capability 与 submission 使用；两反例现在均返回 unapproved。没有发现越权发送。

Windows stdout CRLF 问题由根代理独立发现并修复为 LF；本报告的真实管道测试也确认收到的控制 ack 无 CR，不能把该发现归功于本审查。

## 独立实际验证

在工作目录执行，均不联网、不安装依赖、不调用真实模型：

```powershell
$env:PYTHONDONTWRITEBYTECODE = '1'
.\.venv\Scripts\python.exe -m pytest .local/native-model-control-20261019/review-pipe-probes.py .local/native-model-control-20261019/review-basis-probes.py -q -p no:cacheprovider --junitxml=.local/native-model-control-20261019/review-python-final.xml
node --test .local/native-model-control-20261019/review-node-cross.test.cjs
```

- Python：**11 passed in 3.13s，exit 0**。原始结果 `review-python-final.log` / `.xml` / `.exit`。
- Node：**2 passed，0 failed，1415.1613 ms，exit 0**。原始结果 `review-node-final.log` / `.exit`。

独立断言覆盖：超限 UTF-8 无换行拒绝；非法/秘密字段不进 ack；EOF 在绑定 loop 执行 disable 且后续 dispatch 失败；嵌套重复键、深度、非有限数、安全整数；跨对话及 composer 失效能力；发送期间配置轮换或撤权仍保留已发送费用回执而不发布旧候选；撤销一个会话不影响另一会话；真实 Node/Python 单在途、固定 ack、正常 EOF exit 0；处理器企图返回秘密字段时实际子进程终止且父端不可复用，无秘密输出。

复用正式测试的合成数据库/provider fixture 是测试准备；上述攻击及断言单独编写。没有重复全套回归。

## 静态接线审查

- boot 与 control 使用同一无缓冲 binary FileIO。正常控制处理仅由读取线程转交绑定 app loop；等待一个结果后再读下一条。固定 schema、nonce、序号、byte/depth 限额及 ack 白名单均有落实。失败的生产 fatal 是进程 exit 2；测试替身仅用于观察投影结果。
- ready 在应用 lifespan 完成后发布；初始 registry 为空，没有从磁盘、环境或 renderer 自动装载/授权密钥。维护进程仍走原 EOF 关闭分支。
- NativeModelControl 重新认证 session、当前 owner/案件与恢复态、scope/composer/hash、材料；配置 version、首次意图 fingerprint、原 lease/expiry 共同阻止配置 ABA、预算或期限重放扩张。已持久请求路径返回 existing，不新建 grant/attempt。
- enqueue 核对原 basis；claim/settle 核对持久 request_id 与发送后 scope。GenerationTasks 仍一次解析 runtime；运行中 provider 固定，最终 receipt 与候选发布分开，未加入第二队列。
- Node 适配器 busy 不消费序号，故障/超时终止自有 child，不重试命令。stdout 按字节有界，strict UTF-8 + canonical JSON +字段投影；stderr 丢弃。`withSecret` 沿既有 store 串行通道消费，只返状态，回调结果不外泄。原窗口的 main/preload/setup 未加入配置/授权 IPC，没有 HTTP 授权或 secret 入口。

## 非阻断后续项及边界

`NativeModelControl._intents` 保存 `(fingerprint, policy, lease)`；lease 持有固定 provider，后者的闭包持有旧 secret，所以 disable/reconfigure 后旧 intent 仍可能保留旧密钥引用到进程退出。本片不承诺 immutable string 的可靠擦除，且旧 lease 已被版本/nonce 撤销，未发现新增外泄或恢复执行路径，因此不作为本片阻断。

可在后续以 **fingerprint + 失效 tombstone** 替换失效 intent 的 lease 引用，使旧 provider 只由实际在途 attempt 保留到结算；不能直接清空 intents，否则会破坏原 request_id 的首次批准参数和撤权后不复活约束。大量授权/长期开机时再定义记录数量与生命周期，无需本片扩范围。

本审查不证明 Python/JS 能可靠擦除进程内字符串，不覆盖同用户恶意进程可任意篡改内存/文件的系统级威胁；现有 Windows 路径检查的完整性边界未因只读 callback 扩大。日常设置与发送确认 UI 消费这套接口仍属后续工作。

## 源码摘要

追加维护修复审查结束时 16 个相关产品输入的完整 SHA-256 在 `review-source-sha256.json`（新增 package.json 摘要）。原 15 项摘要保留为 `review-source-sha256.pre-maintenance.json`；对原集合检查仅 desktop_entry.py 发生变化，见 `review-maintenance-source-delta.json`。关键输入：

| 文件 | SHA-256 |
| --- | --- |
| `src/cn_contract/desktop_control.py` | `e225bf47e9ba112ed9dfc98f9641d39058b752d7cf9b82b135010f93dbc81f0d` |
| `src/cn_contract/desktop_entry.py` | `1d43b703b68d6fa7d7a040c17f8f7fc6a2a31f0dee089cb730dda65ef8e5a68c` |
| `src/cn_contract/assistant/native_model_control.py` | `8cb466d76972716d635ac44f41479e8e945fcfdfeabec571ab330acc659d0f8f` |
| `src/cn_contract/assistant/providers/registry.py` | `3664986943d7d295258f2921162de2b44bd089b04a82af1ea723c8971d339f51` |
| `src/cn_contract/web/assistant_generation.py` | `802af1e6d90e77d590118d7a9033e39bd8e11cf585ec1edf2d3b488945c4d802` |
| `desktop/model-control.cjs` | `56186e5d0ba3361cf4173309f46ff752918b0563303fb5a0936f019b1cfa4747` |
| `desktop/backend.cjs` | `3d7c513293fc1b2347c57ec63c0354f1f79572892a7fd13f98bc2e8403c5af8e` |
| `desktop/model-credentials.cjs` | `9f2b90999432fa1670ae4a3de6c17afee7d405c20a78e7334e6032e150ba4914` |

## 追加审查：维护完成后退出（原报告之后发现，已闭合）

根代理在实际 Maintenance→冻结 EXE 的 backup/restore 追加验收发现：子进程发出 complete 后，当父端保持 stdin 打开，daemon watcher 仍在 BufferedReader 上阻塞，解释器退出出现 `_enter_buffered_busy`，exit `3221225477`。正式 source 反例 `maintenance-red.log/xml` 记录 **1 failed**。这是原报告覆盖未包含的实际生命周期问题，不能用此前 PASS 将它抹去。

最终修改仅将 desktop_entry 的统一输入流改为 `os.fdopen(sys.stdin.fileno(), 'rb', buffering=0, closefd=False)`，boot 与 watcher 均使用这一 FileIO。它消除了 Python 缓冲读取器退出锁，不恢复文本预读；`readline(MAX_BYTES+1)` 仍按字节限制，closefd=False 不夺取系统 stdin 描述符所有权。配置、授权、队列和 provider 接线未改变。

本审查者读过该修改与根代理的 RED 证据，并仅追加运行相关真实进程用例：

```powershell
$env:PYTHONDONTWRITEBYTECODE = '1'
.\.venv\Scripts\python.exe -m pytest tests/integration/test_native_control_process.py -q -p no:cacheprovider --junitxml=.local/native-model-control-20261019/review-maintenance-final.xml
```

结果：**2 passed in 5.98s，exit 0**，见 `review-maintenance-final.log/xml/exit`。包含普通实际后端 LF ack、同管道控制、超过 32 KB 且无换行时 exit 2；以及实际 backup + restore 均在父 stdin 仍打开时发 complete、exit 0、stderr 为空，恢复副本仍 quarantined。未重跑无关已绿探针，未调用模型或重做冻结构建。原 15 项产品摘要中仅 desktop_entry 变化，追加核对后当前 16 项摘要稳定。
