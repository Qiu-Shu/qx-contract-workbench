"""Exercise the application's public memory store against real local Hindsight."""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'bridge'))
from case_memory import CaseMemoryStore


def exercise(action, data, expected):
    store = CaseMemoryStore(Path(data) / 'workspace')
    if action == 'seed':
        expected = []
        for label, content in [('A', '虚构甲案约定周三交付蓝色样品。'), ('B', '虚构乙案约定周五归还绿色设备。')]:
            case_id = store.cases.create('合成恢复案件 ' + label)['id']
            note = store.cases.add_note(case_id, 'interview', content, source='合成来源 ' + label)
            memory = store.add(case_id, note_id=note['id'])['memory']
            status = store.sync(case_id)
            assert status['sync_state'] == 'ready', status
            expected.append({'case_id': case_id, 'memory': memory})
    elif action == 'append':
        store.add(expected[0]['case_id'], content='虚构副本新增红色样品。', source='合成副本新增', confirmed=True)
        assert store.sync(expected[0]['case_id'])['sync_state'] == 'ready'
        assert store.list(expected[0]['case_id'])['total'] == 2
        return {'copiedCaseMemoryCount': 2}
    elif action != 'check':
        raise ValueError('Unknown synthetic action')
    for row in expected:
        case_id, memory = row['case_id'], row['memory']
        assert store.status(case_id)['sync_state'] == 'ready'
        assert store.read(case_id, memory['id']) == memory
        assert store.list(case_id)['total'] == 1
        # Deliberately absent from both source texts: keyword fallback must fail this check.
        result = store.recall(case_id, '无法按原文关键词匹配的合成查询', use_hindsight=True)
        assert result['mode'] == 'hindsight', result
        assert result['matches'] == [memory], result
        assert store.sync(case_id)['sync_state'] == 'ready'  # Already indexed; no model extraction.
        other = next(item for item in expected if item['case_id'] != case_id)
        try:
            store.read(case_id, other['memory']['id'])
        except ValueError:
            pass
        else:
            raise AssertionError('Cross-case source access was allowed')
    return expected


if __name__ == '__main__':
    print(json.dumps(exercise(*sys.argv[1:], json.load(sys.stdin)), ensure_ascii=False))
