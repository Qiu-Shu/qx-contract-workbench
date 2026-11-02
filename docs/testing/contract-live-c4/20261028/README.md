# 合同 C4 材料适配与真实 DeepSeek 调用

日期：2026-10-28。用户已授权真实 DeepSeek 调用，累计预算上限人民币 20 元。本次只使用独立虚构合同。

## 实现范围

`assistant/contract_method.py` 定义 `contract-c4-material-v1`；`material_codec.py` 仅为合同材料任务附加该方法，保留其他业务协议及精确历史 SYSTEM 回放，`material_integrity.py` 按原依据重建核验。历史合同结果不因新方法升级而失效。完整计划见 `docs/plans/2026-10-26-contract-live-c4.md`。

## 本次实际验证

命令（项目虚拟环境）：

```text
.venv/Scripts/python.exe -X utf8 -m pytest tests/unit/test_contract_live_method.py tests/unit/test_material_model_codec.py tests/integration/test_contract_c4_material_flow.py -q --junitxml=docs/testing/contract-live-c4/20261028/targeted.xml
```

退出码 0，19 passed，9.56 秒。JUnit：`targeted.xml`。覆盖合同方法绑定、旧协议回放、预算不足、授权撤回、材料变更、持久化及重复执行不重发；测试中的供应商为替身，和下面单次真实调用分别计数。

真实运行命令：

```text
.venv/Scripts/python.exe -X utf8 C:/Users/Administrator/Documents/Codex/2026-10-26/https-github-com-google-research-harness2/work/run_contract_live.py
```

退出码 0。独立虚构 DOCX 经现有上传、解析、合同业务、原生授权、排队和 runner 请求真实 `deepseek-flash`，输出保存且回读相同，模型/业务完整性校验通过，重复执行只返回原回执。新增供应商请求 1 次，ID `8cbe28d4-1611-4aed-9e3c-dd811dc54a45`。输入 1669、输出 1409、合计 3078 tokens；`review_status=unverified`，未签发。脚本独占初始化及数据库触发器限制新增 1 次，不能为重新验证而再次运行。

供应商高峰无缓存保守估价 0.01461 元，累计成功估价 0.496208 元；历史未知 1 元保留，预算保护额 19.353326 / 20 元（不是扣费）。本轮未更新安装包，独立工作数据库未合并到真实用户数据库。

完成前再次只读核对（退出 0，新增网络请求 0）：SQLite integrity_check=ok；唯一新增调用 status=ok；请求 hash 等于保存 basis 的 wire_sha256；响应文件 SHA-256 等于不可变 response_seals；JUnit 为 19 tests、0 failures、0 errors、0 skipped。桌面模型选择只读检查为 Pro；三次桌面快照均返回 USER_CONTROL，未取得界面或修改模型设置，不能声明安装版已切换 Flash。

## 证据与边界

实验根：`C:/Users/Administrator/Documents/Codex/2026-10-26/https-github-com-google-research-harness2`。本次响应、摘要、预算与历史审计在 `outputs/live-contract-results/`；可读草稿在 `outputs/deepseek-live-contract-draft.md`。凭据不进入 Git、报告或输出；本仓库只记录脱敏元数据。

历史四份输入/金标准 JSON 的字节摘要漂移导致原冻结 verifier 未通过，不更新旧封印。独立财务审计核对原历史账本、调用数、响应封印、请求内容对应、评分重放，并加前后文件快照与唯一响应 ID 检查后，继承 19.103326 元保护额。审计明确记录 `original_byte_frozen_verifier_passed=false`。

独立只读审阅检查单次预留、调用前授权、真实 runner 和持久化，发现的前后快照及响应 ID 检查缺口已在发起真实调用前补齐。此前各组回归不累加为本次 19 项分母。

这验证了一个合成样本的真实材料链路，不证明安装版、真实客户材料、法律质量或生产验收通过。C4 材料版协议不同于选优实验，不继承原分数；既有离线计算门不等于自动核验本次自由文本草稿。桌面模型切换状态单独记录，不与此真实调用混同。
