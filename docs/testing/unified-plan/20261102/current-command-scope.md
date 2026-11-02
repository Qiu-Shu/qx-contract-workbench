# 当前指令范围：隔离实现与验证

2026-11-02。本片在已附加隔离工作树 `C:/Users/Administrator/.codex/worktrees/trademark-command-scope/律所项目` 完成源码及本机合成工程验证，主仓产品源码未合入。最后固定代码402个后端、628桌面/页面及四开发门通过，旧请求/成果回放一致。最后增量由Codex复核，不称最终独审零发现；内容质量、采用、安装和生产仍是独立状态。

当前明确请求后面的条件补件安排不再吞掉前面的请求；条件前件与逗号/分号后的从属动作仍整体阻断。引号、URL、小数、日期和版本中的标点不释放条件，URL正文也不作为命令或条件词。当前入口按次序处理暂停、重启和否定；长否定不再受16/10字符窗口限制，后发“不做商标”能撤回原商标请求，引述“继续”不会借旧任务触发处理。新建任务也须是当前非否定指令，否定可覆盖显式new_task。普通引文不因新增续办词取消已明确的当前请求。前端镜像相同反例；controller仅fresh判断一行改用当前helper，发送与未知回执恢复及其余字节保持。

新增 `trademark-triage-v3`，domain与桌面白名单同步；Skill Registry既有委托入口自动使用新默认版本。v1/v2的system、选择、校验与渲染保持，旧辅助函数默认仍按legacy解释；没有新增表或迁移。新版本尚未产生正式内容实验原答，不把旧id语义静默改成新规则。

## 原始工程证据

证据均在隔离工作树 `.audit-local/current-command-scope-20261102/`；主仓仍保存前置原失败和原内容方案。测试仅用虚构材料和loopback，不使用工作台真实模型或微信。

| 检查 | 实际结果 |
| --- | --- |
| 当前范围RED | 32项，20失败12通过，exit1；scope-red.* |
| 引文标点RED | 6项，4失败2通过，exit1；quotes-red.* |
| 长否定与权利撤回RED | 11项，7失败4通过，exit1；denials-red.* |
| 独审四类反例RED | 小数/日期/URL、逗号/修饰暂停、引述继续、裸不/不予，共14项全失败，exit1；review-red.* |
| 定向修复 | 116项通过，exit0；review-green.*。随后38项新边界及实际业务入库通过，exit0；review-target.* |
| 最终固定源码后端 | 402个不同用例，0失败/错误/跳过，exit0；backend-closed.log/xml |
| 最终桌面及页面 | 628项通过，0失败/跳过，exit0；desktop-closed-bound.log |
| 四开发门 | schema/defaults/sources/dependencies分别exit0；*-closed.log |
| 商标旧版本回放 | 2份旧请求、成果和basis，48条旧选择结果一致，exit0；legacy-before.json、trademark-legacy-closed.log |
| 原内容证据回放 | 20份旧请求、8份完整旧成果及旧合同v2首轮一致；32个源证据摘要不变，exit0；old-experiment-closed-replay.json及old-experiment-closed.log。沿用独立作者脚本，Codex在本工作树运行，并非独审者代跑 |
| 最终源码稳定性 | 验证前后967份相关源码/测试摘要相同；closed-checks.json记录9条实际命令、退出码、导入路径和摘要。不是全仓测试或安装版验证 |
| 主仓保护 | 716份受保护文件及暂存保持，合同未补发；主仓.audit-local/trademark-followup-quality-20261102/integrity-current-scope-close.json |

实际链路沿用失败的完整首轮问题，经预览、排队、单次loopback、保存、回读，再补材料；同task、材料新增一份、历史首轮问答逐字一致、首份output_json不变、2attempt/2output。纯条件、暂停、引述和撤回即使带显式workflow及旧task也无法创建模型attempt。它是工程模拟，不是内容实验原答。

中间失败和中间通过均保留，不能与最终402项相加：最初两处版本测试仍将v3当非法/默认v2，158项中2失败156通过；同步未知版本反例和旧版矩阵后通过。一次新集成测试与单元文件同名造成1个收集错误、exit2，已更名；不是产品失败。192、155、360、390项均为较早源码的中间回归；360项对应final-checks.json，390项对应reviewed-checks.json，随后独审新增问题继续修正，以closed-checks.json的402项为最终证据。command-ledger.json保留此前pytest参数、退出码及原始证据位置。

依赖门最初缺少隔离目录未复制的公开缓存，exit1。首次限定缓存路径的复制脚本遇到锁定清单中sources/evidence路径而断言停止，该次脚本退出码未单独捕获，未计成功；对应依赖复查仍exit1。确认路径后仅复制/核对清单中的171份本机公开证据、45,856,671字节，56运行包及1构建包核验通过。未下载、未安装、未扫描私人资料或放宽依赖验证。gates.json、dependency-evidence-copy.json及失败日志保留。

## 独立审阅与范围

前端协作 `wb-bg-6e099cf0f457`、首次只读审阅 `wb-bg-1dc97657b9c8`、后续复审 `wb-bg-509e655334e3` 均completed，桥接actual为deepseek-v4.1-flash且model_verified=true；完整原回执已存。后两次是同一独立审阅会话的前后复核。前端建议中的引号问题已在其完成前修正；长否定与权利撤回经本机对照证实旧代码也存在，随后在当前入口补修。首次独审四类问题有14个实际RED；后续新增URL命令词、否定/引文新建任务、普通引文误拦，12项中9失败3通过、13未选，exit1，data-task-red.*保留。最后增量99项目标和124页面通过，由Codex复核，未再声称独立审阅者已看过最后修正或最终独审零发现；处置见review-disposition.md。

仍使用有限自然语言规则，“特别/分别”等含“别”的表达可能被保守拦截，未声称理解所有表达；该类误拦及前端既有刑事词表差异不属于本片新增授权能力。刑事方法、synthetic-only-v1及README边界保持，不生成刑事内容。主仓初始WIP对照：12个已有产品/测试文件改动、11个新增测试/夹具，旧文件未丢失；closure-final.json记录最终逐文件摘要及controller除fresh一行外字节一致。

## 内容阶段的明确变化

原v1/v2商标对照仍为预检失败，0/4原答、0/8评分，原问题未改；两旧方法继续无法选择原条件句问题，不能把v3修复写成旧实验恢复。下一片按[新协议](../../../plans/2026-11-02-trademark-v3-followup-content.md)做v3单一方法两轮补件内容验证：原材料和原问题保留，新证据目录与2原答/4评分分母独立，不比较方法优劣。协议、源码和输入须在生成前冻结；目前没有初始化、冻结请求或生成原答。

主仓仍不自动覆盖。合同补发保留等待已发出的用户确认；伙伴服务待办。未提交、推送、发布、安装、外发或签发。
