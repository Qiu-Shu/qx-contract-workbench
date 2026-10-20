"""Finalize the narrowed post-freeze review without overwriting run evidence."""
import hashlib
import json
from pathlib import Path

out = Path(__file__).resolve().parent
root = out.parents[2]
json_path = out/'review-standards.json'
md_path = out/'review-standards.md'
prior = json.loads(json_path.read_text(encoding='utf-8'))
followup = json.loads((out/'cancellation-final.json').read_text(encoding='utf-8'))
assert followup['exit_code'] == 0 and followup['source_stable']
expected = {
    'src/cn_contract/assistant/providers/jev.py': '0ef430717db2f11c225ba0fddbb1ac23b736b1d033105d4e027e02bede1fa686',
    'src/cn_contract/assistant/providers/judge_execution.py': '7ad51bb46ba8002a83be414e04247f66d1c78c7293f29303988f27d53cb9951b',
}
assert set(followup['changed_since_previous']) == set(expected)
for name, digest in followup['source_after'].items():
    assert hashlib.sha256((root/name).read_bytes()).hexdigest() == digest
for name, digest in expected.items():
    assert followup['source_after'][name] == digest
for path in (json_path, md_path):
    intermediate = path.with_name(path.stem+'-intermediate'+path.suffix)
    assert not intermediate.exists(), 'Intermediate evidence already saved.'
    intermediate.write_bytes(path.read_bytes())

prior['source_sha256'] = followup['source_after']
prior['independent_verification']['scope_note'] = (
    'First freeze: all three cases passed; preserved unchanged. Only two product files subsequently changed; '
    'their diff and one directly relevant cancellation contract were independently rechecked.')
prior['supplemental_verification'] = {
    'command': followup['command'], 'exit_code': 0, 'passed': 1, 'failed': 0, 'pytest_seconds': 1.43,
    'evidence': ['cancellation-final.log', 'cancellation-final.exit', 'cancellation-final.xml', 'cancellation-final.json'],
    'changed_files': followup['changed_since_previous'], 'source_stable': True,
    'probe': 'Real loopback response decoded, external cancellation during AsyncClient cleanup; safe receipt persists and cancellation still propagates.',
    'input_tokens': 23, 'output_tokens': 7, 'provider_request_id': 'standards-cancel-after-decode',
    'loopback_posts': 1, 'external_network_attempts': 0, 'real_model_calls': 0,
    'unknown_cost_occupied_usd': '0.031', 'unit': 'USD',
    'answers_empty': True, 'decision_count': 0, 'cancellation_propagated': True,
    'replay_extra_posts': 0, 'main_run_row_unchanged': True, 'main_run_events_unchanged': True,
    'source_matches_author_refreeze': True,
}
prior['total_independent_cases_passed'] = 4
prior['closed_spec_followup'] = {
    'origin': 'Independent Spec axis after first Standards report',
    'issue': 'Post-decode cleanup cancellation previously lost safe received usage and provider request ID.',
    'resolution': 'JevCancelledError transports only a non-ok safe JudgeResult; execution validates identity through the shared result boundary, settles without a decision, then re-raises CancelledError.',
    'status': 'independently_verified_closed',
}
for check in prior['checks']:
    if check['file'].endswith('judge_execution.py'):
        check['lines'] = [11, 58]
        check['conclusion'] = ('HTTP stays outside transactions. Success and cancellation results share strict DTO/request/scope/hash validation; '
            'received cancellation accounting settles without answer adoption, then cancellation propagates.')
    if check['file'].endswith('/jev.py'):
        check['lines'] = [49, 236]
        check['conclusion'] += ' Cancellation carries a domain JudgeResult only after receipt, with non-ok status and empty answers; no new credential or authorization path.'
json_path.write_text(json.dumps(prior, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')

report = md_path.read_text(encoding='utf-8')
report = report.replace('本报告仅为 Standards 轴', '已合并重新冻结后的取消专项复核；本报告仅为 Standards 轴')
report = report.replace('`judge_execution.py:10–48`', '`judge_execution.py:11–58`')
report = report.replace('取消保持未知占用后向上传播。',
    '已收到的安全回执在取消通道中仍先结算，再向上传播取消；未收到时保守记为未知占用。')
report = report.replace('核心最终 SHA-256（完整 17 文件见 JSON）',
    '首次冻结 SHA-256（保留作为中间证据；下文列重新冻结后的两项变化，JSON 保存最终 17 文件摘要）')
report += '''

## 重新冻结后的取消专项复核

Spec 轴在首次报告后发现：响应已解析、清理资源期间收到外部取消，会丢失已知使用量和供应商请求号。作者只修改 `jev.py` 与 `judge_execution.py`；本轴复核这两处 diff，并仅增跑直接相关的一个独立探针，未重复前三项。

`jev.py:54–59,232–236` 以 `JevCancelledError` 携带既有 `domain.JudgeResult`，仅对 received 回执启用，强制非 ok、清空答案；异常不新增业务 DTO、密钥或授权接口。`judge_execution.py:34–56` 将取消与正常结果收敛到同一严格 DTO/request/scope/hash 边界；无效取消回执退回未知占用，合法回执落账但不采用建议，最后继续抛出 `CancelledError`。

`cancellation-final.log/.exit/.xml/.json`：**1 passed，退出码 0，1.43s**。真实回环回复已解析后暂停客户端 cleanup 并取消：取消向上传播，input/output tokens **23/7** 和固定合成 request ID 保留；answers 为空、decision 为 0，仍保守占 **0.031 USD**；重复 execute 无追加 POST，Main run 全字段及事件数不变。仅 1 次合成 POST，外网与真实模型调用均为 0。

17 个产品文件运行前后摘要稳定；相比首次验证仅下列两项改变，并与作者重新冻结摘要一致。原报告另存 `review-standards-intermediate.md/json`，原 3 项实际日志未覆盖。累计独立 **3 + 1 项 PASS**，不混计作者或 Spec 结果；取消残余已独立确认关闭，当前仍无 P0–P3 或可行动 Standards 发现。

| 最终变化文件 | SHA-256 |
|---|---|
| jev.py | `0ef430717db2f11c225ba0fddbb1ac23b736b1d033105d4e027e02bede1fa686` |
| judge_execution.py | `7ad51bb46ba8002a83be414e04247f66d1c78c7293f29303988f27d53cb9951b` |
'''
md_path.write_text(report, encoding='utf-8')
print(json.dumps({'status': 'saved', 'findings': 0, 'independent_passed': 4,
    'supplemental_passed': 1, 'source_count': len(followup['source_after'])}))
