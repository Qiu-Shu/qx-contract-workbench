# 阶段 2.1 Skill Registry 独立复核

审阅相对 `phase2-baseline/files` 的 domain、skill_registry、材料装配/codec、Web/本机启动增量，以及两份作者新增测试。没有修改产品源码、Git/index；独立探针仅写 review 目录，使用合成材料、隔离数据库和回环模拟响应。

## 独立实际检查

命令：`.venv/Scripts/python.exe -X utf8 -m pytest .local/unified-plan-20261101/review/test_phase2_registry_independent.py -q --tb=short -p no:cacheprovider --basetemp=.local/unified-plan-20261101/review/pytest-phase2-registry4 --junitxml=.local/unified-plan-20261101/review/phase2-registry-independent-final4.xml`

**4 passed，5.53 秒，exit 0**：

1. 生成完成后删除当前 Skill/metadata 文件并移除 registry，历史 attempt、全部模型记录校验及 DOCX 导出继续成功。
2. 已登记 Skill 仍受调用预算约束：预算不足时抛出 BUDGET_EXCEEDED，0 模型请求、0 attempt。
3. 已登记任务入队后方法文件改变：GenerationTasks 安全结束为 failed_before_send，无输出、0 模型请求，账本完整性校验通过。
4. 相邻 capabilities.json 损坏时本机启动失败，不退回旧方法。

初次探针有测试收集导入错误；接着预算探针先用了模型不允许的 0 值、又遗漏 grant 所需事件循环。这三次属于审阅探针错误，未据此报产品缺陷，XML 分别原样保留。最终四项结果以 final4.xml 为准，不累加中间运行。

## 已核对的保护

- 来源只从可信本机配置读取固定 metadata/SKILL 相对位置；双 SHA、元数据 name/version、显式本地使用批准、绝对根和重定向检查。
- 客户端 MainMaterialSelection 没有源路径或方法字段；提交重建当前来源并比对完整 basis，源文本进入完整 wire 输入大小检查。
- 使用既有材料来源、scope、许可、预算、幂等及输出账本；Skill 文本不授予工具或业务权限。
- 方法快照和元数据摘要保存在现有 manifest；历史验证不依赖当前安装路径。根字段不进入 CapabilityInvocation。
- 合同继续使用现有 METHOD；当前登记配置只接受 sales/case，court 尚无适配器，在已配置 registry 中缺少 court 会明确阻断。

## 必须明确的兼容边界

当前 `skill_registry.resolve_for:65` 在 registry=None 时返回 None；`local_server.build_local_app:199–201` 在 capabilities.json 不存在时不加载 registry，继续启动。因此**注册文件缺失时，新调用仍会走旧通用方法**，并非仅允许旧历史回读。作者 `test_unconfigured_history_keeps_exact_previous_wire` 实际也创建了新业务和新预览，确认这个行为。

若“缺失不回退”包括注册文件缺失，这里尚有待修复的 P2 缺口；如果阶段 2.1 有意保留明确的未启用兼容模式，应记录该例外，不能声称未配置本机已经启用来源绑定或所有缺失都阻断。该边界已单独发给主代理核实；本审阅没有把尚未部署的配置宣称已生效。

已配置来源链内未发现新的可复现权限或账本阻断问题。持衡适配、九份接待资料/知识自动检索和真实模型仍不在本次完成范围，阶段 2 整体不能据此标通过。

## 审阅时摘要

- domain.py: `111f9dc2cb1f32cf562f5c716e3f3d936d68ccd0aed2d27c47f5a27773e21fcf`
- integrations/skill_registry.py: `ce8d4337b1d5ff70183e0bc74b7e081831d733ef43e6cf44311e050a76bb862a`
- assistant/material_preparation.py: `169dbacdd0dd192c736deec4de744037e88d1d9a3b887c8a6837ec4487322721`
- assistant/material_codec.py: `ed9826efd389fca29050348c4e3d3361f10a29c6b23f42bbeefb1582632f9e84`
- web/app.py: `8c7bc69be527ad5c5606065f9440e23d52cf682839098480c77da8ab1e59ecbe`
- web/local_server.py: `701b13e849008c43b2423750d722de3c9da3fb5c4a076d523ef2ac727ad2a71c`
