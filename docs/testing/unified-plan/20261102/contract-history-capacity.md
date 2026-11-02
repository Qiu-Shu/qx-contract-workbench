# 长合同成果：版本化完整承接

2026-11-02，本机合成验证完成。当前合同请求使用 `contract-full-text-v1`：最多八对完整问答、合计65,536 UTF-8 JSON字节，单条20,000字符上限不变。无版本旧请求保持32,768字节选择规则和原序列化；普通聊天、案件、庭审预算不变。历史仍为待核上下文，不能成为新事实来源或授权。

本次先修复“最新整对超限却返回空历史”，再加入独立版本。最新完整问答仍装不下时，返回409 `MATERIAL_HISTORY_TOO_LARGE`，桌面和网页显示原因及原任务、材料、成果保留说明。不会截断原答、改写结论或自动新建任务。当前材料与历史合成后的wire继续受配置上限约束，完整持久化prepared封装仍限262,144字节；现在预览阶段也复用实际prepare精确检查。64KiB是本版本固定边界，不是无限历史或最优容量装配。

## 实际运行证据

证据根：`.audit-local/contract-history-capacity-20261102/`。Python命令使用项目`.venv/Scripts/python.exe -X utf8`。最终三个后端集合去重185项通过，另桌面及页面526项通过，四开发门分别退出0。

| 执行 | 结果与文件 |
| --- | --- |
| 安全guard首次RED：`-m pytest tests/integration/test_contract_history_capacity.py -q` | 2失败、4通过，退出1；`target-red.log/xml`。初版测试冻结为`guard-test-before-version.py` |
| guard实现 | 首次修复误引入不存在的errors模块，2失败4通过；改用既有security.ServiceError后6通过、退出0，见`guard-green.log/xml`。首个错误在本轮工具执行输出保留，不称首次实现即通过 |
| UI guard：`node --test desktop/tests/material-approval.test.cjs scripts/test_assistant_generation_render.mjs` | RED为2失败48通过，GREEN为50通过；`ui-red.log`、`ui-green.log` |
| 版本RED | 核心集成2失败；单元有效RED为5失败8通过；桌面1失败29通过。分别见`version-red-first.*`、`unit-version-red-valid.*`、`ui-version-red.log`。更早单元夹具遗漏来源hash更新的日志另保留 |
| 最终版本集成 | `-m pytest tests/integration/test_contract_history_capacity.py -q -o junit_family=legacy --junitxml=.../version-integration-final.xml`：14通过，退出0；此前一次夹具wire缺canonical排序导致1失败12通过，修正测试编码后通过，未绕过产品验证 |
| 合同及历史回归 | `test_material_followup_history.py`、`test_material_parent_context.py`、`test_contract_review_pipeline.py`及单元`test_assistant_conversation_history.py`、`test_material_input_budget.py`、`test_material_wire_capacity.py`、`test_material_model_codec.py`、`test_contract_review_codec.py`、`test_contract_live_method.py`、`test_contract_history_format.py`：97通过，退出0，`regression.log/xml` |
| 路由及原生授权 | `test_assistant_material_routes.py`、`test_assistant_material_generation.py`、`test_native_model_control.py`：74通过，退出0，`routes-native.log/xml` |
| 桌面及页面 | `node --test desktop/tests/*.test.cjs scripts/test_assistant_generation_render.mjs`：526通过，退出0，`desktop.log` |
| 开发门 | `-m cn_contract.cli schema --check`、`scripts/verify_defaults.py`、`scripts/verify_sources.py --mode development`、`scripts/verify_runtime_dependencies.py --mode development`：分别退出0，`gates.json`及四份`gate-*.log` |

单项复测及中间GREEN包含于最终集合，不重复累计。未运行全仓套件。

## 通过的具体场景

- 独立合成首答13,665字符，完整问答40,282字节；真实上传补充协议后同一合同任务完成第二次loopback生成、保存、回读，wire50,485字节，共2个attempt。前答逐字保留，旧成果JSON不变。无真实模型调用。
- 问题与成果合计67,279字节、答复19,065字符的有效样本触发明确容量错误；HTTP预览与提交没有新增授权、attempt、receipt或output。
- wire145,590字节可以容纳，但完整prepared289,883字节超限的样本在预览阶段被拒绝。另有精确262,143/262,144/262,145字节边界、JSON转义与中文UTF-8检查。
- 新版本空历史仍按原时点从账本重建；伪造为空被拒绝。未知版本、非合同冒用版本、不同任务、较小wire预算及单条字符限制均有覆盖。
- 旧合同有历史的原input/output/wire逐字不变；旧排队请求按原wire仅发送一次；旧长首答后旧规则空历史二答，再切换新版第三答，能够完整承接两次旧答且不改旧记录。既有合同pipeline含导出和备份恢复回归通过。

## 独立复核、WorkBuddy与保护结果

独立源码审阅未发现可行动问题；额外只读回放20份冻结旧请求、8份旧完整成果，wire/manifest字符串和候选canonical字节全部一致，28个源证据哈希不变，退出0。见`review/independent-legacy-replay.json`，没有生成或重新评分法律内容。

WorkBuddy只编辑授权的桌面白名单/版本校验及网页错误文字，任务`wb-bg-b80bc4f4de21`、`wb-bg-dc460dc94328`均completed并释放worker；requested/actual均为`deepseek-v4.1-flash`，桥接model_verified为true。原回执保留为`workbuddy-guard-ui.json`、`workbuddy-version-ui.json`。这证明协作任务模型，不声称修改了WorkBuddy全局桌面聊天模型。

本片基线7098个已有文件无丢失，前片76份证据未变；暂存补丁SHA-256仍为`5336578af1b1c146d7365e990ebe40deb38783bbbfa71a0baba48c22e736a335`。最终核对见`integrity.json`。合同方法提示词、前片三份原答、原实验数据库及评分保持；前片失败不被本次工程验证替代。

尚未证明真实模型总token上下文或法律内容质量。当前仍是合成工程验证，不是采用、签发或生产验收；伙伴模型接口继续待办。下一片采用新材料做[合同补件内容复核](../../../plans/2026-11-02-contract-followup-recheck.md)，原失败与评分分母保留。
