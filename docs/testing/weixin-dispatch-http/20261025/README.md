# D2g5e — 根对话固定消息分发与找回（2026-10-25）

基线`02e7e32a7d16c583d20d02396c6dc08cc348b65d`，Windows实际仓库D:/Documents/ChatGPT/律所项目，沿codex/contract-review-v2。只有本机合成收件HTTP接线，不代表真实微信已接通。

## 源码已实现

根CID下新增POST `weixin-authorization/dispatches`（body仅descriptor_id）及GET `dispatches/by-descriptor/{descriptor_id}`。沿既有登录/同源/CSRF/严格有界JSON，先核当前根权限再读body，读取后再核；最终BEGIN IMMEDIATE内再次解析CID并强制descriptor.mapping_id等于该root。目标CID不反解根。**已绑定root**下未知/其他peer/account描述403；无mapping的CID查询返回null、写409；已知pending查询null且零业务写。

复用固定分发的当前root/历史target ACL、native19、撤权/fence/归档、逐流earliest与CAS及完整父链；旧Python公开签名和旧guard不变。晚到gen1消息不会流入gen2；后代目标失权不剥夺原固定回执权限。恢复/逻辑撤权/会话归档可按当前对象权限只查，新写和重放仍阻断。精确lowercase UUID GET加入既有恢复白名单，不扩到POST、尾斜线、列表或任意子路径。

集中新增两个DTO。9字段响应只含synthetic/recorded、descriptor/conversation/task-event ID、前后task cursor、UTC与完整回执的不透明digest；不输出account/mapping/binding/actor/bot/peer/session/source正文/理由或raw plan。投影在提交前构造，失败与任务事件/游标/回执同事务回滚。丢ACK只精确GET；不自动分发、冻结、执行审查或创建模型任务。

## 本轮实际验证与已有测试

[机器回执](verification-summary.json)保留argv、UTC、退出码、完整不同node ID与输入摘要。**7短组23模块701不同Python全部PASS，含64新增（服务/DTO18、HTTP46）**，0FAIL/ERROR/SKIP；是本轮关联范围，不是历史累计或单次全仓。

| 根最终组 | 不同Python | 结果 |
|---|---:|---|
| final-services-complete | 64 | PASS |
| final-dispatch | 75 | PASS |
| final-http | 87 | PASS |
| final-history | 129 | PASS |
| final-backup | 14 | PASS |
| final-integrity | 169 | PASS |
| final-schema | 163 | PASS |

四开发门exit0；来源13个NOT_PRODUCTION_APPROVED、native_build_verified=false保持。独立HTTP探针另5PASS，不累计入701/64。现有真实两代合成qxbak等由关联模块运行；新HTTP恢复用实际fenced app重建验证精确GET与拒POST，不声称新增的HTTP测试本身执行了qxbak。无浏览器/Node/Electron/安装版运行。

新入口已验晚代际分流、同owner其他peer/account/目标CID拒绝、当前root/固定目标ACL与latest不替代、首后scope/revoke校验、严格body、顺序/重放、实际commit后丢ACK只查、恢复白名单、投影失败回滚以及零run/model/execution。

所有产品输入跨最终组为同一当前SHA，各组before=after。一个**未被旧组执行或导入的新HTTP测试模块**在旧组结束后修正setup/peer准备及root拒绝审计oracle：必须先bind peer再创建generation；拒绝请求保留恰1条核验后的审计，所有业务表仍不变。完整64新用例在修正后重跑。[快照证明](test-fixture-snapshot-proof.json)与旧源码副本列出三函数和新增hashlib/json标准库imports，其余顶层AST相同，外部模块引用0及各组精确未使用摘要差异明确列出；不称全部测试树在所有组都同一全局SHA。

## 失败历史与独立审查

根首次RED7FAIL（缺CID入口断言，不能当7种行为各自RED）；HTTP首次3FAIL/39deselected（404/缺恢复predicate）。中间HTTP guard为10PASS/2FAIL/30deselected，两FAIL当时缺conversation wrapper，不当最终验收。首次合并组61PASS/3FAIL期间HTTP测试源码发生变化，明确废弃其最终快照资格；原日志/XML保留。1项peer夹具在已有generation账号上再bind触发现有正确guard；2项此前以owner破坏历史不变量的ACL夹具改为既有projected-case ACL损伤。未为这些准备错误改产品或放宽断言，最终完整64重新执行。

中间稳定重跑63PASS/1FAIL发现root ACL拒绝经既有security.deny单独提交不可覆盖审计，原“全库完全零写”oracle不正确。只改测试为旧审计prefix逐字节相同、恰1条新增，核action/actor/correlation/实体/None哈希及reason_sha256（无明文reason），所有其他表不变；fixed/later分支仍全状态相同。产品SHA未改，失败日志和此前测试字节保留。

随后61PASS/3FAIL由测试新增局部payload遮蔽原helper引起，独审独立指出后只更名audit_payload。定向3PASS/43deselected后再完整64PASS；定向3已包含于64/701，不重复累计。[测试修正独审](test-correction-review.md)核实peer与审计oracle及未用模块范围，保留全部失败原日志，未把夹具失误当产品RED或漏报失败。

[整体独审](independent-review.md)为未写四产品的同一审查者Spec/Standards双轴0确认问题，另有5项独立FastAPI/TestClient HTTP探针，不声称独立TCP/浏览器验收；不冒称两个独立整体审查者。[交叉独审](http-author-cross-review.md)由HTTP作者检查root三产品，明确排除自己的HTTP实现/测试。[peer夹具说明](peer-fixture-review.md)是作者说明，不冒充独立审阅。

## 尚未实现及NOT_RUN

此片无新UI、pending列表、raw preview、transport/下载解密/外发或可信微信绑定。微信pending附件目前无attachment_id，现有页面尚不能选择另行上传的原件；后端显式resolution及DOCX/PDF桥可后续复用。可信身份/账号资格/数据政策及E有限期模型授权仍待。

真实微信/合同/产品模型/付费、全仓长单进程、Node、浏览器/Electron/安装版0.4.1均NOT_RUN；0.4.1未更新，WIN-PATH-02/原生AV仍OPEN。WorkBuddy本轮NOT_RUN，未采用产出。GitHub后续按实际回执，用户AGENTS保持未暂存。HumanLayer旧pending因Windows argv限长待同步，收尾结果按实际回执；Obsidian成功才称已保存，TencentDB沿正常Stop。

最终[证据独审](final-evidence-review.md)独立复算701/64、48对发布字节、566输入与唯一未用测试摘要例外，0确认问题；未重跑测试，后续Git同步回执不在该快照内。
