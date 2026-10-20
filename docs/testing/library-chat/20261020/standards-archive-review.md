# CH-06B2a Standards — archive 补审

此前 standards-review.md 的 0 项发现仅表示当时审查未识别问题，不能证明归档完整性。其后 Spec 独立复现 P2：腐坏 research.accepted 仍可备份恢复，随后历史读取失败；该发现成立。本补审检查修复后的 4 文件，不覆盖未变产品。

## 最终结论

修复后新增 Standards 待修项 0。依据 AGENTS.md 的后端核验、原件/审计保留及 CONTRIBUTING.md 的复用、短事务和恢复规则：

- research_records.py:9–42 共用纯 initial_call，仅依赖 domain、library_records 和标准库；无权限服务、数据库、文件、网络或 archive 循环依赖。复用 domain DTO 与规范 JSON，不复制一套业务模型。
- research.py:31–44 将运行读取交给纯校验；:112–116 的可选分类仅对无新工作流标记的旧记录返回 None。合法旧 B1 查询词含 local-research-v1 不再被字符串命中误分类；带新标记但错身份/顺序/载荷仍抛错，不回退为旧记录。
- library_integrity.py:107–111 对所有相关运行复核同一初始身份，completed 必须有回执；:155–159 捕获 marker-only、改名和旧 schema 内混入的新事件。校验历史关系而不要求旧会话活跃或当前法库在线。未变 DDL、schema 版本、授权或导入链路。
- test_assistant_research_backup.py 覆盖认证归档创建/恢复拒绝、marker 损坏、旧 B1 兼容、旧会话撤销与较新草稿；没有把真实资料加入测试。

## 实际核验

服务冻结 4 文件 SHA256 与磁盘全部一致，详见 standards-archive-inputs.json。关键纯校验摘要 f8623c52c57605f59bb08c42fb722c1dfb37104a4410b79f964aac8bd76d7fad。

独立定向运行分两批：腐坏 accepted 创建/恢复拒绝及旧 B1 兼容，2 passed / 4.06s / exit 0；最终冻结后合法旧查询词与 marker-only 拒绝，2 passed / 1.95s / exit 0。见 standards-archive-checks.log/xml、standards-archive-final-checks.log/xml。不同批次，不表述为一次 4 项运行。

未重新运行全套、真实数据/模型或安装器；不以服务代理回归代替本审查独立证据。
