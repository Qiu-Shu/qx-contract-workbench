# 证据使用说明

本目录只含独立虚构工程夹具及运行证据，不含用户真实合同。

- `evaluation/development`：保存的48份历史OCRResult原字节副本、重评分和分组摘要。本轮无开发集模型调用。
- `evaluation/holdout`：新6页虚构PNG、PDF、完整参考manifest、实际OCRResult及评分。生成时尚未查看该批OCR输出；现在已是公开的开发记录。
- `evaluation/audit-eight.json`：固定8个审计输入，分别有期望、历史v1与新v2结果。
- `evaluation/frozen-before.json`、`evaluation/receipt.json`：评分器及OCR调用链、原夹具和锁文件摘要；结束时无变更。
- `evaluation-execution.json`、`evaluation.log`：原执行命令、退出码与耗时。132.234秒包含历史位图核验和6页识别，不能当OCR吞吐量。
- `*-red*.xml`、`*-green.xml`、`related.xml`：实际阶段失败与修复结果；收集错误单列，重复用例不累加。
- `full-receipt.json`、`full.xml`、`collection.json`、`full.log`：最终完整工程回归的实际证据；不存在的文件不得解读为已通过。
- `checks.json`和`check-*.log`：逐条来源、默认配置、固定入口及语法检查；13来源继续保留NOT_PRODUCTION_APPROVED。

`evaluate.py`、`run_evaluation.py`、`run_full.py`是原`.audit-local`执行脚本的逐字节存档，保留原命令路径与输出路径，不是可任意位置直接运行的发布CLI。原评估要求全新目录；复跑应在独立的本机虚构工程环境中将存档放回其记录位置，另选新的输出目录并记录新脚本摘要，保留本次证据不覆盖。复跑模型仍受既有本机虚构测试许可和资源边界约束。

代码入口：`cn_contract.acceptance.ocr_scoring.score_page`。只计算已有文字时不启动模型；`scripts/ocr_synthetic_acceptance.py --output <全新目录>`会真实运行48页离线OCR，`--generate-only`只生成虚构夹具。该旧命令的退出条件仍为至少一个清晰页v1命中且无运行错误，退出0不等于v2或全文全部通过；必须看两个版本分列的摘要。

此目录使用`* -text`保留原始证据字节。开发集与留出集、字段与全文、工程与法律质量不得混用分母或相互替代。
