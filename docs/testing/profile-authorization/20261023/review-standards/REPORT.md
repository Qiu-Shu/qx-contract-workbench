# CH-07C2b2b-A Standards 独立审查

基线 `60eb041536dc36dfd4133f0d09b909681146500c`。收到冻结通知后审查 registry 差异、新正式测试及相关 domain/policy/provider/准备函数；没有产品或正式测试并写。

**未发现当前切片待修的 Standards 问题。** 依据 AGENTS 的 DTO 单一归属、后端许可/费用核验和合成数据要求，以及 CONTRIBUTING 的模块复用、短事务和取消不自动重发。Fowler smells 与 ponytail/codebase-design 作为启发：本片延续已有 registry/lease 结构，未据重复的许可分流强行增加抽象。

- `registry.py:81` 许可按完整 `MainProfileSendBasis` 摘要与配置、工作区、单次上限、provider 能力绑定；保留原 policy ID 冲突墓碑与 nonce。
- `:212/232` 提交/执行检查复用现有 DTO 和纯准备函数，重新计算完整 basis 与规范字节；普通内容摘要、wire 摘要、缺少保存计划的 request 都不能替代许可。
- `:273/301` 预检和执行包裹器在当前事件循环上复核许可、配置、时限和模板。失效后丢弃候选，保留已收到 usage/request ID；无重试、DB 事务或新运行入口。普通/上下文/多轮路径明确排除 profile 许可。

## 独立实测

```powershell
.venv/Scripts/python.exe -X utf8 -m pytest .local/profile-authorization-20261023/review-standards/test_authorization_standards.py -q --tb=short --basetemp=.local/profile-authorization-20261023/review-standards/tmp --junitxml=.local/profile-authorization-20261023/review-standards/results.xml
```

一次运行 **6 passed，2.18 秒，退出码 0**：冷导入基线比较；结构自洽但非规范 wire 拒绝；在途直接替换新许可、移除档案方法这两种情况下丢弃候选但保留用量；恶意 Decimal 环境；恰好到期时拒绝。

冷导入检查启动两个独立 Python 子进程，均退出 0：基线源码执行与当前 `import registry` 各加载 14 个相同的项目模块，新增项目模块 0；两侧均未载入 profile_codec、profile_preparation、Web、desktop 或 PDF 模块。详细集合见 `cold-import.json`。这是模块加载观察，不推导整机启动、RSS 或包体收益。

10 个源码/正式测试/计划/依赖输入 SHA-256 前后不变，详见 `inputs-before.json`、`inputs-after.json`、`verification.json`。冻结 registry SHA `aad43283bf4bcfc14db4dbf588c776ea85b6eb18a0e3f3a997ffec03978e1f26`；正式测试 SHA `d165f83cf67000295962088240783bc0975726ea1e279bf46e2783ebf7d83a2e` 均匹配。原始日志为 `output.log`、JUnit 为 `results.xml`。

未重复根 13 文件回归或四门，未跑全套，未真实外发或操作实际工作库、安装版、WorkBuddy。独立探针使用内存替身，不声称完成实际 TCP 验证；正式回环用例仅审读。数据库实时授权、持久费用/次数消费、claim、固定事件原子保存与历史重放仍由后续执行链承担，本片没有激活 native/HTTP/ledger/新格式 guard。
