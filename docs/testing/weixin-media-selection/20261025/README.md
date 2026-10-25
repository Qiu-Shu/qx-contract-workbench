# D2g5f — 待收件文件明确关联已上传原件（2026-10-25）

沿`codex/contract-review-v2`，基线49e7b55。微信离线FILE没有attachment_id时，桌面现在可明确选择本对话已上传并完整读取的DOCX/PDF，保存既有media resolution；真实微信仍未接通。

## 源码已实现

仅修改assistant-tasks.mjs，复用原TaskMediaResolutionInput/PATCH、材料和精确parse接口，无后端产品/DTO/schema/依赖变更。缺原始attachment_id的材料行显示有label的原生选择框，默认空，不按同名匹配；明确按钮提交。同CID候选仅DOCX/PDF；元数据、SHA、parse revision从当前真实响应构造，继续由原后端核权限/原件/解析/版本/fence。未完整读或parser/baseline不符不ready；原收件media_id/event及原件不覆盖。已有resolution的更新按replacement.attachment_id读取，允许再次明确改选。

CID/epoch、当前task/revision、材料快照、选择及loading在await后核对；材料更新清选择，尚未提交的选择进入导航保护，readonly/frozen/busy/dispose/撤权守卫保留。同CID过期父页面通知不能回退较新的直接GET材料快照。新关联丢ACK只精确GET task，以expected_revision+1和完整resolution字段匹配，不重PATCH，不凭latest状态猜成功。保存成功与后续列表刷新失败分开告知。

## 本轮实际验证与已有测试

[机器总表](verification-summary.json)保留不同测试ID、argv、UTC/退出码、完整输入SHA和失败。根4短组11个Python模块共**237个不同用例：236 PASS / 1 FAIL**，含新增HTTP22；并非全仓全绿。失败是既有WIN-PATH-02自然再现，不累加作者22或重复测试次数。全部assistant Node脚本**293 PASS**，含新增60；独立2探针另计。四开发门exit0，来源13个NOT_PRODUCTION_APPROVED、native_build_verified=false保留。

| 根组 | 不同Python | 实际结果 | 退出码 |
|---|---:|---|---:|
| final-http | 47 | 47 PASS / 0 FAIL | 0 |
| final-core | 67 | 67 PASS / 0 FAIL | 0 |
| final-recovery | 76 | 75 PASS / 1 FAIL | 1 |
| final-weixin | 47 | 47 PASS / 0 FAIL | 0 |

HTTP22验证已有后端合同，不是新增前端功能RED：同CID实际上传/读取/关联DOCX/PDF、伪造7类引用/外CID/晚项回滚、陈旧CAS/冻结/暂停/取消、CSRF/同源/身份、body后当前案件权限、同一app内持久fence的HTTP写入隔离、partial PDF仍阻冻结。恢复HTTP22中的fence不是app重建或新执行qxbak；根备份关联模块另实际执行合成qxbak。

[浏览器结果](browser-report.json)使用原生初始化的隔离合成workspace和真实loopback FastAPI/Chromium；实际离线代际收件→分发产生2个无attachment_id的pending任务，登记DOCX/PDF上传→完整读取→空默认选择→键盘明确关联→刷新保留。PDF提交后真实commit、丢ACK、精确target route实测恰`PATCH → GET`，DOCX恰`PATCH`；原件GET前后均200且bytes等于源样本，原收件全行不变。2 generations/2 dispatch receipts/2 resolutions，task execution/assistant run/model attempt/review run均0，外网请求/页面错误0。

1280/360两视口中文长文件名无横向溢出，原生select有label、键盘和可见focus；[宽屏](browser-selection-1280.png)、[窄屏](browser-selection-360.png)。一次批量目视检查，保留现有浅色中文系统字体/密度，未加CSS/联网字体/动画；Impeccable手动detect为[]。browser-03首次通过后仅补强方法trace/原件字节验收，browser-04最终通过，产品视觉未改。

每个根组自身before=after；全部产品、测试及fixture摘要与最终一致。唯一历史快照差异为未被Python/Node组执行或导入的独立浏览器脚本，从browser-03后补强GET trace及原件字节断言；差异逐组列入总表，最终脚本由browser-04实跑，不冒称所有组全部输入始终同一SHA。

## 失败历史与独立复核

作者有效初始RED为54 FAIL（缺选择框，非语法/导入错误）。首次实现54新+21旧=75 PASS；材料GET更新不清选择的回归55 PASS/1 FAIL后修复，56新+21旧=77 PASS。独审[原探针](independent-media-review-probe.mjs)独立发现MEDIA-FRAME-ROLLBACK：新材料rev2被父页面旧rev1回退，正式探针1 PASS/1 FAIL；初探针fixture误触另一提前guard已另存且不作正式RED。作者增加3个回退参数回归和1个非回退例，57 PASS/3 FAIL；最小monotonic scope guard后60新+21旧=81 PASS。**原正式探针字节不变**复验2 PASS/0 FAIL；上述重复不累计入293。

[产品独审](independent-review.md)为未写前端者同一审查者Spec/Standards两轴，历史P2已复验关闭、0遗留；明确排除其本人HTTP22。[HTTP测试交叉独审](http-test-independent-review.md)由前端作者检查他人HTTP测试，0遗留、不重跑pytest、不审自身JS。[浏览器脚本独审](browser-independent-review.md)原发现验收未直接记GET的证据缺口，补trace/原件GET后按最终SHA关闭；只静态审阅和读回root报告，不冒称独立执行浏览器。

browser-01在原生凭据格式校验前失败（脚本用户名/口令长度不合要求），无成功浏览器/无输入快照，标NOT_CAPTURED；只修合成凭据。browser-02上传未登记assisted fixture遭正确DATA_POLICY_UNAPPROVED（mock_demo），改用既有select_fixture销售样本，不放宽产品登记策略；日志/失败报告保留。browser-03通过但当时只有PATCH计数，不把其lost_ack_query_only布尔本身当直接GET证明；browser-04补强后通过。

**仍有1项真实FAIL**：[final-recovery.log](final-recovery.log) / [XML](final-recovery.xml) 的`test_restore_blocks_each_pending_execution_and_all_task_writes[awaiting_facts]`，workspace_backup.py:380目录发布rename报WinError5。该Python产品与测试均未改，本片JS不被该测试执行；已知WIN-PATH-02继续OPEN，不修改保护、不跳过用例、不以再次偶然通过掩盖失败。其他75项本组通过不能关闭该缺陷，原生长进程AV也仍OPEN。

## 尚未实现及NOT_RUN

真实可信微信身份/账号资格、transport/下载解密、pending descriptor列表UI、E有限期模型许可仍待。无真实账号登录/机器人安装/合同外发/产品真实模型或付费、签发和自动外发。安装版0.4.1未更新；全仓长单进程、安装版Electron、真实微信/合同/模型/付费及WorkBuddy本轮NOT_RUN。开发链通过不等于生产/律师样本/真实试点批准。

产品`958b8e6`已正常推送，远端SHA/tree及5,761条目一致，[同步回执](github-sync.md)；用户AGENTS保持未暂存。HumanLayer旧pending限长待同步，收尾按实际回执；Obsidian成功才称已保存，TencentDB沿正常Stop。

最终[证据独审](final-evidence-review.md)独立复算237/236/1、293/60、63对拷贝及626输入，0遗留；新增两条精确.gitattributes规则仅保留测量字节和测试有意CRLF，不改产品运行配置。后续Git和记忆回执不在该审阅快照内。
