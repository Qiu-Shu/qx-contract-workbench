# 待补材料与跟进清单：实际验证

日期：2026-10-26（Asia/Shanghai）。分支dhb_law；基线4afbd62324dd8522e878370edb2966d9d986fedd。本文为开发验证完成时的记录。用户随后明确要求将本片提交并推送至dhb_law，记录随源码交接；实际同步以Git提交及远端ref核对为准。未合并或更新服务器/安装版0.4.1。

## 本片交付

对话页顶部“待补与跟进”可记录标题、待补原因、影响、下一步、期限、状态及处理结果；每项至少关联一条固定版本事实或一份已有原件/读取版本，每类最多10条。未收到的材料先写在待补内容，收到后人工关联原件。状态由律师登记为待补、已催补、收到待核、已处理或不再跟进；后两者必须有结果。新增上传不自动完成或重定向任何事项。

事实更正/移出、事实引用的原话或材料变化、关联材料重读/移出后，显示需人工重新核对。已处理项也可重新出现在待办视图；明确取消项不会自动复活，在全部/不再跟进仍可回看提醒。状态和旧结果不静默改写，无关事实更新不误报。没有编辑/待查结果时重开清单即读取新提醒；有草稿时保留，保存/取消后再核对来源。

编辑旧项保留原引用，只有明确点击关联当前所选才替换；可修改、移出当前版而保留历史、历史只读、回查固定事实及原件。新ID不能复制不再当前的旧引用。允许为当前底稿里待重核的事实新建open事项来追补，但会立即显示提醒；有重核缺口时拒绝新完成或改写已完成结果。

独立不可变assistant_followup_revisions表，assistant-followups-v1精确追加；旧40份结构指纹不变。请求固定scope/profile/evidence/base版本，保存前后核权限和来源，原件I/O后重核。回执幂等，未知仅GET查原请求，不重发。历史as-of核验拒绝未来事实/档案/材料版本；真实qxbak恢复保留新增记录和来源，只允许精确读取。

容量：100项、200次保存版本，单请求及快照2MiB。本片没有模型调用、自动催补/消息、提醒自动化、OCR、余额计算或新导出。原档案、事实和材料不因跟进状态而自动更改。

## 验证结果

| 检查 | 实际结果与证据 |
|---|---|
| 后端专项 | 最终23 passed，exit0；qx-followup-final-backend.log。包含材料先行/无事实、后续上传不自动完成、完整状态历史、来源变化重核、伪造/CAS/CSRF/当前权限/撤权、语义篡改及真实qxbak只读恢复 |
| 新schema专项 | 70 passed，exit0；qx-followup-schema-final-only.log。旧40结构指纹、精确迁移、原位升级保留既有evidence与身份、未知结构拒绝 |
| 18模块关联Python | 444 passed，exit0；qx-followup-related.log，包含新schema70和当时后端22；最后新增材料先行一项由最终23专项覆盖 |
| 8模块schema/微信任务兼容 | 342 passed，exit0；qx-followup-schema-final.log，包含新schema70，与关联组重叠 |
| 前端专项/关联前端 | 最终40 passed；关联388 passed，exit0；followup-frontend-reopen-green.log、qx-followup-frontend-final2.log |
| 桌面逻辑 | 369 passed，exit0；qx-followup-desktop-final.log |
| 独立HTTP/Node探针复跑 | HTTP8 passed、Node6 passed，exit0；qx-followup-review-final.log、qx-followup-review-node-final.log |
| 真实Chromium | DOCX实际上传读取→事实版本1→关联清单→4状态→历史及依据回查→事实版本2→重开清单出现需重核→明确重关联→丢ACK1POST+1回执GET→重开版本5；0模型发送、外部请求、页面错误；browser-report.json |
| 页面 | 人工查看最终1440目录和390清单截图，无横向溢出；表单样式与既有页面一致 |
| 开发门 | schema/defaults/development sources三项exit0；runtime dependencies仍exit1：MANIFEST_INVALID:FileNotFoundError，见gates.json |

各测试组有重叠，不能相加声称不同测试总数。不是全仓Python、原生Windows安装、真实客户或律师法律质量验收。

