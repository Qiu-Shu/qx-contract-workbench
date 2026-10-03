# T09 父节点实际验收

状态：ENGINEERING_PASS / BLOCKED_LIVE / PRODUCTION_BLOCKED。独立虚构数据，QCC与真实模型0；不外传、付费、接受条款或启用正式签发。沿已有代码增量实现，业务DTO/schema/defaults不改。

|实际命令或检查|exit|实际结果|
|---|---:|---|
|`.venv/Scripts/python.exe -X utf8 -m pytest --junitxml=docs/testing/T09-results.xml -q`|0|646 passed，0警告，173.18秒；JUnit failures/errors/skipped均0|
|`python scripts/verify_defaults.py --file config/defaults.json`|0|canonical仍0e4acba46c67b731cd9662d7b118217ddc55047ab69315961c7f78dfcfa9c887|
|`python -m cn_contract.cli schema --check`|0|唯一ReviewRun与保存schema一致|
|`python -m pip check`|0|No broken requirements found|
|`python scripts/verify_sources.py --mode development`|0|13来源、errors=[]，保留13生产批准警告|
|`python scripts/verify_sources.py --mode release`|1|G04/G06/G08/G10/G13生产批准缺失，G06/G08/G10/G13依赖使用范围待审，共9个实际阻断|
|`git diff --check`|0|仅普通pyproject的CRLF→LF提示；原始来源/锁/fixture禁止转换|
|实际Word与Poppler六轮|0|三报告及内部修订+Accept/Reject，十页实际打开检查；Word实际全文/另存XML各五段exact，重复句未改，原件/候选不变|
|`Get-Process -Name WINWORD`末尾只读核对|0|进程数0，无自建残留|

原始父节点结果：`.audit-local/t09-parent-checks.json`。Word/原始副本/图像及封证见[T09-word-visual.md](T09-word-visual.md)；原生结果不是XML结构oracle。最新制品绑定作者75文件冻结，SHA909fc8fd9a909f9a60689741ebb3fad5df15526807db1ed310cc58149fba67f8；Word验收后75/75仍一致，六輪十页封证SHA60540bd5c98f2ce3619bf8b3b09cb941255622648ff3b5a971c9a652fd4ac07d。

作者37目标/192关联回归通过；同冻结独立37目标、61探针、136必要关联回归全部exit0、0警告/失败/错误/跳过，75原文件及五固定fixture前后不变。正式RED与辅助错误分别记录；partial文件、当前复核资格、junction路径、人工项绑定、独立读取撤销、审计和双文件锚点归属均实际失败后原probe复验闭合。详见[T09.md](T09.md)、[独立审阅](T09-review.md)，不存在已知未闭合P1/P2。

依赖独立核验正式53 wheel/95主许可/78边、3423安装RECORD、旧51完整records及build1/17保留；实际环境69，仅新增python-docx1.2.0，lxml6.1.3原为开发依赖。36正式依赖冻结和3823输入hash无漂移，主许可闭包不是整个原生供应链或生产批准，见[T09-dependencies](../reuse/T09-dependencies.md)和[独立依赖审阅](T09-dependency-review.md)。Jinja/MarkupSafe仍未安装；未来55候选不能覆盖当前53完整记录，实际只读核对见[T10-current-pre-adoption](T10-current-pre-adoption.md)。

内部原生正文修改支持完整普通段落exact跨run。复杂对象、表格、字段、书签、目标旧修订/隐藏对象等人工；客户/对方原件包未经全部对外范围验证，只提供新草案和同项人工表。mock批准门实际BLOCKED_LIVE，无formal正例、真实例外授权或真实律师验收。QCC收据报告消费者、全合同补丁后法律/数值语义重审未实现，不将安全拒绝或局部结构支持称完整业务验收。四类T06 CLI已完成并保留，本阶段不重复运行、不重做T00–T08。

提交前 `.audit-local/t09_parent_stage.py` 实际exit0：作者75、正式依赖36、独立业务35、独立依赖19与后续静态12封证均匹配；57明确暂存路径、245受保护索引原始字节、五固定fixture与646项JUnit、Word六轮十页一致。正式53包锁raw SHA59107995ac98235004e189b36187e095425dd2754dce9a522cb54161fb56701c。普通工程文本CRLF→LF提示不触及原始来源、锁或fixture；来源保留RST分隔符等原字节，工程cached检查明确排除raw sources且逐blob核验。没有失败检查后提交。

独立业务doc SHA044bc4366ee2e287b1e156bc807cd100a13b4d875e3f2923d8df843bdc450c69，35证据freeze SHA16c2ef8ec0a872b6e23ee707caa1ef91a72789e0adba329f2c11a68179e81dee；三个最终运行JSON SHAba2420312dc4276a6de1a2b16a9cefe420d06469fdfa7a912c4c79182df95b78。此为当轮本机原始证据字节，普通Git工程文本按LF存储，不声称所有工程doc的Git blob与CRLF证据hash相同。
