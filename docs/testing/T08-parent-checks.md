# T08 父节点实际验收

状态：ENGINEERING_PASS / BLOCKED_LIVE / PRODUCTION_BLOCKED。仅独立虚构数据、模拟积分和本机合成MCP，真实外查/付费/材料外传0。沿T07代码增量实施，不重做已完成任务。

|实际命令或检查|退出码|实际结果|
|---|---:|---|
|`.venv/Scripts/python.exe -X utf8 -m pytest -q --tb=short --junitxml=docs/testing/T08-results.xml`|0|609 passed，0警告，128.10秒|
|作者冻结清单父节点SHA/bytes核对|0|12/12一致，清单SHA 39eb67deedee2380c4d365d9b68a9bca8f28f5d75978cc4d618b741e28339721|
|`scripts/verify_defaults.py --file config/defaults.json`|0|canonical hash仍0e4acba46c67b731cd9662d7b118217ddc55047ab69315961c7f78dfcfa9c887|
|`python -m cn_contract.cli schema --check`|0|与唯一ReviewRun模型一致，无domain/schema改动|
|`python -m pip check`|0|No broken requirements found，无本阶段新安装|
|`scripts/verify_sources.py --mode development`|0|13项errors=[]，13项生产批准警告保留|
|`scripts/verify_sources.py --mode release`|1|G06/G10/G13各DEPENDENCY_REVIEW_PENDING与PRODUCTION_APPROVAL_MISSING，共6个真实阻断|
|`git diff --check`|0|工程改动检查通过|

完整原始运行结果在`.audit-local/t08-parent-checks.json`。全套不是84项规格验收或法律准确率，未重复T06四案CLI/Word/UI。作者首批11项为真实功能断言RED；其最终52目标29.78秒、78关联17.75秒，均exit0。Factory直接调用绕过网关先真实RED，现必须消费持久化网关发送凭证。作者辅助文件名错误不算功能RED。

独立审阅在同冻结代码实际运行52目标33.15秒、58独立探针37.68秒、78关联回归19.78秒，全部exit0、0失败/错误/跳过/警告。四类批准内部失败后caller继续commit、跨案存在性差异、早期transport拒绝漏审计均真实RED后修复并原probe复验。对账只追加费用新版本，保原provider status/raw/query_at；实际25超额账单保负5和阻断incident。专门两项实际安装SDK→Factory探针证明重用实例每次dispatch增量独立且网络callback可另开Database短写；不是沿用T07旧transport的通过声明。详见[T08-review.md](T08-review.md)。

独立证据27文件封存SHA da7c95c8c77468381779ff600fccae393fdf006d6482843c4597a6e3c2546e57；33源/测试/固定样例运行前后相同、作者12文件初终匹配。此前另一reviewer两次被工具内容防护终止，实际测试0；未将其失败计作功能RED或继承其PASS，现审阅全部为重新实际执行。父节点两次只读文档路径误写已纠正，不是测试失败。

持久性边界：调用方Session的批准/预算/账单操作使用保存点；网络入口只接受显式Database的精确Factory，提交预留及发送标记并关闭Session后才等待网络。未知送达/扣费保持预留/次数，新Database恢复不自动发送。HTTP授权交接helper使用短事务；完整UI/API尚待T10。所有身份、价格、账单批准都是虚构工程身份，不能代替现实律师、供应商或生产批准。

额外已授权公开参考读取：Scrapling实际取得6页Microsoft Word API HTML，HTTP均200；首次curl77失败保留。ASCII临时CA是原证书字节副本，TLS保持启用，安装包关键文件与wheel一致；Word/COM/渲染仍NOT_RUN。见[工具记录](../tools/SCRAPLING.md)与[T09公开参考](../superpowers/plans/2026-10-03-T09-word-reference.md)。T09/T10依赖候选和T11静态映射仅准备，未纳入本阶段业务PASS。

提交前实际`.venv/Scripts/python.exe -X utf8 .audit-local/t08_parent_stage.py`退出0：冻结12/12、22明确暂存路径、222受保护索引原始字节、固定五fixture SHA、正式51包锁SHA及609项JUnit全部一致；`git diff --cached --check`退出0。两份普通工程文档CRLF→LF提示不涉及原始证据；来源/锁/固定fixture禁止转换。没有任何失败检查后提交。
