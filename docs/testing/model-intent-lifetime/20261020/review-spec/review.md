# CH-04I 独立 Spec 复核

基线：`921ba30`。审阅对象：当前未提交的 `native_model_control.py` 与 `providers/registry.py`。依据：`docs/plans/2026-10-20-model-intent-lifetime.md`、v2.1 已批准的权限/费用/来源和恢复边界、仓库 AGENTS。复核者未编写或修改产品与作者测试。

## 结论

**未发现本批阻断性 Spec 偏差。** 新增接口仅返回当前配置代次及当前 grant 的两个裸对象标识，不含 provider、密钥 resolver、actor 或 policy。旧请求记录保留身份指纹与代次；不会因撤权、重配置或同一 policy 重挂而恢复授权。

`authorization_token` 并非新的发送权限接口：它保留原 `snapshot_for` 在此调用点所做的工作区/用户/会话及有效期验证。完整会话、草稿版本、正文摘要仍由 `authorize` 前序核验，实际发送仍经 lease 的 `check_submission`、`check_execution` 与持久化费用账本。两个新增方法均进入原事件循环检查。

已登记 run 的分支仍位于新代次验证之前，保持原持久化身份/内容核验和 `existing` 语义；它不创建新 grant。此结论没有将原有“已停用/配置版本不匹配仍拒绝原生授权入口”说成新增支持。

## 独立合成实测

命令（`PYTHONPATH=src;.`）：

```text
.venv/Scripts/python.exe -m pytest .local/model-intent-lifetime-20261020/review-spec/probe_spec.py -q --junitxml=.local/model-intent-lifetime-20261020/review-spec/results.xml
```

退出码 **0**，**14 passed in 6.88s**。只复用既有合成工作区/用户夹具，没有调用作者的 12 项测试函数。

| 独立场景 | 实测结果 |
| --- | --- |
| 真正的 DeepSeekProvider 类，24 次合成配置/授权/停用；generate 被禁止调用 | 每轮 provider、resolver 和 resolver 捕获的配置 DTO 均可回收；24 个请求墓碑仅保留指纹和裸代次；DB 无模型任务 |
| 同一个 provider 对象、同一个 policy、同样配置重新挂载 | 配置及 grant 均产生新代次；旧原生意图不能复活 |
| 畸形代次 7 类及另一个 registry 的同 policy 代次 | 8 项全部拒绝；正确标识仍有效且同请求幂等 |
| 到期前 1 微秒及恰好到期 | 前者可复用、后者拒绝；没有替换或续期 policy |
| 两个新增方法在无运行循环及后续不同循环中调用 | 均拒绝 |
| 成功回执后更新草稿并撤权，再用原请求读 existing | 原回执/待核输出保留；仍各 1 任务/回执/输出，未新增授权或发送 |
| 在途合成调用停用后取消 | 执行期间保留 lease；结束后 provider/resolver/lease 均释放；保存 1 费用未知回执，无输出 |

产品 SHA256（实测后冻结文件核对）：

- `src/cn_contract/assistant/native_model_control.py`: `0a6ea8b9eac612e9fe334ba7f4562d717c1b039c2e4de3a20168c29a0b21dbc4`
- `src/cn_contract/assistant/providers/registry.py`: `a8e99983a1623359bcf28d5e4bb513bcb7ac4e913138685436f45f61768f16ad`

## 边界

保留请求墓碑意味着记录数仍随本次后台生命周期内请求数增长，这是明确的防重放设计，本批不是清空全部历史内存。弱引用与 GC 证明引用可释放，不证明字符串安全擦除、RSS、安装包体或启动时间下降。

此审阅未调用真实模型、读取真实凭据、联网或操作安装版；Windows 原生管道/冻结构建和关联回归由主代理独立记录。原始命令输出、逐项 XML 及结构化结果位于本目录 `probe.log`、`results.xml`、`report.json`。
