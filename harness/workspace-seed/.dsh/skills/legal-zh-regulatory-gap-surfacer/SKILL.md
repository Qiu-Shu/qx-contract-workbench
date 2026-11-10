---
name: legal-zh-regulatory-gap-surfacer
description: "Retired workbench entry; retained only for source traceability."
disable-model-invocation: true
user-invocable: false
---

<!-- workbench-skill-repair-v2 -->
<!-- workbench-skill-disabled-v2 -->

# 已停用的专业入口

助手判读，仅核合成输入与输出的一致性及最小可用性，非人工/律师认证。旧题制度摘要覆盖边界已改善。新题明确参考2026-11-04、K1期限2026-11-01且源记录open，却仍只报“是否逾期取决于期限来源，待核”，漏掉可从题干直接给出的“按源记录期限已过，实际履行待核”状态，削弱跟踪器核心排序用途。此项是过度待核造成的功能不足，不是错误断言实际未履行，也不是工具缺失；两轮未同时达标，建议停用并用核心事项跟踪替代。

此入口不继续执行旧流程，也不通过原库绕过停用。当前业务可从 `qx-case-work` 开始完成一般合同审查或案件材料整理；这不代表该核心入口已获得本专项能力认证。专项判断仍需依据材料和已核来源由律师审查。

原始中英文库和许可保留在 `legal-library/zh/` 与 `legal-library/en/`。状态及原因见 `legal-library/workbench/skill-status.md`。
