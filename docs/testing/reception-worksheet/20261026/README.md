# 接待追问与事项底稿：本地验证记录

完成日期：2026-10-26（Asia/Shanghai）；实施计划日期：2026-10-25。工作分支 `dhb_law`，HEAD `43257111f0d6ad03b1b8ef1f4bc86151ee58937a`。本轮没有提交、推送、更新服务器或安装版。

## 实际交付

对话页顶部“接待底稿”打开内联编辑区，保存原始陈述、内部事项底稿、追问、材料要求和独立客户回复。提纲明确插入到原备注之后；候选需明确采用、保存。事项底稿是可编辑文字，复用现有档案版本和受保护人工字段，没有新数据库结构或隐藏文字解析器。

本地借贷模板给出追问理由、原话摘录和材料要求，标明未调用模型。虚构“借出10万元、部分已还”会追问实际还款时间、金额、方式与凭证，不推定余额。“准备AI追问”保存补充输入并生成可核对任务，沿原发送入口继续；准备操作不发送模型请求。现有模型模板、批准和预算路径保持原样。

客户回复可接既有“成果与导出”按客户版预览、复制、下载Word。内部底稿不会进入客户版。恢复工作区允许精确读取底稿及回执，继续禁止写入和重新发送。

## 检查结果

| 检查 | 实际结果 | 证据 |
|---|---|---|
| 专项后端与合成HTTP模型链 | 17 passed，exit 0 | qx-worksheet-final-backend.log |
| 12个关联Python模块，含上述专项 | 235 passed，exit 0 | qx-worksheet-final-related.log |
| 专项前端 | 15 passed，exit 0 | qx-worksheet-node-green4.log |
| 关联前端（含专项） | 336 passed，exit 0 | qx-worksheet-final-frontend.log |
| 桌面回归 | 369 passed，exit 0 | qx-worksheet-final-desktop.log |
| 独立审查探针复跑 | Python 3 passed、exit 0；晚准备结果未覆盖新skill，edit次数0 | independent_review_probe.py、independent_prepare_probe.mjs及对应log |
| 实际Chromium | 1280/390宽度、保存/重开、未保存导航、模板采用、断ACK查回执、准备不发送、客户Word下载通过；页面异常0，外部请求0 | browser-report.json、两张worksheet截图 |
| 实际Word包和渲染 | 1页人工检查；全部XML含客户回复且无内部备注 | artifact-check.json、worksheet-client.docx、page-1.png |
| schema、defaults、development sources | 三项exit 0 | gates.json、gate-1至3.log |
| runtime dependencies | exit 1：MANIFEST_INVALID:FileNotFoundError | gate-4.log；未修复、未称全门通过 |

专项Python覆盖真实qxbak备份恢复、旧会话/写入拒绝、精确只读回执、当前身份与CSRF、保存CAS、来源不可由客户端替换、重复请求稳定回执。模型测试仅向合成本机HTTP provider发送一次，验证沿原受控profile执行并保存待核候选；没有调用真实外部模型。各测试组有重叠，不能相加当作不同用例总量。

浏览器真实提交成功后丢弃ACK：观察到1次POST和1次回执GET，没有重发提交。准备后generation POST为0。浏览器脚本第一次在所有产品断言结束后，记录报告时误对普通对象调用url()而失败；修正记录器，在全新合成工作区完整重跑成功。首轮合成工作区样本保留在任务临时目录，记录器错误未另存日志；最终证据为本目录最终运行。

Word渲染使用QA专用FONTCONFIG_FILE及系统已有中文字体，见render-fonts.conf；没有改动产品文档、系统字体或安装配置。

## 修复与独立复核

见[independent-review.md](independent-review.md)。首次RED包括缺失实现、明确采用相同候选未标记修改、关联接待记录连续保存覆盖人工值、恢复读取及晚准备结果隔离。RED日志按实际保留。合成模型测试首次失败是断言未解码wire JSON转义，修正断言后通过；不是外部模型成功证据。

原132份修改/未跟踪文件任务前已备份至`.git/codex-preserved/reception-worksheet-20261025`。baseline-preservation.json记录实际变化及保留结果；task.diff是相对此基线的本轮修改，source-sha256.json固定本轮源文件。既有CH08、接待助手等改动不归为本轮新增。

## 复现命令

本机Python：`/tmp/qx-audit-20261024-venv/bin/python`。在仓库根使用`PYTHONPATH=src`，pytest采用`--basetemp=/private/tmp/一个新的专用目录`。

```sh
python -m pytest tests/integration/test_reception_worksheet.py tests/integration/test_reception_worksheet_model.py -q
python -m pytest tests/integration/test_reception_worksheet.py tests/integration/test_reception_worksheet_model.py tests/integration/test_assistant_pages.py tests/integration/test_assistant_profile_routes.py tests/integration/test_assistant_profile_store.py tests/integration/test_assistant_profile_history.py tests/integration/test_assistant_profile_execution.py tests/integration/test_assistant_conversation_history_flow.py tests/integration/test_assistant_outputs.py tests/integration/test_assistant_output_models.py tests/integration/test_reception_assistant.py tests/unit/test_assistant_profiles.py -q
node --test scripts/test_reception_worksheet.mjs
node --test scripts/test_assistant_*.mjs scripts/test_reception_worksheet.mjs
TMPDIR=/private/tmp node --test desktop/tests/*.test.cjs
python -m cn_contract.cli schema --check
python scripts/verify_defaults.py
python scripts/verify_sources.py --mode development
python scripts/verify_runtime_dependencies.py --mode development
```

browser_server.py/browser_check.cjs保留实际合成浏览器步骤。需要先创建全新临时目录并写入`/tmp/qx-worksheet-browser-path`，启动18770本机合成服务；脚本含本机运行时路径和纯虚构测试账户，不可用于真实账号。独审Python探针通过pytest以新basetemp复跑；独审Node脚本直接运行。源代码与截图等证据为本地验证，未覆盖安装版、Windows、真实客户资料、真实模型服务质量、律师法律质量验收或生产可用性。
