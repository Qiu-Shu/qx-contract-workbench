# T06 父节点实际验收

日期2026-10-03，workspace为`D:\Documents\ChatGPT\律所项目`，分支`codex/contract-review-v2`。仅独立虚构数据；未运行真实模型、QCC或付费网络。

|实际命令/检查|退出码|实际结果|
|---|---:|---|
|`.venv/Scripts/python.exe -X utf8 -m pytest --junitxml=docs/testing/T06-results.xml -q`|0|511 passed，1条既有Starlette/httpx弃用警告，75.18秒；完整JUnit已保存|
|四个`python -m cn_contract.cli demo --fixture tests/fixtures/synthetic/<type>_basic.docx --provider mock --qcc off`|各0|sales/service/lease/nda实际执行，不是作者测试中的一次sales；各18维，验证ok，QCC0|
|`.venv/Scripts/python.exe -X utf8 .audit-local/t06_parent_verify.py`|0|四份JSON和SQLite/原件独立核对；16个raw hash一致；23/23冻结文件SHA/bytes一致|
|`scripts/verify_defaults.py --file config/defaults.json`|0|0e4acba46c67b731cd9662d7b118217ddc55047ab69315961c7f78dfcfa9c887不变|
|`python -m cn_contract.cli schema --check`|0|唯一ReviewRun生成schema一致|
|`python -m pip check`|0|No broken requirements found；T06没有新增依赖|
|`scripts/verify_sources.py --mode development`|0|checked_sources=13，errors=[]，13条NOT_PRODUCTION_APPROVED警告|
|`scripts/verify_sources.py --mode release`|1|实际G06/G10的DEPENDENCY_REVIEW_PENDING及PRODUCTION_APPROVAL_MISSING；符合阻断门，不能写生产PASS|
|`git diff --check`|0|当时修改检查通过；提交前另核索引|

独立审阅最终80目标、77攻击探针、42必要权限/CLI回归与22计算回归均退出0；作者80目标与161受影响回归退出0。独立23/23作者文件哈希匹配；29个文件与四份JUnit封存于`.audit-local/t06-review/final-seal.json`。六组P2全部复验关闭，详情见T06-review.md；初始辅助收集、测试构造和错误文件名没有冒计功能RED。

父节点原始CLI stdout/退出码和辅助JSON留在忽略目录`.audit-local/t06-parent-demo-commands.json`、`t06-parent-demo-verification.json`及`t06-parent-checks.json`。辅助读不存在CHANGELOG_IMPLEMENTATION.md和Windows glob错误均实际exit1，后按rg发现真实CHANGELOG.md及目录检索；与功能测试无关，未当PASS/RED。验收脚本仅检查本轮已执行结果，没有添加镜像实现的正式测试。

首次stage提示provenance.json的CRLF会转LF；已新增`.gitattributes`虚构fixture路径的`-text`属性，但普通add沿用了原缓存blob。第一次索引hash检查实际exit1，父节点错误地继续提交032d5d7；工作区原文件及四份DOCX未变。随后逐项确认只有provenance索引hash不一致，`git add --renormalize -- tests/fixtures/synthetic/provenance.json`后5/5索引hash检查exit0，再补提交保留真实字节。没有把第一次失败写PASS，业务代码及此前511/四CLI通过结果未变。

mock字节计数不代表真实供应商tokenizer或真实费用；0使用mock_credit单位。失败使用留证在调用者提交后持久；外层事务整体回滚仍回滚技术记录，真实付费提供者尚未开放，不能声称已完成真实费用耐久保证。真实律师规则批准、法律金标准、试点、正式签发、Word/PDF及生产仍各自待完成。
