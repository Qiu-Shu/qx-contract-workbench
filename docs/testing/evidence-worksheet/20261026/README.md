# 材料目录与事实证据底稿：实际验证

日期：2026-10-26，Asia/Shanghai。分支dhb_law，基线af1ba29609b5188006003b4ff9a217362a7064b1；以下为开发验证完成时的记录。用户随后明确要求本片提交并推送到dhb_law，验证记录随源码交接；实际同步以Git提交和远端ref核对为准。主线合并、服务器和安装版0.4.1更新不在本次操作范围。

## 当前可操作范围

对话页顶部“事实与材料”打开内联底稿：查看当前及已移出材料的目录，复用既有上传/原文读取；选已保存接待原话、DOCX/文字PDF解析锚点或人工摘录，登记事实类别、日期、核对状态和相反说法。事实按日期显示，未知日期保留空值。借款约定、实际交付、还款分开；本片以文字记录款项，没有余额/利息计算。

每条依据由服务器核对归属、固定版本、原件摘要和解析位置；原话要求来自明确保存的人工陈述。人工摘录标明其来源种类，不冒充OCR。核对状态与来源分别记录，“律师登记已核对”不把客户陈述变成材料证明。

支持编辑、移出当前版而保留历史、保存重开、只读历史回看和依据回查。材料重读/移出或原话变更后，已有事实保留旧依据并提示重核；新事实不能借新ID使用不再当前的旧来源。未加入清单的表单内容也阻止导航/整份保存。保存未知时仅按原request_id查询回执，不重发。

事实单独存于新增不可变assistant_evidence_revisions表；assistant-evidence-v1为精确追加版本，旧档案、模型协议和原备注不改。最多100条事实、200次保存版本、单请求/快照2MiB。新表及历史来源验证随初始化、原位升级、备份恢复接入；恢复副本仅允许精确GET底稿/历史/回执，禁止写入和重发。没有模型或外部服务调用。

本片不包含后续待补任务闭合、争点工作稿、文字庭前对练、自动OCR、全卷AI或新成果导出。原CH08仍保留原范围。

## 实际结果

| 检查 | 结果及证据 |
|---|---|
| 最终事实与schema专项 | 59 passed，exit0；qx-evidence-final-special3.log。包含38份旧结构指纹、真实原位升级保留旧人工档案、来源篡改、不可变触发器、移出历史、真实qxbak恢复及PNG原件人工注记；PNG检查不证明识字准确性 |
| 16个关联Python模块 | 349 passed，exit0；qx-evidence-related.log。包含专项的前56项；随后新增3项在最终专项另验，组间重叠，不累计不同用例数 |
| 微信/任务/schema兼容7模块 | 250 passed，exit0；qx-evidence-compat3.log |
| 前端专项/关联前端 | 专项12 passed；关联348 passed，exit0，包含专项；qx-evidence-node-green3.log、qx-evidence-frontend.log |
| 桌面逻辑回归 | 369 passed，exit0；qx-evidence-desktop.log；不等于原生Windows安装器验收 |
| 独立HTTP探针复跑 | 3 passed，exit0；qx-evidence-review-final2.log |
| 独立前端竞争探针 | 表单刷新返回false并保留旧base_revision；迟到A未覆盖后选B；对应review-form/source-final日志 |
| 实际Chromium | 全新合成工作区完成上传读取、四条事实、相反说法/人工摘录、修改重开、版本1只读、版本3返回当前、依据回查、材料移出提示、丢ACK后版本4；1POST+1回执GET，0模型发送/外部请求/页面异常；browser-report.json |
| 真实页面检查 | 人工查看1280目录/事实及390宽度截图，无横向溢出；另只读浏览器检查刷新按钮恢复可用，补拍evidence-directory-1280.png |
| 开发门 | schema/defaults/development sources均exit0；runtime dependencies仍exit1：MANIFEST_INVALID:FileNotFoundError，见gates.json及gate-4.log |

最终专项59项由原56项加触发器/移出历史两项及PNG人工注记一项组成。独审同一审查者复核，不是两名独立审查；源码已由主执行者核对并复跑探针，见independent-review.md。

