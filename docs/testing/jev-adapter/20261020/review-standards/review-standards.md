# CH-05A 独立 Standards 审阅

**最终结论：无未关闭 P0–P3；发现并关闭 1 项 P2。** 本报告只覆盖 Standards，不替代 Spec 或真实供应商验收。

基线 `7dd5abbb4890b25303bc77080c4d24fcc3f5e716`；开始时 HEAD 等于基线，three-dot diff/提交列表为空。按任务审阅工作区 `domain.py` 增量及新增 routing/jev/codec，随后仅扩至日志修复所需 `main.py` 两行。采用仓库 AGENTS、Ponytail full、code-review 的 12 项 Fowler smell baseline，以及本片计划/协议所载模块边界；不重新委派。

## 发现与关闭

**P2：两个提供器交替安装日志保护会无限嵌套全局工厂。** 原 `jev.py:24–35` 与主提供器各自仅识别自己的 marker；交替安装 600 对后，普通应用的 `Logger.makeRecord` 出现 `RecursionError`，影响全进程日志。属于重复状态性代码导致的组合缺陷，而非单纯风格建议。原复现 `log-composition-red.log/.exit`：退出 **1**，无模型/网络/密钥读取。

作者在两处工厂加 `functools.wraps(previous)` 保留已有标记（现 `jev.py:25–38`、`main.py:149–161`），保留各自 ContextVar，不建立提供器互相依赖。冻结后**原探针** `log-composition-final.log/.exit` 退出 **0**：600 对交替、普通日志、Jev/主模型隐私日志与外部上下文均通过。此 P2 已关闭。

## 其余源码判断

- `domain.py:2986–3089`：业务 DTO 集中于领域模块，复用 frozen/extra-forbid；DTO 只做校验，没有 HTTP、DB 或授权动作。缺 usage 不补零。
- `routing.py:7–24`：只依赖 domain/typing；显式选择优先，建议仅收窄已允许技能。返回三个业务字段，不读环境/数据库、不修改输入、不切换供应商或授予权限。
- `jev_codec.py:31–174`：固定问题/严格投影/响应校验独立于传输；完整 scope 参与本机摘要但不上送。固定错误消息、关闭序列化警告、反射检查，未记录原始正文或异常字符串。
- `jev.py:49–240`：默认关闭，无前置回调则 no_egress；本地跳过先于密钥/延迟 HTTP 导入。复用既有 httpx2，无新 SDK、无生产接线、无 DB/持久队列或主提供器依赖。固定端点、无代理/重定向/重试，配置复验与取消仍在本模块边界内。

## 独立证据

仅复验两个既有脚本：日志组合 **1 场景**及架构 **3 组**，均退出 **0**；不把作者 124 项计入独立数量。`architecture-final.log/.exit` 证明冷导入无 SDK/httpx2/主适配器/web/DB；默认关闭和缺 preflight 均无凭据读取、HTTP 导入、外部网络；路由不改请求或候选集合。命令见 `review-standards.json`。首次与最终日志均保留。

最终复验后 SHA-256 见 `source-final-sha256.json`，其中 Jev/codec/main 与作者冻结值一致：

| 文件 | SHA-256 |
|---|---|
| domain.py | `9d16e632bd0f50149b6843cf4781669e9f7032e0dc55fae59a22752f5bc28516` |
| routing.py | `b6529e27d501fc129851c9c304fa2143e066010eebc7596482c27cfff0fd1cee` |
| jev_codec.py | `bc69e1145e09de8d3a53fd24c8cf0093a0120198d330041ea5e216b38deb1e69` |
| jev.py | `06f913b805fca0d4bc5df636a485dca39b02761cb0a9edc9b8e18ed7edec8dd2` |
| main.py | `cd15eec8824219294b484fa46289f7a30ed0fefec4aa03eaf54557a6b2869598` |

未改产品、作者测试、项目状态或提交；未读取真实密钥/材料，未调用远程模型。未重跑协议全套、Windows 冻结验收；持久授权/预算接线及真实中文效果仍是后续边界。
