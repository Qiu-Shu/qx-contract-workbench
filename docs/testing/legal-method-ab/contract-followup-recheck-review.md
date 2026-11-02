# 新材料合同补件对照：输入传递失败保留

2026-11-02，contract-followup-02原计划C4与v3各两轮、4份原答、2对成果、8条双评。材料、两轮问题、评分协议及源码在生成前冻结；本轮没有取得任何原答，评分未运行，不能将缺失按0分解释。

两组各自独立WorkBuddy任务已终止：C4为wb-bg-fe24a309ec23，v3为wb-bg-3737c73ec03a；requested/actual均为deepseek-v4.1-flash，model_verified=true。桥接state=completed表示任务回执完整返回，答案明确说明未写response.json，不等于内容生成完成。两个原回执分别保存在本片各组round1/generator-receipt.json。

两份request.json里的user content均为嵌套的单行JSON字符串，最长行10,605/12,438字符。两组分别报告Read工具在约2000字符处截断，未读到完整问题和来源正文，故停止。独立只读核查两个SQLite均为0模型attempt、0output，response.json均不存在；第二轮未准备，未进入loopback。这是评测输入传递失败，不能据此给C4或v3的法律内容优劣打分。

原实验的frozen-inputs、两轮问题、源码摘要、数据库与失败回执保持。没有自动重发生成任务。当前分母为原答0/4、评分0/8；另有两条已收到的失败任务回执。证据根为`.audit-local/contract-followup-recheck-20261102/`，见delivery-failure.json、delivery-db-check.json和round1-dispatch-freeze.json。

恢复准备仅生成新的可读视图，不改原wire或产品方法：C4分2页、最长物理行275字符；v3分3页、最长物理行272字符；每页不超过12,000 UTF-8字节。长字符串以无损片段展示，user JSON展开，反向还原后两份request完全相等，包括system、question、来源及历史文本。最终候选见readable-ready/proof.json及各组index.json；旧readable-proposal保留，其行长统计含行末LF、多计1字符，页面内容与最终候选逐字一致。新辅助脚本scripts/workbuddy_input_view.py没有模型、网络或重试接口，拒绝覆盖现有输出。

实际最终单元及既有准备包关联34项通过，其中新增15项覆盖长历史/特殊字符、逐字引用偏移、分页重组、重复键/NaN、非规范JSON、标记碰撞、改动与重新封印后的替换检测，以及Unicode分行符不绕过物理行上限、行长元数据重算。独审后2反例先失败，修复后34项exit0，见input-view-review-red.*与input-view-final.*。最初新模块缺失导致收集错误1、exit2，这不是长行根因的证据；原生截断依据是上面两条任务回执。探针准备脚本第一次缺少项目根导入路径，exit1，修正后exit0，均保留日志。

非法律随机标记只读探针wb-bg-edeae38c30b1已completed，桥接实核Flash，3个跨片段标记全部与私有预期一致。它没有读取原合同或评分，没有生成合同内容、运行测试或改文件；原回执、严格边界提取核对与初始页封印见delivery-probe/receipt.json、validation.json和delivery-view-freeze.json。最后修复只改变行长统计口径和校验；原案候选页面字节未变。

独审五项建议中，Unicode物理行与行长元数据两项已实际RED/GREEN修复。其余取舍：失败时保留不可覆盖的半成品证据，未经verify成功不派发，暂不引入Windows原子rename/自动清理；纯restore函数不充当验证入口，调用者必须用持有原raw的verify_package确认身份，不用可同时篡改的索引自证来源；固定片段跨词是有意设计，已用三条跨片段随机标记实核拼接，暂不加语义拆词。索引只读取列举的固定页名，不消费目录额外文件。最后小增量由Codex验证，不冒称WorkBuddy代跑或复读最终源码。

可读恢复候选已经准备并验证。已向用户询问是否允许C4/v3各补发一次，原失败永久保留；尚未收到明确批准，因为已冻结规则禁止自动重试失败任务，批准前不重发，不把新尝试覆盖原失败。

2026-11-02T01:43Z收口检查：11份冻结输入、556份源码快照、6份派发记录、8份最终可读视图和8份失败回执相关封印均一致（不同清单有重叠，不累加为文件总数）。两组可读视图重新逐字还原通过；两个SQLite只读检查仍为0attempt/0output、检查前后摘要不变，无response.json及第二轮目录。7,102份原有文件无缺失，130份前片证据、暂存区、原材料和问题保持。完整性脚本及git diff --check均退出0，记录于delivery-close-result.json、delivery-close-integrity.json及delivery-close-check-*.log。34项既有最终测试记录已核对，本次没有重复执行测试或派发生成。自动化skill已回读确认保存“等待明确补发批准”的约束，其他自动化未动。
