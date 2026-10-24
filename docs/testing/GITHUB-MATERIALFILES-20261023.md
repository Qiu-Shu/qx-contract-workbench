# UX-02 材料拖拽与多文件切片 GitHub 同步回执（2026-10-23）

- 仓库：`Qiu-Shu/qx-contract-workbench`（私有），分支 `codex/contract-review-v2`。
- 产品提交：`0446ca8`「UX-02: drag-and-drop multi-file materials with widened formats」（19 文件，+1685/-45，含执行合同与证据目录；含 GitHub 复用评估对照表）。
- 推送输出：`90cf287..0446ca8  codex/contract-review-v2 -> codex/contract-review-v2`（正常推送，未 force；推送时代理 127.0.0.1:57373 一度宕机，后台每 40 秒重试，约 2 分 41 秒后成功）。
- 远端核对：`git ls-remote origin codex/contract-review-v2` 返回 `0446ca8b668664e71bb4eb27e2aae16d52669b25`，与本地 `git rev-parse HEAD` 逐字符一致。
- 敏感模式扫描：diff 对真实密钥模式（sk-*/bearer）0 命中；测试仅用虚构材料。
- 验证摘要：Python 新增格式测试 5/5；关联回归 109 通过 + 2 基线复现环境失败（safe-delete shim 超深路径 Errno 53 家族，HEAD worktree 同等复现 2/2）；前端全套件 146/146（新增 4 项）；四开发门 exit 0；桌面侧零改动。证据：[material-files/20261023](material-files/20261023/README.md)。
- 边界：无 schema/依赖变更；未引入第三方库；已上传原件物理删除不在本片（账本引用约束，另立片）；parse 仍仅 DOCX。
- 本回执为独立第二次提交，推送后同样以 ls-remote 核对为准。

## 追加：.doc 支持同步（2026-10-24）

- 追加提交：`992ddf3`「UX-02 follow-up: accept legacy .doc originals」——`application/msword`/`.doc` 入 mime 映射与前端预筛，OLE2 魔数嗅探防伪造，读取仍仅 DOCX。
- 推送输出：`13e4f50..992ddf3  codex/contract-review-v2 -> codex/contract-review-v2`（正常推送，未 force；代理不稳，前台重试超时后转后台每 45 秒重试成功）。
- 远端核对：`git ls-remote origin codex/contract-review-v2` 返回 `992ddf33ba3c44704fecc2b18f8b58a9bf2532a5`，与本地 `git rev-parse HEAD` 逐字符一致。
- 验证：格式测试 5/5（含 .doc 往返与伪造拒绝）、前端全套件 146/146、四开发门 exit 0。
