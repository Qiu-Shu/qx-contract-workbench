# D2g5c — schema18专用合成代际收件（2026-10-25）

基线`421ffa5abf464c8e8c89a49ab02f7afa19246d8c`；实际Windows仓库D:/Documents/ChatGPT/律所项目。本片提供专用Python合成服务，不是微信登录、轮询或桌面收件开关。所有材料独立虚构。

## 源码已实现

[新服务generation_ingress.py](../../../../src/cn_contract/weixin_inbox/generation_ingress.py)：80行record_generation_poll、95行find_generation_poll_receipt复用既有WeixinPollInput/Receipt。写入口严格要求native schema18、实际principal/account owner/workspace、已有代际、非撤销及非恢复；没有新增DTO/schema/依赖/HTTP/UI/transport。其他peer在同账号内仍按零代mapping/grant解释。

[accounts.py](../../../../src/cn_contract/weixin_inbox/accounts.py)：63行旧_mapping_reason的全账号暂停不变，82行提取纯_scope_reason，核精确synthetic binding、实际owner/workspace、当前案件成员/案件归档/接待归属及转案投影。新写还核root归档、当前实际目标完整scope；root旧版本不将新目标锁回旧scope。逐条拒绝只形成blocked描述，不调用会rollback+独立commit审计的高层authorize，锁和整批快照保持。

[ingress.py](../../../../src/cn_contract/weixin_inbox/ingress.py)：184行提取事务内_record_poll，保留raw上限/严格JSON/逐条完整描述/全局来源去重/不可变receipt/账号checkpoint CAS。private generation_aware默认false，仅专用入口固定传true。新接受的原始非零代描述与7字段sidecar同事务写入；blocked/duplicate/零代均无sidecar。源event namespace不加代号。after=True严格排在全账号活动之后，同钟/回拨也不与generation相等。

提交前完整provenance及父链复验；正向跨代reply、旧unknown reply因新消息而跨代变known，均整poll VERSION_CONFLICT回滚，原游标不推进、旧目标不改派。该明确保守策略可能阻断该批进度，须调用方人工处理冲突，不能据此自动重发或静默丢弃某条消息。

新固定query/精确重放按sidecar固定历史目标核当前root及该目标权限，不转去后来无关目标。恢复/逻辑撤销/会话归档可查已存回执，当前案件撤权/案件归档/接待归属仍拒绝。未知请求只查不写。旧record_synthetic_poll、binding/refresh及dispatch仍受原暂停guard；现v18存档继续拒绝非零代实际dispatch，没有创建TaskDraft或启动模型。

## 本轮实际验证与已有测试

[机器回执](verification-summary.json)记录九个关联短组、每组完整argv/UTC起止/退出码/前后SHA及全部不同case ID。本轮34模块、886个不同Python全部PASS，0FAIL/ERROR/SKIP；52新增已包含，既有24/37/15重复不叠加，不是历史累计或全仓单进程。15既有脚本233Node与四开发门全部exit0。83份源码/测试/合成helper/冻结fixture/脚本输入摘要跨组一致。

| 根最终组 | 不同Python | 结果 |
|---|---:|---|
| final-new | 52 | PASS |
| final-legacy | 110 | PASS |
| final-targets | 101 | PASS |
| final-preview | 68 | PASS |
| final-provenance | 106 | PASS |
| final-dispatch | 38 | PASS |
| final-integrity | 226 | PASS |
| final-routes | 87 | PASS |
| final-task | 98 | PASS |

52新增由[根服务测试37](../../../../tests/integration/test_weixin_generation_ingress.py)和[独立原子性测试15](../../../../tests/integration/test_weixin_generation_ingress_atomic.py)构成。实际覆盖两代公开服务收件/固定sidecar、混合accepted/blocked/duplicate及零代peer、pending DOCX、同钟/回拨、严格schema17拒绝/旧guard、请求与raw精确重放、正反跨代reply、当前root/目标案件和接待投影、固定查询恢复/撤权/归档。

独立15实跑还覆盖真正SQL sidecar/checkpoint/precommit故障全回滚，实际commit后丢ACK只查询、不同/相同请求线程CAS、poll与append竞争、全新Python进程，以及带独立合成DOCX的真实qxbak恢复。原源文件字节不变；恢复旧session401，重新login可按固定来源查询，所有新写/重放仍BLOCKED_LIVE，既有enable/egress位false。没有用SQL seed替代本片新入口的运行验收。

[Spec](spec-review.md)与[Standards](standards-review.md)由两名不同独立代理分别完成，均0确认遗留；[源摘要及说明](review.md)。Standards代理编写并执行独立atomic测试，未写产品；Spec代理只读证据，测试NOT_RUN。两者未重复根大组回归，不据此称全仓或生产通过。

## 失败与证据边界

根最初1collection ERROR是RestoreFenceRow导入位置写错，先纠正测试导入；正式RED24FAIL/0error为专用模块缺失，随后24PASS；补充当前ACL/严格封装/重放13例后37PASS。独立focused RED1FAIL/0error，完整15最终PASS。源前后hash未在这两次RED捕获，标记NOT_CAPTURED；最终关联组已逐份冻结。原始失败XML/log和时间保留，不能把collection错误算成缺实现的证明，也不能将初始24再加到37。

证据发布统一UTF-8 LF，log/XML只去pytest行尾空白；本机raw捕获保留，captured与published摘要分开。四开发门仍包含来源NOT_PRODUCTION_APPROVED提示、native_build_verified=false，exit0不代表法律/生产批准。

## 未实现与NOT_RUN

下一片为按固定代际执行实际合成分发及相应独立版本化来源校验，再推进官方微信可信身份/账户资格/数据政策与E有限期模型许可。当前仅专用合成收件服务；桌面原授权页仍是历史记录操作，没有新增自动poll/下载解密/消息外发。

全仓单进程、浏览器/Electron/安装版0.4.1、WorkBuddy本轮、真实微信登录/轮询/下载/发送、真实合同/产品模型/付费调用均NOT_RUN。没有安装机器人、连接账号、签发意见或自动对外发送。既有WIN-PATH-02目录rename WinError5及原生长进程AV保持OPEN；上轮SQLite路径修复不因本片扩大成所有长路径支持。

GitHub正常提交推送后附回执；用户AGENTS保持未暂存。HumanLayer/Obsidian按本轮独立回执收尾，TencentDB沿正常Stop自动提炼，不预报未发生的保存成功。
