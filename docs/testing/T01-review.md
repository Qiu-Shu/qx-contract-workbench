# T01 独立审阅记录

日期：2026-10-02。审阅对象为工作区中的 T01 配置、领域模型、报告 schema、CLI、工程声明及开发依赖锁；尚未提交的文件按实际内容审阅。除本记录外，审阅者未修改实现、测试、索引或分支。

## 当前结论

原三项重要领域契约问题均经独立定向复审关闭。T01 本次工程范围独立审阅通过；未发现修正引入的实际回归。此结论不代表生产、法律样本或真实试点批准。

单一默认配置的规范化 SHA-256 与规格一致。已安装的模块入口与 console script 在仓库外均可运行；应用/测试和构建依赖的本地 wheel 哈希、元数据、许可文件及依赖闭包核对未发现重要缺口。未调用真实模型、企查查或付费服务。

## 已确认问题

1. **P2，默认配置核验脚本忽略指定路径，已修正并复核。** 初次审阅时 `scripts/verify_defaults.py` 没有解析规格 §15 的 `--file`。指定不存在文件仍退出 0、打印基线哈希。实现者加入参数解析和回归后，同一命令退出 1，返回 `CONFIG_INVALID: FileNotFoundError`。
2. **P2，Actor 的规范角色不能输入，已关闭。** 原 `domain.py` 的 `Role` 使用 `intake/lawyer/reviewer/approver/...`，规格 §1 的 `handling_lawyer/reviewing_lawyer/assistant` 全部被 `Actor` 拒绝。这会迫使后续服务另造角色映射，与 T01 的唯一规范词汇要求冲突。修正后枚举恰为四个规范角色，全部接受并可往返，八个自创旧角色均拒绝。
3. **P2，事实值的 JSON 往返丢失类型，已关闭。** 原 `FactValue` 为未加判别的 `Union[str, bool, int, Decimal, date, datetime, None]`。合法 Fact 的 Decimal/date/datetime 经 `model_dump_json()` 再 `model_validate_json()` 全部变成 str；FactDecision 共用该类型。另确认 Decimal 事实允许 `unit=None`，未保持规格 §5 的精确数值与明确单位约定。修正采用七种 `kind/value` 判别 DTO；独立 Fact/FactDecision 标准往返保留类型、精度和 UTC，Decimal 事实的 null、空白及空字符串单位全部拒绝。
4. **P2，ModelRequest 默认 JSON 输出不能作为自己的输入，已关闭。** 原 `output_schema` 只配置输入 alias `schema`；默认 `model_dump_json()` 输出 `output_schema`，重新校验时出现 `schema` missing。修正采用 `serialize_by_alias=True`，默认 JSON 仅输出规范 `schema` 键并能重新校验；继承的 extra 禁止和 frozen 约束仍保留。

以上问题描述保留初次审阅事实，后续实现增补会改变行号。关闭证据来自下述独立定向复审，不以实现者的完成声明或原有测试通过代替验证。

## 实际命令与结果

| 命令或实际探针 | 退出码 | 结果数量/内容 |
| --- | --- | --- |
| `.venv/Scripts/python.exe -m pytest tests/unit/test_defaults.py tests/unit/test_cli.py -q`（初次部分审阅） | 0 | 14 passed |
| `.venv/Scripts/python.exe scripts/verify_defaults.py` | 0 | 1 个哈希，与规格 `0e4acba46c67b731cd9662d7b118217ddc55047ab69315961c7f78dfcfa9c887` 相同 |
| `.venv/Scripts/python.exe scripts/verify_defaults.py --file config/does-not-exist.json`（修复前） | 0 | 错误接受；仍输出基线哈希 |
| 同一不存在文件命令（修复后） | 1 | `CONFIG_INVALID: FileNotFoundError`；正确拒绝 |
| `.venv/Scripts/python.exe -m pytest tests/unit/test_domain.py tests/unit/test_defaults.py tests/unit/test_cli.py -q`（领域修复前完整目标） | 0 | 80 passed |
| `.venv/Scripts/python.exe -m cn_contract.cli schema --check` | 0 | 保存 schema 与单一领域模型一致 |
| `.venv/Scripts/python.exe -m pip install --dry-run --ignore-installed --no-index --disable-pip-version-check --no-cache-dir --find-links .audit-local/t01-dependencies/wheelhouse --require-hashes -r requirements.lock` | 0 | 完整拟安装 11 包；无实际安装 |
| 上述离线 dry-run 改为 `-r requirements-build.lock` | 0 | 拟安装 setuptools 84.0.0 共 1 包；无实际安装 |
| PowerShell here-string 经 `.venv/Scripts/python.exe -` 执行独立锁探针 | 0 | 12 个 wheel、12 份 METADATA、46 条许可引用（含嵌入包重复引用）、11 条活跃依赖边；0 个错误 |
| PowerShell here-string 经 `.venv/Scripts/python.exe -` 执行 schema 与报告往返探针 | 0 | 13 个 schema 定义、14 个本地引用、6 个有属性的闭合模型对象；四类 ReviewRun 往返，0 个错误 |
| PowerShell here-string 经 `.venv/Scripts/python.exe -` 执行已安装 CLI 探针 | 0 | 清除 PYTHONPATH、cwd 使用系统临时目录；模块和 `.venv/Scripts/cn-contract.exe` 两次配置校验均退出 0、哈希一致 |
| PowerShell here-string 经 `.venv/Scripts/python.exe -` 执行角色/事实探针 | 0 | admin 接受，三个规范角色被拒绝；Decimal/date/datetime 三次往返均变 str；Decimal 无单位被接受。该退出码表示探针完成，不表示被审行为通过 |
| PowerShell here-string 经 `.venv/Scripts/python.exe -` 执行 ModelRequest 探针 | 0 | 首次模型校验接受；默认 JSON 输出后再校验出现 `schema` missing。该退出码表示探针完成，不表示被审行为通过 |

