# CH-06B2b2a 独立 Spec 复核

结论：**无必须修复项（0发现）**。基线 `aa77af6903fd324bc3fd7cc4f5fb5b78a99a3aa9`；审查工作区diff及新增文件，未产生提交。规格为 `docs/plans/2026-10-21-context-provider.md`。

核对 `domain.py` 新MainContext类型、context_codec/context、deepseek_protocol/deepseek_transport及main。规格要求的完整来源摘要、批准前范围与确定后继、精确预览字节、默认拒绝adapter、共享传输和严格候选均已对应实现；未发现越范围接通应用发送。旧V1类型未扩宽，来源校验不以quote摘要代替完整CitationRef身份。

独立合成探针 **6 passed，exit0，pytest 0.60秒**：

- 冻结基线所有既有domain类AST不变；旧main实际代码与新main的V1 wire及5种候选/错误解码结果逐字一致。
- 改变不在外发投影中的registered_source_sha256（同步重算citation身份）仍被原完整摘要拒绝；同quote来源跨scope拒绝。
- 伪造嵌套审核状态及内部citation身份不能通过重新序列化验证。
- 第二条已选引用可返回；交换第一条的quote hash被拒，received usage和供应商回执保留。
- 默认无预检以及读取密钥后预检抛错均拒绝；客户端导入陷阱证明未进入HTTP，私有异常内容不泄漏。

命令、退出码、全新D盘basetemp及8输入前后SHA保存在 `spec-context-probes.json`，输入稳定；独立脚本/日志/XML同目录。未修改产品或既有测试，未使用数据库、真实材料、网络或模型账户。

明确非本片缺陷：prepare负责投影自洽，完整保存记录由validate_sources和可信预检核验；basis构造不等于许可。schema、原生授权、来源关系、同attempt执行和归档恢复按规格属于下一片；不能用当前6项通过宣称应用资料发送已开放。未重跑已有61项或整套回归。
