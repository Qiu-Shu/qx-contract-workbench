# 已安装版本的知识库迁移

`desktop/installed-migrations.cjs` 提供 `migrateInstalledKnowledge({data, portableConfig, seedInstructions, payload, yaml})`。启动时完成初始种子复制后、启动 dsh 前调用；`portableConfig`、`seedInstructions` 必须由启动器先替换安装目录与资料目录占位符。`payload` 用于从现有 dsh 依赖加载 `js-yaml`；隔离测试可直接传入 `yaml`。JSON 配置不需要加载解析依赖。

迁移只修改 `.local/dsh-home/profiles/web/cordis.patch.yml` 和 `workspace/AGENTS.md`：仅补缺失的 `qx-knowledge-ui`、`qx-knowledge`；遇到已有同 ID（包括停用覆盖项）保留原配置；已有“本机律所知识库”章节保留原文，只在完全缺少章节时追加种子中的该章节。不会读取或修改案件、聊天、知识库原件、索引或技能文件。

所有待改原文先备份到 `.local/migrations/knowledge-v1-<随机标识>/`；临时文件写入并刷新后，通过重命名替换单个目标文件。最后写入 `.local/migrations/knowledge-v1.json` 完成标记。中断后的部分变更可安全重试；标记完成后不会把用户主动删除的插件再次加回。配置无法解析、路径被链接到其他位置或写入前发现文件已变化时停止迁移，不用默认值覆盖用户配置。普通块式 YAML 保留注释；特殊流式 YAML 可能重新排版，设置的值和类型保留，精确原文仍可在备份中找回。

注意：两个目标文件是分别原子替换，并非文件系统级整体事务；失败时启动器应停止启动并显示可重试提示，保留备份。既有技能仍由原先“不覆盖已有文件”的种子逻辑保护，迁移不强制更新律师自定义技能。

隔离检查：`node --test desktop/installed-migrations.test.cjs`，仅使用临时合成资料。覆盖旧 JSON、YAML 注释和类型、停用插件、用户指令保留、备份、损坏配置、重复执行及部分迁移恢复；不接触现有律师资料或调用模型。

## 上传隐私组件的独立迁移

另提供 `migrateInstalledPrivacy({data, payload, portableConfig})`，同样在 dsh 启动前调用，`portableConfig` 必须已经替换路径占位符并包含 `qx-upload-privacy`。测试可额外注入 `yaml`。它复用配置解析、原文备份与原子替换逻辑，只补缺失的该插件，不读取、创建或改写 `workspace/AGENTS.md`。

该迁移使用独立的 `.local/migrations/upload-privacy-v1.json` 标记与 `upload-privacy-v1-<随机标识>/` 备份目录。已有 `knowledge-v1` 标记不会阻止它执行；已有隐私组件配置（包括停用和自定义设置）原样保留；重复执行不再添加。配置解析、输入校验或文件替换失败时不记录成功，保留可重试状态和已经生成的原文备份。启动器应分别调用两个迁移，不能根据知识库迁移的返回状态跳过隐私迁移。

隔离测试另外覆盖知识库迁移已完成后的隐私升级、停用与用户设置保留、无需指令文件、重复调用、损坏配置和模拟文件锁定失败后的安全重试。
