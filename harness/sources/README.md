# 来源与重建

两个法律库 ZIP 来自用户提供的上游英文版与中文版，原包内均含 Apache-2.0 LICENSE；保留原始归档，适配代码不执行包内脚本。运行 `python scripts/prepare_legal_skills.py --workspace <路径>` 重建法律库与 Skill 目录，参数相对 `harness/` 执行。原库中的外部服务说明不代表已配置对应账号。

微信归档来源、版本和提交见 [wechat-sources.json](wechat-sources.json)，MIT 许可保存在本目录。该文件的 `unverified` 为最初引入时的历史状态；本人扫码及手机收发的后续实测见 [本机交接](../docs/2026-11-03-本机交接.md)。Harness npm 固定为 0.2.2-alpha.2，许可见 [Harness-MIT-LICENSE.txt](Harness-MIT-LICENSE.txt)。

| 归档 | SHA-256 |
| --- | --- |
| `claude-for-legal-main.zip` | `ab1e6bef45e6ddc43f3a8788c5bc20f126149ddfd68b3f64da6ce4b0accfb8f7` |
| `claude-for-legal-ZH.zip` | `c00397d993994a63bb911efa06e0a93b2bbc4d140cd2e3f1801911461fafead7` |
| `dsh-wechat-media-feb4088.tar.gz` | `28322d02d20e3ad4db91fbe3d7ab29878a331d32dabe5795520d8ed6d5a189d5` |

其他复用 Skill 的来源和文件摘要见 `config/skills/sources.json`，各自许可证随源文件保留。安装包由 GitHub Release 分发，依赖缓存和用户工作区不入 Git。
