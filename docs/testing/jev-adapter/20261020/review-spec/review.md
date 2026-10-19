# CH-05A 独立 Spec 复核

基线 `7dd5abb`；依据本片实施计划、2026-10-20 官方协议核对笔记、v2.1 §8 以及 AGENTS。对象为未提交的 5 个产品文件：domain.py、routing.py、jev.py、jev_codec.py，以及既有 main.py 的 wraps/import 两行兼容修改。复核者未实现或改写产品、未修改作者测试、未提交代码。

## 最终结论

**本片无未关闭的阻断发现。独立 36 项探针全部通过，exit 0，1.02s；5 个产品文件在测试前后 SHA256 一致。**

本结论限定为薄提供器、内部 DTO、固定问题编解码与纯路由。源码检索没有在 Web 路由、原生设置、主应用或队列中找到 JevProvider/choose_workflow 接线；默认配置关闭，未设置可信 preflight 时返回 no_egress。不能把当前合成回环通过称为真实供应商连通、中文法律质量验收、首页可用或持久预算/外发权限已经接通。

## 发现及关闭

1. **P2：内部结果语义不完整。** 初稿允许 primary_intent 缺固定概率选项，或超过 2 秒仍为 ok，路由复验后会采用。现在 JudgeResult 按固定题目验证类型、选项与 ok 的绝对耗时；model_copy 旁路也被路由重验挡住。原始 `contract-red.log/xml` 为 12 failed / 2 passed（同时涵盖下一项），修改后原样探针 14 passed。
2. **P2：RouteDecision 三字段相互矛盾。** 初稿可表示有新工作流却声称 current/no_suggestion。现在只允许明确选择/建议配非空工作流，或者 current 配空工作流与对应保留原因。原样复验通过。
3. **P2：未核验响应媒体类型。** 初稿对 text/plain、text/html、缺 Content-Type 的 JSON 正文均给 ok。独立本机回环 `transport-red.log/xml` 为 3 failed / 4 passed。现在这些响应均 invalid，application/json; charset=utf-8 正常；只有安全追踪信息可保留，不采用答案。
4. **P2：主/辅日志安装交替导致无界包装。** 初稿主/辅各自只识别最外层标记；本轮直接调用 602 轮后安全普通日志发生 RecursionError。当前两者用 wraps 保留已有标记，两个顺序均稳定，602 轮及主/辅/普通异步上下文隔离通过。最早的独立 pytest 运行发生于 Jev 单侧 wraps 修复已落地、Main 尚未修复时，`logging-red.log/xml` 中 1 failed / 3 passed 是“首次安装就完全稳定”的过严断言；该部分不是残余递归缺陷。探针随后允许两轮初始化，再验证长期稳定；原始日志保留，未冒称原样 RED→GREEN。原先无界增长的直接复现命令与实测输出见下文。

另外明确了 `JudgeResult.model` 的证据含义：未发送/发送未知不能把请求配置模型写成“供应商实际模型”；收到错误模型时也不自动补期望模型。已新增两个独立探针，现均通过。这是证据语义澄清，不重复计为上述四项之一。

## 独立探针

命令：`.venv/Scripts/python.exe .local/jev-adapter-20261020/review-spec/run_final.py`；其实际 pytest 参数、环境、逐项名称及前后摘要保存在 `report.json`。仅使用独立虚构内容和随机本机端口，真实凭据与外部模型调用均为零。

| 文件 | 数量 | 覆盖 |
| --- | ---: | --- |
| probe_contract.py | 14 | 固定问题语义、超时结果不采用、伪造 DTO 重验、决定一致性、显式优先及允许技能边界 |
| probe_codec.py | 9 | 本机身份不进 wire 但参与摘要、无效答案与安全回执分离、合成秘密反射、Noul 数值与未知 usage、追踪 ID 控制字符 |
| probe_transport.py | 9 | 独立回环媒体类型、最小 wire、429 不采用/不重试、同步解码超过总截止、取消、默认无许可、错误模型不冒充 |
| probe_logging.py | 4 | 双顺序日志安装长期稳定、602 次交替无递归、主/辅/普通异步上下文隔离 |

36 是本轮独立用例数，不与作者用例或历史回归相加重复宣传。`final.log`、`final.xml` 记录最终结果；初次失败及中间复验均保留。

## 最终产品 SHA256

| 文件 | SHA256 |
| --- | --- |
| src/cn_contract/domain.py | 9d16e632bd0f50149b6843cf4781669e9f7032e0dc55fae59a22752f5bc28516 |
| src/cn_contract/assistant/routing.py | b6529e27d501fc129851c9c304fa2143e066010eebc7596482c27cfff0fd1cee |
| src/cn_contract/assistant/providers/main.py | cd15eec8824219294b484fa46289f7a30ed0fefec4aa03eaf54557a6b2869598 |
| src/cn_contract/assistant/providers/jev.py | 06f913b805fca0d4bc5df636a485dca39b02761cb0a9edc9b8e18ed7edec8dd2 |
| src/cn_contract/assistant/providers/jev_codec.py | bc69e1145e09de8d3a53fd24c8cf0093a0120198d330041ea5e216b38deb1e69 |

## 原始日志链问题的直接复现记录

在安装 wraps 补丁前，独立 Python 进程运行如下逻辑；finally 恢复日志工厂，没有修改产品：

```python
original = logging.getLogRecordFactory()
try:
    main._protect_logs(); jev._protect_logs()
    first = logging.getLogRecordFactory()
    main._protect_logs(); jev._protect_logs()
    print('factory_identity_stable_after_second_pair:', logging.getLogRecordFactory() is first)
    for _ in range(600):
        main._protect_logs(); jev._protect_logs()
    try:
        logging.makeLogRecord({'name':'synthetic.review', 'msg':'synthetic-safe-log'})
        print('record_created: true')
    except RecursionError:
        print('record_created: false; RecursionError after 602 alternating pairs')
finally:
    logging.setLogRecordFactory(original)
```

当次工具原始输出为：

```text
factory_identity_stable_after_second_pair: False
record_created: false; RecursionError after 602 alternating pairs
```

这是本会话实际观察摘录，命令捕获异常后 exit 0；不是当前版本仍失败，也不是 pytest 的初始 XML。最终 602 轮探针验证当前产品不会再触发该错误。

## 后续接线前提

三参数路由没有当前作用域/配置参数，不能单凭 DTO 验证证明来源仍有效；下一片调用方须保存完整原诉求、核验当前作用域/输入/配置、独立 Jev 外发权限与预算，持久 claim 后才可令 preflight 放行。结果建议不批准法律事实、档案归并或对外发送。

同步 Python 工作仍可能实际阻塞超过时限；本片证明过期结果不被采用，不宣传硬实时调度。未知 usage 不等于零费用；取消后由未来持久账本保留发送未知。本审阅未重跑整仓库、未验证真实 TypeSafe/安装版或独立冻结构建；这些由主代理按实际范围另记。
