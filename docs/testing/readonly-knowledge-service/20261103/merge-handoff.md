# 最新主线合并预览与维护者交接

2026-11-03 使用 Git 原生三方合并预览，结果为存在冲突。此记录用于请维护者完成主线整合并复验，不把试点分支的测试结果视为组合结果。

- 目标分支：`codex/contract-review-v2`，预览基点 `15acd84546616f8c44dc394e04bf7753cad72739`。
- 已测试的试点代码提交：`92fd47fd9d3dbcd78516333a864043d955ed9bf2`；后续交接文档提交不改变该产品代码。
- 命令：`git merge-tree --write-tree --name-only 15acd84546616f8c44dc394e04bf7753cad72739 92fd47fd9d3dbcd78516333a864043d955ed9bf2`。
- 实际退出码：`1`，共28个冲突文件。

## 冲突文件

- `README.md`
- `docs/TASK_STATUS.md`
- `sources/runtime-dependencies.lock.json`
- `src/cn_contract/assistant/attachment_integrity.py`
- `src/cn_contract/assistant/evidence_records.py`
- `src/cn_contract/assistant/followup_records.py`
- `src/cn_contract/assistant/judge_integrity.py`
- `src/cn_contract/assistant/library_integrity.py`
- `src/cn_contract/assistant/model_integrity.py`
- `src/cn_contract/assistant/profile_integrity.py`
- `src/cn_contract/storage_bootstrap.py`
- `src/cn_contract/storage_schema.py`
- `src/cn_contract/task_drafts/integrity.py`
- `src/cn_contract/web/app.py`
- `src/cn_contract/weixin_inbox/dispatch_integrity.py`
- `src/cn_contract/weixin_inbox/generation_dispatch.py`
- `src/cn_contract/weixin_inbox/generation_ingress.py`
- `src/cn_contract/weixin_inbox/generation_integrity.py`
- `src/cn_contract/weixin_inbox/generations.py`
- `src/cn_contract/weixin_inbox/grant_integrity.py`
- `src/cn_contract/weixin_inbox/integrity.py`
- `src/cn_contract/weixin_inbox/personal.py`
- `src/cn_contract/weixin_inbox/provenance_integrity.py`
- `tests/integration/test_assistant_library_schema.py`
- `tests/integration/test_followup_schema.py`
- `tests/integration/test_weixin_personal.py`
- `tests/integration/test_weixin_personal_runtime.py`
- `tests/integration/test_workspace_upgrade.py`

## 请维护者处理后再合并

1. 保留主线后续微信服务、桌面及材料处理实现，同时纳入知识服务；不要整份采用某一侧文件覆盖另一侧。
2. 明确两个分支各自已经产生的数据库版本与迁移顺序，保留精确结构校验、不可变记录、恢复后的权限限制和旧工作区升级路径；不能仅把schema版本名改成最新字符串。
3. 将活动v4依赖锁与主线变化逐字段对账，保留新旧证据及固定SHA；重新执行依赖开发门禁，生产/发布阻断继续保留。
4. 合并后执行本目录记录的知识、基线、迁移、前端测试，并补充新微信服务及两边工作区升级回归；完整回归与实际HTTP主对话→原文引用链路在最终组合上重新确认。
5. 确认最终组合后由维护者合并。此交接不授权部署、安装更新或上传真实知识资料。

本次试点分支357项Python通过/10项Windows跳过、独立服务26项通过、前端483项通过、引用交互6项通过。详细命令、历史全量对应关系及依赖扫描分类见[本轮验证记录](README.md)；这些结果尚不覆盖处理完上述冲突的主线组合。
