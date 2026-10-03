# T12 规格与现有入口映射

v2.0 T12文件栏允许“创建/按现有仓库映射修改”。本阶段增量沿既有安装包与CLI，不新增重复入口；用户要求保留可用实现、不整仓重写。

| 规格条目 | 本仓库实际实现 | 实际验证与限制 |
| --- | --- | --- |
| scripts/build_release_manifest.py / build_release_manifest | src/cn_contract/ops/release.py；现有 python -m cn_contract.cli release-manifest | 正式CLI与旧入口13目标通过；根development退出0/75阻断、production退出1。缺现实批准不创建生产清单。 |
| check_egress | src/cn_contract/ops/egress.py；既有Factory/MCP入口重核 | 后端固定虚构loopback登记才允许；真实端点、地域/OS/TLS部署仍阻断。 |
| backup_and_verify | src/cn_contract/ops/backup.py、storage.py；复用SQLite与cryptography | 根r6新目录真实服务恢复；数据库38表/9文件。只独立虚构、公开测试key，真实密钥托管未批准。 |
| 安全/运维与环境配置 | docs/SECURITY_RUNBOOK.md、OPERATIONS_RUNBOOK.md、.env.example；既有本机demo-server与.gitignore | 单实例本机虚构演示；生产HTTPS、国内host、OS限制没有部署证据，不冒称部署完成。 |

发布CLI实际复用服务，不执行证据文件中的代码；只固定服务器验证器路径可加载。普通引用仅绑定bytes，不认证实际律师批准或当前全能力。测试/开发清单与生产签发保持独立状态。入口映射是实现组织方式，未取消任何生产门禁或真实验收要求。
