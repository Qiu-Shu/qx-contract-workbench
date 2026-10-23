import hashlib
import json
from pathlib import Path

here = Path(__file__).resolve().parent
root = here.parents[2]
original = json.loads((here / 'inputs-before.json').read_text('utf-8'))
products = {p: digest for p, digest in original.items() if not p.startswith('.local')}
current = {p: hashlib.sha256((root / p).read_bytes()).hexdigest() for p in products}
windows = json.loads((here.parent / 'windows-01/report.json').read_text('utf-8'))
common = sorted(set(products) & set(windows['source_before']))
result = {
    'baseline': '5d5e688b14ac53b81029184413cd37ce631b144c',
    'essential_findings': [],
    'independent_node': {'exit_code': 0, 'passed': 3},
    'independent_python_initial': {'collection_errors': 1, 'child_exit_code': None, 'runner_exit_code': 1},
    'independent_python_after_path_fix': {'exit_code': 1, 'passed': 2, 'failed': 1, 'failure': 'synthetic fixture rules-storage flag missing before intake conversion'},
    'independent_python_single_supplement': {'exit_code': 0, 'passed': 1},
    'distinct_independent_cases_final_passed': 6,
    'single_all_green_run_claimed': False,
    'product_and_contract_input_count': len(products),
    'product_and_contract_inputs_unchanged': current == products,
    'product_and_contract_hashes': current,
    'supplement_all_inputs': 28,
    'supplement_all_inputs_stable': True,
    'parent_windows_artifact_only': {
        'source_count': len(windows['source_before']),
        'source_before_equals_after': windows['source_before'] == windows['source_after'],
        'review_overlap_count': len(common),
        'review_overlap_sha_matches': all(current[p] == windows['source_before'][p] for p in common),
        'independently_executed': False},
    'limitations': ['no actual Windows run by this reviewer', 'no actual vendor request',
                    'no full Python or author Node suite rerun', 'no installed application or real materials touched'],
}
(here / 'final-verification.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
(here / 'report.md').write_text('''# CH-07C3a 独立 Spec 复核

基线：`5d5e688b14ac53b81029184413cd37ce631b144c`；范围为本轮工作树差异及新增文件，对照 `docs/plans/2026-10-23-profile-ui.md` 与 v2.1。结论：**0 项必须修复的问题**。本结论仅针对本片实施合同。

## 合同核对

- `assistant-generation.mjs` 复用既有发送状态机；支持可信桌面授权时普通无技能/附件/选片文字走一次 profile 流程。预览及原生确认绑定完整保存计划；取消/编辑/切换使旧确认失效。`existing` 与未知提交均按原请求 GET 找回，不补发 POST、不重新授权；其他材料/技能与旧桥路径未静默扩权。
- `providers/profile_history.py` 与 `attempts.read_attempt` 从持久 output、固定 handler、完整 basis/policy、事件及保存回执装配保存结果；缺失/篡改链路拒绝。回答与保存结果分开，未保存不展示已保存。后续合法接待更正、转案、新会话仍能读取原历史，不要求原授权续期。
- `assistant-profile.mjs` 为默认收起的只读面板，复用当前/历史读取接口；保留未知、冲突、律师保护值及原文位置，金额保留字符串。显示采用文字节点。关闭、切换、撤权和晚到响应隔离；无虚假编辑能力。
- domain DTO、静态白名单和主页面入口均为对应最小接线；未新增表、队列、模型调用或运行依赖。

## 独立探针及真实执行记录

1. Node 独立边界 **3 通过，退出码 0**：existing+未知 GET 不补发；提交后撤权清除旧结果；面板关闭再打开时旧响应不覆盖新版本。仅复用作者脚本测试前的夹具声明，未运行作者测试用例。见 `node.log`、`node.xml`、`node-exitcode.txt`、`commands.json`。
2. Python 首轮因复核脚本缺少测试目录路径，**1 个 collection error**，随后输出解码失败使复核 runner 退出 1；子进程退出码当时未记录，未推定。保留 `initial-runner/`。
3. 修正复核环境后，Python **2 通过、1 失败，退出码 1**。失败来自独立夹具未标记已初始化的 rules storage，发生在转案前；未触及待验历史断言。保留 `fixture-initial/` 与 `python.log/xml`。只补本地复核夹具标记，产品未变。
4. 仅补跑该一项，**1 通过，退出码 0**：先更正接待、转案、撤销原会话，再用新会话读到原保存/回答，且无业务写入；旧会话拒绝。见 `supplement-command.json`、`supplement.log/xml`、`supplement-summary.json`。

最终 6 个不同独立探针均已通过；**不是一次六项全绿运行**。另两项 Python 探针验证：重算摘要但降为 wire-only 许可仍拒绝；删除 model.finished 不留下可展示的已保存回执。

## 输入固定与边界

首轮至收尾 **21 个产品/合同/引用测试输入摘要未变**；补验自身 **28 个输入前后稳定**。准确摘要与根 Windows 证据交集见 `final-verification.json`；根证据 627 输入前后相等只作文件核对，不计为本复核实机执行。

本复核未运行真实模型、外部供应商请求、Windows 实机、作者整套回归；未操作安装版或真实材料，未改产品及共享测试。根任务的 366 桌面、141 前端、265 Python、6 组 Windows 结果属于其单独证据，不与上述独立计数合并。

可发布证据：本报告、`final-verification.json`、三个独立探针源/夹具及执行脚本、`commands.json`、`completion-command.json`、`supplement-command.json`、`node.log/xml`、`node-exitcode.txt`、`python.log/xml`、`python-exitcode.txt`、`supplement.log/xml`、`supplement-exitcode.txt`、摘要清单及 `initial-runner/`、`fixture-initial/` 下失败记录。**不发布**本地合成数据库/临时工作区与 `__pycache__`。
''', encoding='utf-8')
print(json.dumps({k: result[k] for k in ('product_and_contract_input_count', 'product_and_contract_inputs_unchanged', 'parent_windows_artifact_only')}, ensure_ascii=False))
print('report_sha256=' + hashlib.sha256((here / 'report.md').read_bytes()).hexdigest())
