# Standards 轴复核

硬违规：本次未发现。DTO 集中定义；权限、版本、来源由后端核验；档案、接待、回执同事务保存；备份沿用既有校验链。仅改标题继承摘要来源，改写咨询正文会中断继承。

建议（非阻断）：来源规则在 profile_store:99、intake/service:35、profile_integrity:116 三处维护，当前一致；后续成组覆盖回归，无需立即抽象。

范围：基线 2b72c9a02a25607761705811550323fa9fcfce00，检查 working diff 及新增文件：domain、profile_store、assistant_profiles、intake/service、profile_integrity、ops/backup。六文件读前后 SHA256 一致。排除自写 schema/迁移；未跑测试，不代表运行或生产验收。
