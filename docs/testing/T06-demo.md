# 四份虚构合同实际演示

父节点2026-10-03实际执行四次文件路径CLI，每个退出0：

```powershell
.venv/Scripts/python.exe -X utf8 -m cn_contract.cli demo --fixture tests/fixtures/synthetic/sales_basic.docx --provider mock --qcc off
.venv/Scripts/python.exe -X utf8 -m cn_contract.cli demo --fixture tests/fixtures/synthetic/service_basic.docx --provider mock --qcc off
.venv/Scripts/python.exe -X utf8 -m cn_contract.cli demo --fixture tests/fixtures/synthetic/lease_basic.docx --provider mock --qcc off
.venv/Scripts/python.exe -X utf8 -m cn_contract.cli demo --fixture tests/fixtures/synthetic/nda_basic.docx --provider mock --qcc off
```

|独立fixture|实际run UUID|完整维度|reviewed_issue / insufficient_material|意见数|候选事实|确认版本|审查/确认前mock调用|QCC|
|---|---|---:|---|---:|---:|---:|---|---:|
|sales_basic.docx|a3a9756a-00f5-4fe3-8cbf-6f179b022815|18|1 / 17|3|3|2|3 / 1|0|
|service_basic.docx|cf137c29-0913-481b-bbe9-5054e7bf8d06|18|3 / 15|6|1|2|3 / 1|0|
|lease_basic.docx|2f83cb52-1198-4245-99b4-0aaf76efbf29|18|3 / 15|5|2|2|3 / 1|0|
|nda_basic.docx|84ea9137-3810-4ff9-bad0-1e910acf1080|18|2 / 16|4|1|2|3 / 1|0|

四份均run completed、matter awaiting_lawyer、validation ok、费用0 mock_credit。技术mock观察和缺件意见不证明法律效力、不宣称没有风险。全部法律规则未现实批准，明确BLOCKED_RULE_APPROVAL；mock不能正式签发，未生成Word/PDF。

实际产物均在workspace的`.local/review-demo/`下，分别为：

- `sales-20261003T055142-411382ab3cb541e29b747438a0d77a33`
- `service-20261003T055142-d50a5672b6d1484b9f7d1c6949fff4a1`
- `lease-20261003T055142-be8a7ec58f8948d49aa480c917db1c00`
- `nda-20261003T055142-c189ca1d3fa94613a8de3687c794d6af`

每目录实际存在review、manifest、parse、facts-candidate、facts-confirmed、validation、attempts、intakes、summary共9个JSON，另有受保护evidence.db和originals。父节点只读SQLite integrity/FK、run与JSON相等、manifest绑定原件SHA、确认事实SHA/版本、全部16次原始返回SHA逐项通过。原件SHA与provenance登记四份fixture一致；没有读取或上传真实合同。输出不进入Git；仅独立虚构fixture和上述实际记录提交。