独立锁探针从 `sources/runtime-dependencies.lock.json` 取得目标平台和记录；逐一读取本地已下载 wheel，核对 SHA-256、大小、内置 METADATA、包名与版本、缓存的 PyPI JSON 和 METADATA 哈希、实际安装版本、两份 pip 锁的版本和哈希；以 `packaging.Requirement` 根据记录的目标环境计算活跃依赖，检查所有边的目标版本均在对应锁中。每条许可引用同时与本地证据和 wheel 内原始文件比较。没有重新访问网络。

schema 探针解析保存文件，检查所有 `$ref` 在本地 `$defs` 中可解、有属性的对象均 `additionalProperties=false`，随后为 sales/service/lease/nda 分别构造独立虚构 ReviewRun 并执行标准 JSON 往返。恰好 18 个不同维度、额外字段和意见双向引用的检查由已实跑的目标测试覆盖；跨字段业务校验仍以 Pydantic 为准。

## 未作为本阶段缺陷裁定的范围

- 对象级授权、客户端审批 ID 真伪、案件 membership、CSRF、正式签发和状态迁移由后续服务任务实现；当前 DTO 校验不代表取得任何权限。
- 管理员配置更新审计及实际模型/企查查预算网关尚非 T01 可调用接口；当前默认 mock、QCC 关闭。
- 独立 wheel 安装后的资源打包未裁定；本阶段约定及实际验证的是 editable 安装。
- 生产许可、上游源码 commit、规则批准、数据政策和安全审查仍有明确阻断；开发锁的可复现证据不视为生产批准。
- 正式法律样本、真实材料试点、完整审查业务闭环和复杂 Word 原生修订不属 T01 完成声明。

## 修正后的定向复审

复审限于原三项 P2 及受影响 schema；未修改实现或扩大至后续服务功能。

| 实际命令 | 退出码 | 实际结果 |
| --- | --- | --- |
| `.venv/Scripts/python.exe -m pytest tests/unit/test_domain.py -q -k "actor_accepts_only_spec_roles or actor_rejects_unapproved_role_vocabulary or fact_tag or fact_decision_tag or decimal_fact or fact_decision_rejects or model_request_standard_json_roundtrip or review_schema_contains_closed_objects_and_all_coverage_ids or manifest_binds_contract_type_and_unknown_route"` | 0 | 50 passed，61 deselected |
| PowerShell here-string 经 `.venv/Scripts/python.exe -` 执行独立复审探针 | 0 | 4 个规范角色接受、8 个旧角色拒绝；Fact/FactDecision 共 16 次往返，3 个缺失或空白 Decimal 单位拒绝；ModelRequest 1 次标准往返；0 个错误 |
| `.venv/Scripts/python.exe -m cn_contract.cli schema --check` | 0 | 保存报告 schema 与当前 ReviewRun 单一模型相同 |

独立复审探针使用八组手写虚构事实：数字外观文本、日期外观文本、bool、integer、长精度 Decimal、date、带 `+08:00` 时区 datetime、null。各组分别构造 Fact 与 FactDecision，经 `model_dump_json()` 和 `model_validate_json()` 检查 `kind`、Python 精确类型和值；datetime 另检查 UTC 偏移为 0。Decimal 使用 `0.12345678901234567890123456789` 验证未舍入。

同一探针重新构造合法 ModelRequest，确认标准输出存在 `schema` 且不存在 `output_schema`，恢复结果与原对象相等，extra 仍为 forbid、frozen 仍为 true。Fact 与 FactDecision 的独立 JSON Schema 均检查 `kind` discriminator、七个 `oneOf` 变体以及每个变体 `additionalProperties=false`。最后直接比较已保存报告 JSON 与 `ReviewRun.model_json_schema()`，结果相同。

根任务另报告全套 158 passed；本审阅者未重复全套，该数量不计入本次独立复审实跑结果。
