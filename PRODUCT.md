# 群兴法律工作台
<!-- impeccable:product-schema 1 -->

## Platform
web

现有本机网页工作台；最终交付目标为统一 Windows 应用，桌面封装尚待实测。

## Users
宋萌律师及约10人以内受邀用户。中文长文阅读、办案资料核对和法律资料检索是主要使用场景。

## Product Purpose
复用已有合同、持衡及家事资源，让咨询接待、案件办理、合同审查和资料回查连续进行。本轮优先把本机案例和法规变为可检索、可回查的资料库。

## Capabilities and Constraints
现有 FastAPI、Jinja 与静态页面及登录、权限、同源控制继续保留。原件、版本和审核状态必须可追溯，检索命中不代表法律结论正确或法规仍有效。先本地建设，阿里云统一接口部署另行实施；不增加收费订阅。

## Brand Commitments
用户于2026-10-30明确指定采用同伴 `dhb_law` 前端：保留合入的温情工作台、工作台/对话双视图及共用输入、材料和底稿节点。后续功能沿用该界面，不恢复已搁置的本机旧样式。Impeccable 主导操作可用性，Taste 辅助视觉；保持中文可读、键盘操作、克制强调色及原文核对区域。合并与实测见 docs/testing/frontend-integration/20261030/README.md。

## Evidence on Hand
已确认设计见 docs/superpowers/specs/2026-10-14-local-legal-library-design.md；实测盘点见 docs/testing/LOCAL-LIBRARY-PREFLIGHT-20261014.md。来源完整性、法律效力和正式交付是不同验收状态。

## Accessibility & Inclusion
键盘可操作、正文可调字号、窄窗口可用，状态以文字说明，不能仅靠颜色区分。
