# 家事技能上游来源补查

2026-11-01，通过已连接 GitHub 只读检索 `divorce-practice-stephane-boghossian`，未运行检索到的 Skill，未复制到运行 prompt/rules/Skill 目录。

找到名称、作者和许可标识相符的公开候选来源：

- 仓库：`lawve-ai/awesome-legal-skills`。
- 固定读取提交：`f9f28cdccbeb98bbdde010042ea9f525ca427c72`。
- [Skill 入口](https://github.com/lawve-ai/awesome-legal-skills/blob/f9f28cdccbeb98bbdde010042ea9f525ca427c72/skills/divorce-practice-stephane-boghossian/SKILL.md)，Git blob SHA `7974663cfa17de44f71656b03799eff171a65b42`。本次读取前 70 行；元数据标注 `Stephane Boghossian`、`agpl-3.0`，Skill 版本 `0.1.0`、元数据版本 `2026-06-29`。
- [仓库 README](https://github.com/lawve-ai/awesome-legal-skills/blob/f9f28cdccbeb98bbdde010042ea9f525ca427c72/README.md)，Git blob SHA `8a7be20ef087330d1e4ad8ed7be54f7aeb208b89`。其许可段区分清单自身与被收录作品：清单标为 CC BY-NC-ND 4.0，各资源适用其作者自己的条款。因此不能用仓库根许可证替代具体 Skill 的许可声明。
- [根 LICENSE](https://github.com/lawve-ai/awesome-legal-skills/blob/f9f28cdccbeb98bbdde010042ea9f525ca427c72/LICENSE)，Git blob SHA `c741d9203a142f267b0ada2b03a74a64a38a4293`；本次读取前 22 行，标题为 Attribution-NonCommercial-NoDerivatives 4.0 International。
- 同一提交的 `skills/divorce-practice-stephane-boghossian/LICENSE` 返回 404。这个结果仅证明该精确路径不存在，不证明仓库所有位置均无许可原文。

检索还返回 `CSlawyer1985/legal-skillhub` 中同名中文入口；本轮没有据此认定本机三份知识文件的完整来源链，也没有将镜像视为作者的额外授权。

更新后的缺口：已找到可固定读取的公开候选入口，不再笼统称“找不到上游仓库”；但本机 0.2.0 派生内容与此入口的逐文件对应、完整许可材料、改编与分发方案及使用批准记录仍待核对。本轮是工程来源盘点，未作商业使用的法律结论。项目 AGENTS 的未批准 AGPL 来源阻断继续有效。

本机家事工作树及 `THIRD_PARTY_NOTICES.md` 保持原样。核对完成前不更换其来源声明，不改变工作台运行能力状态。

## 用户随后确认

2026-11-01，本轮用户明确提供 `https://github.com/Qiu-Shu/songmeng-family-law-skill`，说明本机有更新版本、项目由其研发，并授予全部权限。该确认解除本轮家事项目本地接入的授权阻断：以已经盘点并保护的本机 0.2.0 工作树为准继续实施，不用远端 0.1.1 覆盖，不重复要求同项许可。

继续保留现有原作者/来源/许可说明；该操作授权不改写上游声明，也不等于本轮已完成商业分发法律审查、发布或真实客户材料测试。前述缺项作为来源追溯待核记录，不再据此停止已授权的本地适配工作。
