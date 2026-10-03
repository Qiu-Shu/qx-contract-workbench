# 离线工程评测与待批准法律评测

来源：实施规格 v2.0 §14、§14.1、T11。固定套件为 `tests/acceptance/cases.json`，84项对应44项V1、24项AUD和16项NEW；原始编号、场景、预期、来源和责任任务由服务器登记表逐项核对。生产完成、法律样本验收与本机mock工程执行分别记录。

## 固定执行入口

`src/cn_contract/acceptance/definitions.py`登记固定测试节点；数据里的entrypoint只作登记键，不能选择shell、eval或任意导入。套件和独立虚构manifest要求固定路径及原始字节hash；客户端自填PASS、换预期、换来源、换文件或漏项均被拒绝。40份材料及16个交易家族框架逐份核对hash、派生正文、家族分区、唯一物理文件和来源。只使用已核字节快照读取DOCX；损坏文件受控拒绝。

每次实际执行保存argv、退出码、起止UTC、JUnit和日志hash，以及所登记测试、代码、helpers、原始五份fixture、40份新材料、家族框架、配置、来源与依赖锁及明确local字段声明的仓内缓存证据hash。服务器固定pytest插件额外保存本次原生collection参数nodeid全集JSON/hash；每个完整函数只有其全部参数出现在具名JUnit执行记录且通过才可PASS。pytest中途exit0/1也不能把已执行一个参数当整函数通过；普通assertion exit1中其他充分执行的节点可以分别通过。无身份纯元数据不加PASS，无classname但含error/failure/skipped的原生记录仍如实统计。运行生成的pyc和__pycache__不作为源输入，上游相对README等文件名不能偶然绑定本项目同名文件。前后hash相同只说明所列输入在该次执行期间稳定，不能替代OS网络隔离或生产批准。

## 能力、部分断言与guard分别计分

六种状态完整列出并合计84：PASS、FAIL、NOT_RUN、NOT_IMPLEMENTED、NOT_SUPPORTED、BLOCKED。能力行仅在完整原预期已有登记断言且实际执行通过时PASS；遗漏节点、未执行或输入漂移不能证实通过。部分已有功能和正确安全降级另有partial_status、guard_status及实际节点，不把guard通过转成未实现能力通过。

当前可完整运行的工程能力登记为V1-D07危险解包拒绝、V1-Q08未知扣费保持与不重发、V1-Q09并发原子预留、NEW-01四类自有schema、NEW-14有界结构修复。其他行依实际缺口保留状态。OCR、复杂表格自动修订、完整patch语义重审、QCC报告消费者、全部法律场景和100积分月封顶语义均不能借已有guard称完成。原始规格要求拒绝不安全输入的行可以用实际拒绝断言通过；混合了缺失能力的行须继续报告缺口。

cases里的fixture是固定catalog参考材料；部分危险文件、MCP、并发和预算断言另由已登记测试生成专用独立虚构输入。材料正文中的情景说明不是实际扫描、缺页、宏或付费发送证据。报告同时列catalog引用、实际执行节点及限制。

## 40份工程材料的独立分母

新材料为短工程片段：四类各8份常规材料，加8份边界片段。按实际交易框架划分16个家族，完整家族分为开发24份、预留盲测16份；不能通过改金额、姓名或family名字把同框架分到两边。作者已经看到全部材料，因此预留分区不是独立律师盲测。边界片段的文字描述不能替代对应技术文件或真实场景。

实际sampler独立调用T02–T06建案、原件入库、解析、候选事实、人工模拟确认、18维mock审查和持久attempt/raw usage；每份保存受保护数据库记录及结果JSON/hash。samples_reviewed只数实际存在run_id的材料，未执行为0。类型、家族和分区计数是固定材料库存分母；工程结果另列每份PASS、FAIL或NOT_SUPPORTED和unsupported_parts。40材料的工程运行不提升84行的缺失能力状态。T06原四DOCX和provenance保持原bytes；web/demo仍只接受原四个登记虚构hash。

## 法律与上线门

目前缺少两名真实律师的金标准，gold.status=pending、两reviewer=null、disagreements=pending。法律正确率、重大问题召回率、意见精确率、原文锚点正确率、实际服务费用和人工复核用时均保持null/unknown，不用mock或作者自评填入成绩。95%、85%、99%是待批准目标，尚无实测分子、分母或统计外推。

编造法源、跨案泄漏、未经批准真实外传、超预算绕过、错位自动修改、未经批准签发是零容忍硬门；对应能力、partial或guard任何一次FAIL均NO_GO，不以平均分覆盖。缺能力、许可、地域、规则、数据政策、provider或真实律师批准时仍BLOCKED；离线mock不会获得GO或生产签发。

离线测试只访问独立localhost模拟SDK，实际QCC和真实模型请求为0，不付费、不上传真实材料。approved_model/live_guarded缺批准时先阻断零请求，不能凭两个模型名称默认跨供应商复制合同。浏览器旅程、Word视觉和完整网络捕获不是本评测产物；沿用的T10证据有各自来源和限制。

## 命令与制品

```powershell
.\.venv\Scripts\python.exe -X utf8 -m cn_contract.cli evaluate --suite tests/acceptance/cases.json --offline --output .local/evaluation-new.json
```

Linux已重建获准依赖环境后，使用 `.venv/bin/python -X utf8 -m cn_contract.cli evaluate --suite tests/acceptance/cases.json --offline --output .local/evaluation-new.json`。输出必须为本项目新JSON文件，不能覆盖旧证据。当前未满足全部能力和法律批准，实际生成报告后退出码仍为1；这是受阻验收结果，不是安装或运行成功替代上线批准。遗漏offline或使用非登记套件返回受控失败且不生成评测制品。最终实际结果与命令记录见 `docs/testing/T11.md` 和父节点的CLI/全套证据。
