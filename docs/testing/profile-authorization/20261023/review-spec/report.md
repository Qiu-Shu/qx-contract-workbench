# C2b2b-A 独立 Spec 复核

基线：`60eb041536dc36dfd4133f0d09b909681146500c`。规格：`docs/plans/2026-10-23-profile-authorization.md`。

**结论：0 项发现。未发现本片要求遗漏、额外行为或误实现。** 本结论限于内部许可切片，不等于完整自动归档或费用执行链已完成。

实际审查 `git diff 60eb041536dc36dfd4133f0d09b909681146500c -- src/cn_contract/assistant/providers/registry.py tests/integration/test_assistant_profile_authorization.py`，并直接读取尚未跟踪的新测试文件全文；没有把 Git 不显示新文件误当作不存在。

## 规格闭合情况

- 合同第1项：grant 绑定完整 basis 摘要作为唯一允许键，同时检查 workspace/config、max_calls=1及 callable generate_profile；同policy ID的历史冲突机制保留。正文或wire摘要均不能替代用途与保存计划。
- 第2项：提交与执行检查复用真实输入DTO及纯 basis 构造，执行接收完整 prepared 和 request_id；DTO重验把 wire 与basis绑定，当前配置/模板重建basis再校验，拒绝自洽但已替换的wire。数据库现时权限和版本明确仍归C2b2a调用方。
- 第3项：profile独立预检重复snapshot、require_policy和完整prepared核验；provider wrapper返回后独立检查，撤权、配置改变、换许可、到期时移除候选，保留received使用量和供应商标识，无新增重试。
- 第4项：普通、context、rounds与profile许可双向隔离；旧lease的nonce/配置版本/loop失效规则继续复用。未增加DTO、schema、队列或原生/HTTP入口；原完整性封闭guard保持。

## 实际验证与冻结输入

预先编写的独立探针**14 passed，0 failed，exit 0，0.73s**。覆盖有效单次合成委托、相同wire的四种保存计划变化、正文/wire摘要误用、自洽伪造模板wire、四种迟到失效的费用保留、缺完整保存计划的原始请求，以及入口/guard静态不变。合成provider故意不执行preflight，验证wrapper自身的最后一道检查。

```text
.venv/Scripts/python.exe -X utf8 -m pytest .local/profile-authorization-20261023/review-spec/test_independent_spec.py -q --tb=short --basetemp=.local/profile-authorization-20261023/review-spec/probe-temp --junitxml=.local/profile-authorization-20261023/review-spec/results.xml
```

| 冻结文件 | SHA-256 |
|---|---|
| registry.py | aad43283bf4bcfc14db4dbf588c776ea85b6eb18a0e3f3a997ffec03978e1f26 |
| test_assistant_profile_authorization.py | d165f83cf67000295962088240783bc0975726ea1e279bf46e2783ebf7d83a2e |

**17项输入前后摘要全部一致**，含产品、规格、相关边界和独立探针本身。证据：`inputs-before.json`、`input-stability.json`、`results.xml`、`output.log`、`exit-code.txt`。

本独审未执行作者测试、根13文件回归、四门或真实HTTP；作者测试中的回环HTTP仅做静态检查，其运行结果由统筹记录。只使用合成内存DTO/provider，未改产品/作者测试，未触及真实数据、密钥或活动桌面，未提交。持久次数消费、费用预留、claim、固定事件原子保存与历史/恢复闭合仍待后续整体接线，max_calls=1不是供应商收费上限。
