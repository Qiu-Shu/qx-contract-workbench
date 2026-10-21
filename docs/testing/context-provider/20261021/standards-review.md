# CH-06B2b2a Standards 独立复核

基线：`aa77af6903fd324bc3fd7cc4f5fb5b78a99a3aa9`；范围为当前未提交的 DTO、codec、共享 DeepSeek 传输及三个新测试文件。依据根 `AGENTS.md`、`CONTRIBUTING.md`、本片计划及 ponytail/code-review；先用 CodeGraph 定位，再核对当前差异。输入逐文件 SHA-256 见 `standards-evidence.json`（12 项）。

**结论：未发现本片引入的硬性标准违规或需要修改的 Fowler smell。**

- `domain.py:3514–3606` 集中定义业务 DTO，旧文件前缀逐字符不变；沿用金额/usage 类型，没有扩宽 V1 请求或输出契约，符合 AGENTS 的唯一 DTO 与旧行为保护要求。
- `context_codec.py:17–62` 复用既有预览和来源投影，完整引用摘要、顺序、绑定范围与确定后继版本分别核验；没有数据库、当前权限或第二个任务队列。`context.py:1–15` 明确 basis 不是授权且默认拒绝，符合 CONTRIBUTING 的后端权限核验约定；可信组装回调仍须由后续接线实现，不能把本片当作已完成许可。
- `main.py:23–53` 保留原 V1 builder 和兼容导出；静态 AST 核对 `_SYSTEM`、`build_request` 未变。`deepseek_transport.py:66–125` 复用一条有界 HTTP 路径，密钥读取前后严格预检、延迟导入、取消继续抛出、无重试；协议解析保留合法 usage，未知费用不伪作零。共享基类和两个窄 adapter 解决当前两种 codec 的实际复用，不构成需要删除的推测性抽象。

独立执行：`standards-command.json` 所列 pytest 命令 **6 passed / 0.96s / exit 0**；含新上下文取消及日志上下文恢复、默认拒绝零密钥/HTTP导入、完整来源身份、撤销预检、截断响应 unknown。新增独立探针仅存本目录；复用四个定向测试，无既有测试改写。

静态脚本 `.venv/Scripts/python.exe -X utf8 .local/context-provider-20261021/standards-capture.py` **exit 0**：V1 AST、旧 domain 前缀、registry/policy/runner/model_integrity 均未变化。命令、日志、XML、退出码与摘要留存本目录。

未跑整套、未联网模型或接触真实资料；应用接线、一次许可、schema、历史/备份兼容及安装版尚不在本片完成声明内。以上结论只覆盖所记录输入摘要。
