# CH-06B2b1：选定历史引用的本机完整预览

2026-10-20，基线 `0d53fdfdae806c6fec90c01cab1531a7cb666831`。本片实现开发接口；没有新增律师选片界面、资料发送许可或模型调用，安装版0.4.1未更新。

## 实现及分层

请求只接受当前范围、草稿版本和1—8个有序不重复引用ID。服务从当前草稿和已保存回执重建问题与引用，核对所有者、对话、案件、绑定和历史版本；跨范围、陈旧选择、已选附件、归档或恢复副本均拒绝。

`assistant/context_preview.py`负责来源及当前权限；独立`providers/context_preview.py`负责纯投影和规范JSON；薄HTTP模块校验登录、同源、CSRF，并在读请求体前后复核。配置读取不读取密钥、不消耗或改变旧许可。无新DDL、依赖、队列、业务记录写入。DTO统一在domain.py，旧V1类型未加字段。

预览保留原问题、引用UUID、标题、原文位置、版本、摘要及待核状态；内部metadata/身份不进入wire，但原文字面内容不自动脱敏。无配置仍返回完整清单和系统模板；有配置返回完整请求、UTF-8字节数和摘要。超限保留完整预览，不截断。`ready`仅表示符合配置预算，所有状态都`sending_enabled=false`。

## 本轮结果

| 验证 | 实际结果与证据 |
| --- | --- |
| 最终关联回归 | **644通过，0失败/错误/跳过，exit0，461.141秒**；[完整报告](target-verification.json)、[JUnit](target.xml)、[输出](target.log)、[节点清单](target-nodeids.txt)。491份源码/配置/测试/脚本输入前后一致。不是全套。 |
| 四开发检查 | schema/defaults/sources development/runtime dependencies development均exit0；[gate-1](gate-1.log)、[gate-2](gate-2.log)、[gate-3](gate-3.log)、[gate-4](gate-4.log)。开发允许的原有发布待办仍按日志保留。 |
| 新增测试 | 31纯预览+11服务+14HTTP+1配置，共57项，包含在最终关联回归中，不重复相加。 |
| 旧V1字节 | 固定请求973 UTF-8字节，SHA256 `fe24920857e4a951b627c2ee0b4c3a01253c550e7cf134e3420b3db843d3873f`；[codec记录](codec-summary.json)。独立Spec还比较固定基线的三个DTO序列化。 |
| Windows实际HTTP | **9组检查、27次请求、exit0**，4条合成引用，3402字节内容在3401预算时完整返回超限；跨域/缺CSRF/陈旧选择拒绝。主模型生成、Jev、密钥读取均0，预览没有新增assistant表记录。端口61592已关闭；[摘要](http-summary.json)、[回执](http-report.json)、[脚本](http-probe.py)。 |
| 独立需求复核 | 6项独立探针通过，0待修；撤权/改草稿/恢复fence请求体竞态、损坏引用、V1与配置许可边界。[审查](spec-review.md)、[输入及结果](spec-probes.json)。 |
| 独立规范复核 | 4项定向检查通过，硬规则及需修建议均0；[审查](standards-review.md)、[输入](standards-inputs.json)、[改名映射](standards-rename-map.json)。 |
| WorkBuddy | 本轮connected后`wb-93002fc64088` completed/end_turn，成功读2文件，第三路径不存在即跳过；只读方案意见，非产品验证。[原回执](workbuddy-completed.json)、[统筹逐项核对](workbuddy-resolution.md)。 |

目标集合涵盖本片四个接口、既有生成/原生许可、法库/研究任务、模型/附件/旧版备份恢复和40份合成材料验收；与已完成的旧全套结果分开，未因文档变化重复全套。已有独立DuckDB解释器仅用于可能需要的合成测试环境，本轮未访问旧试点库或安装新依赖。

## 失败和诊断均保留

- 有效RED分别覆盖codec缺失、服务缺失、HTTP404、配置入口缺失；见相应`*-red*`与[test-counts](test-counts.json)。最初服务测试的C盘预算错误属于环境前提失败，不作为产品RED。
- 服务扩展测试一轮10通过/1 fixture错误，修正fixture导入后该项通过；HTTP过期许可fixture校准后精确复验通过。这些早期数量不叠加到最终644。
- 第一次全套因unit/integration同名测试收集失败；只更改integration文件名，字节内容不变，[原失败](full-collection-error/full.log)。
- 第二次广泛回归在深目录出现失败后中止；[中止说明](full-path-interrupted/README.md)明确原runner误读陈旧XML的counts不可采用。独立相同样本在短路径完成、深路径稳定WinError206，相关旧源码与基线一致；[诊断](path-diagnosis.md)。并未取得每个原F的完整栈，不一概归因。旧合同长路径问题尚未修复，TODO中WIN-PATH-01单独跟进。
- 最终关联runner初次缺少仓库import路径，26项收集错误；只修本地测试脚本后重跑，[原错误](target-import-error/target.log)。Spec一次诊断变量错误、实际HTTP三次探针初始化错误、路径诊断一次元数据错误均保留，未改变产品规则。

证据文件逐项摘要见[manifest](manifest.json)，只包含筛选后的合成回执/诊断脚本；没有临时数据库、真实原件、凭据、安装器或运行环境。

## 复现与下一步

关联复现先在仓库根目录建立全新、足够短且有40GiB以上可用空间的专用D盘临时目录，按[target-nodeids](target-nodeids.txt)运行pytest；[verify.py](verify.py)与[target_runner.py](target_runner.py)记录本轮方式。脚本中的`.local`输出位置是原运行位置，若复用已归档脚本须调整本机输出目录，不覆盖证据。用户已有临时目录、真实资料目录不可用作pytest basetemp。

独立HTTP脚本在真实Windows回环运行源码服务，不是TestClient；没有验证Electron窗口、GUI、冻结后端、安装器、系统DPI、真实供应商或法律质量。本片不提供整体包体/RSS/冷启动改善结论。

下一片按[发送存储设计](../../../plans/2026-10-20-context-send-storage.md)同时闭合新许可、不可变输入格式、来源关联、原生确认、费用/取消和升级恢复，再接一次资料辅助回答；设计未实施。之后才扩展有界多轮与自动档案。

WIN-PATH-01另有[可复用路径适配接续说明](long-path-readiness.md)，列出既有helper及合同创建/读取/事务清理/恢复要共同覆盖的操作。该说明是未实施方案，不是本片修复记录。
