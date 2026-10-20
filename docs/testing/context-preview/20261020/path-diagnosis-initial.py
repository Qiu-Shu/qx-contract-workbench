from pathlib import Path
import sqlite3, json, hashlib
root=Path.cwd(); out=root/'.local/library-context-20261020'
old='tests/integration/test_assistant_context_preview.py'; new='tests/integration/test_assistant_context_preview_service.py'
record=json.loads((out/'spec-probes.json').read_text('utf-8'))
renamed=hashlib.sha256((root/new).read_bytes()).hexdigest()
assert record['inputs_after'][old]==renamed
with (out/'spec-review.md').open('a',encoding='utf-8') as f:
    f.write('\n补充：完整收集发现 unit/integration 同名测试模块冲突；integration 文件仅改名为 `test_assistant_context_preview_service.py`。与探针输入清单的原文件 SHA256 对比一致（'+renamed+'），产品未变，因此上述审查结论继续适用；未重复运行6项探针。\n')
p=root/'.local/library-context-20261020/full-pytest-3dc80d7b4b044ad9bce53c12a98c446f/test_40_samples_really_parse_c0/samples-e66d1a3015234a21924f9a0229c4afe6/protected-state.db'
with sqlite3.connect(p.as_uri()+'?mode=ro',uri=True) as db:
    tables=[r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    data={'database':str(p),'path_chars':len(str(p)), 'counts':{t:db.execute('SELECT COUNT(*) FROM "'+t+'"').fetchone()[0] for t in tables if t in {'matters','documents','audit_events','parse_results','fact_snapshots','review_runs'}}, 'audit_schema':db.execute('PRAGMA table_info(audit_events)').fetchall()}
    if 'audit_events' in tables:
        data['audit_rows']=db.execute('SELECT * FROM audit_events LIMIT 6').fetchall()
(out/'path-diagnosis-initial.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(data,ensure_ascii=False,indent=2))
