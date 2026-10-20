# WIN-PATH-01 独立 Spec 审阅

基线 `7446a9ce47d9452568f7d2ea1cf53c92167d53f4`；commit list 为空。范围：`git diff` 中 persistence.py 的I/O适配、新增两个长路径测试文件与 `docs/plans/2026-10-20-contract-long-path.md`。按本片合同原件/qxbak范围审阅，不将实际UNC、超长SQLite URL或旧cnbak任意长目标列为遗漏。

**必须修复：0 项；无发现。**

- “在文件 I/O 使用扩展路径，在逻辑引用…保留普通路径”：`Database.__init__` 保持普通storage_root；create/read/cleanup只在I/O转换。相对 `matter/version/original.bin`、SQL URL及DTO没有新前缀字段，未改schema或哈希内容。
- “事务清理…已有原件不覆盖”：目录独占创建仍在取得原件清理所有权之前，原件open仍为 `xb`。原有事务登记、nested释放向parent移交、回滚和close清理机制没有改写；两端路径统一转换后仍先检查root包含关系，未改为递归清理。
- “保留 SHA、权限和引用；…恢复只读”：新集成测试走真实本机合同DOCX上传、qxbak、恢复HTTP、再备份，并核对旧cookie撤销及写请求阻断；备份/恢复的fence和授权代码未改。本审查未重复该集成批次。
- 授权仍先于版本读和文件访问。`read_original` 新增的OSError捕获覆盖resolve错误，只返回既有通用冲突码，没有暴露路径或把损坏视为成功。

独立必要探针 **4 passed / 4.23秒 / exit0**：撤权后的原件read/create均在filesystem helper与流读取之前拒绝（2）；预先存在的UUID目录及marker不被失败创建清理（1）；nested成功释放后outer提交失败只清理两份新长路径文件、保留旧原件/配额/审计（1）。临时目录全新D盘 `.local/lps-af79d4ab`，输入SHA前后相同。

证据：`spec-path-probes.py`、`spec-path-probes.log/xml`、`spec-path-probes.json`（完整命令、退出码、7项源码/测试/规格/探针输入SHA）。没有修改产品或测试，没有运行广套、真实材料、供应商、网络或WorkBuddy。结论限于已声明范围，不表示新安装包或未验证平台能力已完成。
