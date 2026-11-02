# 合同同名公司立场续办：工程前置

2026-11-02，本片从新材料内容复核的预检转为立场来源修复，现已完成本机合成工程验证；收口时新实验尚未初始化、冻结请求或生成原答。工作树仍沿codex/contract-review-v2；新方法名contract-review-v3与Git分支名无关。

当前“我代表乙方某公司（供应方）”可由本次用户引文确立角色。“仍代表同名公司”须同时引用本次延续指令和一条有效的历史用户公司/角色声明。历史来源从同一任务、固定作用域、当前版本与时点之前的已接受业务记录重建，包括没有模型成果的声明或撤回。模型回答和合同文字不能确立我方角色；缺少来源、冲突或无法解析的本人声明保持unknown。

最新撤回、换公司、角色冲突或相关不明确声明清除旧推断。没有绑定任务的相关声明只会保守停止同作用域推断，不给任何任务新增角色；明确其他任务和新任务保持隔离。即使本次没有历史来源，也从账本重建校验，防止删掉来源后绕过检查。旧v1/v2提示词、角色校验和去重渲染固定，既有64KiB合同历史和262144字节完整封装上限不变。

证据根：`.audit-local/contract-followup-recheck-20261102/`。以下均为本机虚构材料与loopback；不是实际模型法律质量或采用验收。

| 实际检查 | 结果 |
| --- | --- |
| 首次合法candidate RED | 3项CONTRACT_STANCE_INVALID，exit1；stance-core-red.log/xml。DTO和引文已合法，不把schema错误算缺陷 |
| 真实业务账本RED | 新模块缺失1失败；后续发现纯条款供应方描述误清空、未绑定撤回漏清空，失败与修复日志均保留 |
| 独审当前冲突RED | 普通无括号公司变更、空白/已经撤回4失败1通过，修复后54相关项通过；stance-review-red/green.* |
| 时间前缀与未解析自身声明RED | 现在/目前/本次/暂时角色或公司变化共9失败5通过；修复后63相关项通过，stance-temporal-red/green.* |
| WorkBuddy首轮反例 | 10项中9失败1通过，修复后77单元通过；stance-wb-red/green.* |
| 意见、中立及引述反例 | 16项中7失败9通过，修复后137目标通过；stance-wb-second-red.*、stance-precision.* |
| 插入语反例 | 12项中3失败9通过，修复后143目标通过；stance-insert-red/green.* |
| 代理人等名词反例 | 11项中4失败7通过，最后修复后91相关单元通过；stance-nouns-red/green.* |
| 最终固定源码关联 | 316个不同后端用例、18文件，0失败/错误/跳过，exit0；源码及测试运行前后hash一致。stance-frozen-command.json记录完整命令与源码hash，stance-frozen.log/xml/json/exit.txt记录实际结果 |
| 桌面/页面 | 528通过、exit0，stance-desktop-final.log；首次527通过1失败为旧未知版本测试仍把v3当非法，已同步v4反例并保留原失败日志 |
| 四开发门 | 最后源码下schema/defaults/sources/dependencies分别exit0，stance-frozen-gates.json及四日志记录实际命令 |
| 中间回归保留 | 177、288各通过；302项pytest通过但运行期间补入独审反例，源码稳定性检查失败、外层exit1，不能算最终固定源码通过。原日志、stance-final-interim-note.json保留；已由最后316项取代 |
| 独立旧证据回放 | 独立作者脚本核对20旧请求、8旧完整成果，另旧v2首轮request/response/result重建一致；32个源证据hash保持。Codex在最后源码复跑exit0，review/legacy-replay-frozen.json；初始独立记录未覆盖 |

合法集成通过两轮单次loopback、同任务新增附件、完整历史、当前与历史双引文、首份output_json不变、2attempt/2output、Word导出和加密备份恢复回读。两种伪来源（省略有效见证、撤回后强塞旧见证）均在归档校验被拒，并在发送前failed_before_send/not_sent，网络发送0次，重复执行不重发。reserved读取仅展示原态，不为此次变更扩大通用read接口语义。

WorkBuddy桌面适配任务wb-bg-1d4afa14ba43已completed，桥接实际deepseek-v4.1-flash、model_verified=true；原回执workbuddy-v3-desktop.json保存。源码四轮任务wb-bg-48cf10ea283f、wb-bg-7988bdec805b、wb-bg-033b0253f38c、wb-bg-d35e2135723e也均completed并实核Flash。独审实际是只读源码推演，没有代跑测试；其列举反例由Codex逐项RED/GREEN闭环，末轮名词误判的最后增量由Codex复核及最终316项验证，不冒称独立审阅者已读最终增量或独审零发现。原始回执及处置见review/closure-triage.md。原Codex独审因子代理额度中断，其已完成的旧回放/问题记录仍保留。

本片基线7102个已有文件无丢失，130份前片证据hash不变；暂存补丁SHA-256仍为5336578af1b1c146d7365e990ebe40deb38783bbbfa71a0baba48c22e736a335。新材料作者原稿和三份正文、两个问题保留；九处评分预期在冻结前按原文纠偏，实验使用全文非盲评，不删除模型实质内容。见preflight-review.md和stance-integrity-before-freeze.json。

下一步按[新材料计划](../../../plans/2026-11-02-contract-followup-recheck.md)冻结C4-v3内容实验。新实验在任何原答前将生成方改为两个隔离WorkBuddy Flash会话，Codex主评，Flash评分另起会话；同模型相关性、非盲限制与实际生成Token/费用未知均保留，工作台只用loopback测试账本。生成回执检查1有效/7字段错误/3歧义格式反例通过，见generation-preflight.log/exit.txt。

v3本片首次引入且未部署，不存在已发生的生产v3存档升级；现在冻结角色解析、来源选择和渲染语义，今后语义改动另起方法版本。有限自然语言识别不支持任意公司别名或所有表达；复杂他人角色叙述和介词“为”等可能要求明确角色，不据此作法律身份或业务权限判断。工程通过不证明内容质量或采用验收。未提交、推送、安装、调用工作台真实模型/QCC/微信或签发外发，伙伴接口仍待办。