## 原始失败与修复

- 首轮11项RED为缺少新路由，见qx-evidence-red.log；前端10项RED为缺少binder。
- green1：6通过/5失败；测试夹具误用/parse而非既有/parses，产品又重复启动了Database已自动开启的BEGIN IMMEDIATE。修正夹具并移除重复事务，保留原数据库串行保护。
- green2：8通过/3失败；补新schema对既有校验器/当前入口的精确版本兼容。测试中的结构错误引用应422；撤权探针改拦截实际body_input而非未调用的Request.body。
- green3：10通过/1失败；版本白名单机械编辑引入一处语法错误，compileall定位并修正。green4后端11通过，真实qxbak通过。
- schema1：55通过/1测试错误，actor篡改先违反FK；改为已有另一user再验证语义拒绝。schema2：56通过。随后追加触发器测试第一次漏导入deepcopy，57通过/1失败；补导入后58通过，最后PNG专项合入59通过。
- compat首轮命令引用不存在的测试文件，exit4/0项；compat2为239通过/11失败，均是旧测试把最新版本写死19或造旧schema时漏移除新增表。仅修改3份测试的当前目标和精确旧夹具，不改历史指纹；兼容同组重跑250通过。
- 独立探针首次主执行者复跑因缺tests/integration搜索路径而收集失败；补PYTHONPATH后3通过。
- 两项实际前端缺陷：表单编辑未入清单时刷新可能覆盖别窗新事实；A/B依据回查逆序返回会显示旧A。均已用失败回归确认后修复，详见独审记录与RED日志。

## 复现

仓库根运行，Python使用/tmp/qx-audit-20261024-venv/bin/python，环境PYTHONPATH=src；pytest使用全新/private/tmp专用basetemp，保留产品符号链接限制。

```sh
python -m pytest tests/integration/test_evidence_worksheet.py tests/integration/test_evidence_schema.py -q
python -m pytest tests/integration/test_evidence_worksheet.py tests/integration/test_evidence_schema.py tests/integration/test_reception_worksheet.py tests/integration/test_reception_worksheet_model.py tests/integration/test_assistant_pages.py tests/integration/test_assistant_profile_routes.py tests/integration/test_assistant_profile_store.py tests/integration/test_assistant_profile_history.py tests/integration/test_assistant_profile_execution.py tests/integration/test_assistant_conversation_history_flow.py tests/integration/test_assistant_outputs.py tests/integration/test_assistant_output_models.py tests/integration/test_assistant_attachment_routes.py tests/integration/test_assistant_profile_sources.py tests/integration/test_reception_assistant.py tests/unit/test_assistant_profiles.py -q
python -m pytest tests/integration/test_weixin_generation_dispatch_schema.py tests/integration/test_weixin_generation_dispatch_integrity.py tests/integration/test_weixin_generation_dispatch.py tests/integration/test_weixin_generation_dispatch_atomic.py tests/integration/test_weixin_generation_ingress.py tests/integration/test_weixin_generation_integrity.py tests/integration/test_task_drafts.py -q
node --test scripts/test_evidence_worksheet.mjs
node --test scripts/test_assistant_*.mjs scripts/test_reception_worksheet.mjs scripts/test_evidence_worksheet.mjs
TMPDIR=/private/tmp node --test desktop/tests/*.test.cjs
```

独立HTTP探针需PYTHONPATH=src:tests/integration，pytest以新basetemp运行independent_http_probe.py；两个独立Node探针直接运行。browser_server.py会创建全新合成目录和18771本机服务；browser_check.cjs读取指针完成合成流程，含本机Chrome/Playwright路径，服务需手工按步骤启动。脚本中的账户均为虚构测试账户。

原af1ba29基线文件指纹见.git/codex-preserved/evidence-worksheet-20261026；baseline-preservation.json列实际编辑文件，source-sha256.json固定本轮源文件。原始测试日志含格式空白，保留原字节。当前验证不覆盖全仓Python、发布安装版、真实客户资料或律师法律质量验收。
