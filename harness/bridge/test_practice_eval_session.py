"""Real MCP relay, synthetic-only, without a model or credential access."""
import json
from pathlib import Path
import subprocess
import sys
from uuid import uuid4


def test_real_relay_isolates_case_and_reads_full_saved_artifacts():
    script = Path(__file__).with_name('practice_eval_session.py')
    child = subprocess.Popen([sys.executable, '-X', 'utf8', str(script), 'offline-review-'+uuid4().hex, 'corporate'],
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                             text=True, encoding='utf-8')
    try:
        ready = json.loads(child.stdout.readline())
        assert ready['ready']
        cid = ready['case_id']
        long_body = '合成讨论保留反对意见。' * 900
        requests = [
            {'name':'read_case_material','arguments':{'case_id':'other-case','path':ready['material_path']}},
            {'name':'read_case_material','arguments':{'case_id':cid,'path':'../private.txt'}},
            {'name':'create_case','arguments':{'title':'Not allowed'}},
            {'name':'record_case_note','arguments':{'case_id':cid,'kind':'corporate_record','content':long_body}},
            {'name':'write_word_draft','arguments':{'filename':'合成.docx','title':'合成会议记录','content':long_body}},
            {'op':'finalize'}]
        output, _ = child.communicate('\n'.join(json.dumps(r,ensure_ascii=False) for r in requests)+'\n',timeout=90)
        rows = [json.loads(line) for line in output.splitlines()]
        assert child.returncode == 0 and len(rows) == 6
        assert all(r['is_error'] for r in rows[:3])
        assert rows[3].get('executed') is True
        actual = rows[-1]
        assert actual.get('source_unchanged') is True and actual.get('notes_complete') is True
        assert actual['case']['notes'][0]['content'] == long_body
        assert actual['drafts'][0]['sha256'] and long_body in actual['drafts'][0]['text']
    finally:
        if child.poll() is None:
            child.kill(); child.wait()
