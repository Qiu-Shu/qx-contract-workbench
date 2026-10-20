# CH-06B2b1 Standards 独立审查

固定点 0d53fdfdae806c6fec90c01cab1531a7cb666831；commit list 为空，审查该点至工作树 diff 及新增源文件/测试。输入 SHA256 记录于 standards-inputs.json（10 文件）。

## 结论

硬规则违反 0；需修正的 smell 建议 0。AGENTS.md、CONTRIBUTING.md 优先；Fowler baseline 按启发式逐项核对，不为套用抽象而改动已有框架。

- domain.py:3420 起统一增加 Selection/Source/Manifest/Preview DTO；原 V1 类型未改。片段身份、位置、摘要、重复选择、JSON 字节及 sending_enabled=false 由后端核验。
- providers/context_preview.py:22–57 为纯投影及完整预览；复用 domain、canonical_json 与既有引用校验。新 wire 模板独立，未改旧 build_request。没有网络、秘密解析、账本写入、许可或运行分派。
- assistant/context_preview.py:11–31 从已保存草稿及服务器引用重建，复用当前权限/版本/附件与恢复栅栏；完整限定相同对话、工作区、案件及 binding，不凭客户端正文建立依据。
- web/assistant_context.py:16–37 保持薄路由；body 前后复核登录、同源和 CSRF，再委托服务。registry.py:76–79 只取当前验证后的配置，未调用 resolve/grant 或更改旧授权。无新 DDL、依赖或运行队列。
- 同构的旧/新 wire 字段遵循独立版本要求；本片无需为减少少量重复而改写旧协议。其他分层及命名与项目约定一致。

## 独立核验

4 项定向合成测试通过，4.05s，exit 0：旧 V1 固定 wire 字节、双层 JSON 转义下保留完整超预算预览、配置读取不改变 grant、恢复副本阻断新预览且保留历史引用读取。命令及输入摘要见 standards-inputs.json；原始输出 standards-checks.log/xml/exit。临时目录全部位于 D 盘。

未运行全套、真实资料/模型、桌面冻结或安装器；本结论仅对应记录的源文件摘要，不把主代理回归或后续未审变更计作本次独立验证。

## 冻结后文件名更正

全套收集发现 unit/integration 中测试文件同名；集成文件已从 `tests/integration/test_assistant_context_preview.py` 改名为 `tests/integration/test_assistant_context_preview_service.py`。独立核对原审查摘要与现文件均为 `639b4a44e03a6f05b6977fbc8a9e6c919876aa5910b77c21601351719e2cfe28`，旧路径不存在；原审查全部 10 项文件内容仍相同，只有该路径变化。映射见 standards-rename-map.json；不重跑定向测试，原审查结论保持。

此前收集失败应保留为失败记录。后续旧合同 Windows 长路径 WinError 206 诊断及短 D 根关联回归不属于本次 Standards 独立运行，也不构成旧长路径问题已修复的证明。本报告不宣称全套通过。