## 失败和修正

- 后端首轮15项RED为缺少路由，green1全部15通过。补权限/原件I/O撤权/重哈希语义篡改后22通过；最终另补材料先行及不自动完成为23通过。
- 前端首轮缺binder，34失败；首轮实现33/34，一个测试未实际修改却期待POST，修正触发条件后34通过。独审确认原因/影响空白可加入但真实HTTP422，补验证及取消项筛选，先34通过/2失败，后36通过。
- 同CID绑定版本变化会reset而丢草稿和未知请求，独立探针实际确认。当前无公开重绑定API，此为状态防护缺口，不能称普通用户现行必现。修复保留同对话/工作区草稿及request，阻断旧写与响应；明确放弃才采用新绑定，未知仍GET；先36通过/2失败，后38通过。切对话/工作区或撤权仍清私有内容。
- 干净清单重开最初不取新提醒，补回归先39通过/1失败，修复后40通过；有表单、清单草稿或未知结果时重开不自动读取或覆盖。
- schema首轮29失败/40通过；一个Database导入拼写错误在实现前已修并确认余项为预期缺失，之后新增纯追加结构断言，最终70通过。主兼容组首轮333通过/8失败，仅修本轮新增表影响的精确降级夹具和最新迁移终点，同组最终342通过。
- 首次实际浏览器在等待重核提示时，测试期待“需重新核对”，产品实际文本为“需人工重新核对”；流程已产生正确提示。修正检查文本后全新工作区通过，之后按最终样式及重开逻辑再用全新工作区完整通过。保留browser1/2/final日志。

## 保留的既有历史失败

扩展10个更旧schema模块：526 passed、8 failed、6 errors（qx-followup-schema-historical1.log）。将4afbd623源码独立展开后，相关14个相同测试节点精确复现8 failed/6 errors，另33 passed/199 deselected（qx-followup-schema-baseline-failures.log）。主执行者比对失败/错误节点集合完全一致。

这些涉及更旧library迁移delta及v16/v17原位升级夹具；未为本片全绿而修历史测试或放宽产品守卫。3个原文件test_assistant_library_schema.py、test_weixin_generation_schema.py、test_weixin_provenance_schema.py保留不变。当前扩展组仍FAIL，不能被其他通过组覆盖。运行依赖清单缺失、Windows/安装发布与生产验收也继续开放。

## 复现

仓库根使用/tmp/qx-audit-20261024-venv/bin/python，PYTHONPATH=src；pytest指定全新/private/tmp专用basetemp，桌面设置TMPDIR=/private/tmp。

```sh
python -m pytest tests/integration/test_followup_worksheet.py -q
python -m pytest tests/integration/test_followup_schema.py -q
python -m pytest tests/integration/test_followup_schema.py tests/integration/test_evidence_schema.py tests/integration/test_storage_schema_versions.py tests/integration/test_weixin_generation_dispatch_schema.py tests/integration/test_weixin_generation_dispatch_integrity.py tests/integration/test_weixin_generation_ingress.py tests/integration/test_weixin_generation_integrity.py tests/integration/test_task_drafts.py -q
node --test scripts/test_followup_worksheet.mjs
node --test scripts/test_assistant_*.mjs scripts/test_reception_worksheet.mjs scripts/test_evidence_worksheet.mjs scripts/test_followup_worksheet.mjs
TMPDIR=/private/tmp node --test desktop/tests/*.test.cjs
```

18模块关联及扩展历史完整命令列在commands.json。独立HTTP探针运行时增加PYTHONPATH=src:tests/integration；独立final Node探针用node --test运行。browser_server.py创建全新合成工作区、18772本机服务；browser_check.cjs读取指针完整操作，仅含虚构测试账户与本机Chrome/Playwright路径。所有原件/工作区留在临时目录，没有复制到证据目录。

实施分工：schema/兼容及前端独立并行，主执行者核源码、后端、集成、实际浏览器、结果和基线；另有独立审查者（见independent-review.md）。baseline-preservation.json列原文件保留范围，source-sha256.json固定最终源码。既有测试原始日志保留格式空白。提交前记录中的本地状态由后续Git提交和远端同步结果接续。
