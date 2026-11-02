# DeepSeek Flash / Pro 真实配对测评

2026-10-28。用户要求由助手比较模型并继续合同智能体任务；复用已授权 DeepSeek 接口与累计人民币 20 元上限，全部使用独立虚构材料。

## 方法及实际执行

独立代理先制定 4 个新微场景与 12 项 0/1 评分标准，随后冻结输入、评分、system、脚本及请求摘要。原文分别覆盖明确基数期间计算、正文附件顺位、双方主张与损失证明、合同中的提示注入。两模型 messages 完全相同，使用当前 `contract-c4-material-v1` system、非思考模式、JSON text/citations 输出和4096输出token上限；输入采用独立 compact-evaluation-v1，不声称复测了完整材料数据库或安装版。

外部实验根：`C:/Users/Administrator/Documents/Codex/2026-10-26/https-github-com-google-research-harness2`。

实际命令（均在本项目虚拟环境）：

```text
.venv/Scripts/python.exe -X utf8 <实验根>/work/compare_contract_models.py selftest
.venv/Scripts/python.exe -X utf8 <实验根>/work/compare_contract_models.py prepare
.venv/Scripts/python.exe -X utf8 <实验根>/work/compare_contract_models.py run
```

三类命令实际退出码均 0；selftest 两次通过但不重复计为独立测试数量。prepare 发起 0 网络请求，run 恰好新增2次成功真实请求，无重试。另独立审阅的两个“只改某一模型输入”的无网络反例均被调用前校验阻断；未读取凭据。调用前修复原先自比请求内容、未从fixtures重建的公平性缺口后，才冻结及调用。

|模型|输入/输出 tokens|本次秒数|高峰无缓存估价|
|---|---:|---:|---:|
|deepseek-flash|1320 / 2120|11.688|0.019600元|
|deepseek-v4-pro|1317 / 2664|47.906|0.083781元|

不同模型的 tokenizer 用量不同；输入文字完全一致。延时为各一次顺序请求，不能当作稳定速度基准。JSON严格只有text/citations，四个合法来源编号全部覆盖，没有未知编号；这不等于引用文字逐字核对或法律结论正确。

## 财务及封存审计

按 [DeepSeek 官方定价](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/) 当日高峰无缓存价格独立复算：Flash输入2/输出8、Pro输入9/输出27元每百万tokens。真实记录中的缓存优惠未抵扣，均为保守估价，未核销账单。

本次0.103381元；累计成功估价0.599589元；原未知1元预留继续保留。保护额19.853326/20元，剩余保护空间0.146674元。两次各预留0.25元；保护额不等于扣费，也不因本次实际估价低而重写旧不可变预留。

独立只读审计退出0：预算仅两次新增成功请求、响应ID唯一、请求与响应模型匹配、messages相同、输入/rubric/runner/system哈希与冻结相符、请求摘要及不可变响应封印相符、使用量与账本相同，旧证据文件未变。记录在 `outputs/model-pair-20261028/finance-review.json`。

原历史四份输入JSON字节漂移边界仍保留；本次继承的是此前独立内容与财务审计，不宣称原字节冻结验证恢复通过。原始请求/响应、冻结计划和预算在 `outputs/model-pair-20261028/`，匿名答案及冻结rubric在 `work/model-pair-20261028/`。

## 使用状态

匿名评分已完成：A=Pro、B=Flash，双方11/12，四例各3/3/3/2。F04.3的失分均是摘录内层引号样式差异，非语义改写或服从注入；按冻结标准保留分数。Pro把“无法证明条件满足”同时写成“条件尚未满足/暂无须付款”的措辞风险另行记录，不事后加扣分。按预定同分费用优先规则，选择Flash + 当前C4方法作为下一步试点首选，不称内容能力全面胜出。匿名证据及逐项原句在 `work/model-pair-20261028/blind-scores.json`，用户报告为 `outputs/deepseek-flash-pro-comparison.md`。

此次不修改合同 system 或正式法律签发规则，不上传客户材料，不提交/推送，不覆盖其他聊天的前端与打包修改。模型质量选择以已冻结标准及单独匿名复核为据，最终用户报告保存在外部实验输出目录。

桌面设置只读结果仍为 `deepseek-v4-pro`；当前桌面工具持续返回 USER_CONTROL，尚未取得界面或修改选择。独立API对比成功不能替代桌面切换、安装版验收或真实合同质量验收。
