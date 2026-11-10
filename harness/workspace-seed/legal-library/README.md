# 法律 Skill 工作区库

中文优先：18 个领域/工作流入口、157 个唯一命名的完整中文技能，共 175 个可发现条目。
Harness 只把名称和简介放入技能目录，调用 `skill` 时才读取所选完整正文及其资源。

- `.dsh/skills/`：适配入口、完整技能及所需引用资源。
- `legal-library/zh/`：中文 ZIP 的原始目录结构、CLAUDE.md、references、许可证与脚本源码。
- `legal-library/en/`：英文 ZIP 原始源码，用于按需参照；不重复注册同名技能。
- `legal-library/skill-catalog.json`：唯一名称、原文件、资源路径、来源 ZIP SHA-256 的对应关系。

合同审查示例：`chinese-legal-commercial` → `legal-zh-commercial-review` → 按协议类型选择 NDA、供应商或 SaaS 审查。
每个细项技能保留原始完整正文，并明确领域 CLAUDE.md 和 references 的读取路径。
原始库安装脚本未运行；没有写入用户全局技能、画像或 MCP 配置。

适配说明：生成版本修改唯一名称、路径及与当前用户任务相容的加载说明；原始库不改写。
两个来源的许可证均保存在各自 `LICENSE` 文件中。原库中外部服务、机构模板和占位符不代表本机已经配置。
英文包独有的 CoCounsel 外部插件保留源码，不列为已连接功能。

发现依据：官方 Harness `ce7073d51254c26cd63b22a60835b8f948deb447` 的 skill-filesystem。
发现路径为最近 `.git` 祖先下的 `.dsh/skills`；无 `.git` 时用 cwd。
启动会话时应选择此 `workspace`，或者由运行配置显式指定这里的 `.dsh/skills` 为 customSkillDirs。

验证边界：目录发现及一项合同技能加载不代表 157 个法律工作流均已实际运行。
