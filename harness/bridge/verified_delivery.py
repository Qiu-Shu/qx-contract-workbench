"""Producer-owned receipts for the runtime's saved-result delivery boundary."""
import hashlib
import json


def text_sha256(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def attach_delivery(cases, case_id, result):
    if result.get('recorded') is False or result.get('saved') is False:
        return result
    notes, sources = [], {}
    with cases.db() as db:
        cases._case(db, case_id)
        if result.get('id'):
            row = db.execute('SELECT * FROM legal_notes WHERE id=? AND case_id=?',
                             (result['id'], case_id)).fetchone()
            if row is None or db.execute('SELECT 1 FROM legal_notes WHERE supersedes=? AND case_id=?',
                                        (row['id'], case_id)).fetchone():
                raise ValueError('交付记录已变化，请回读后重新处理。')
            notes.append({'id': row['id'], 'sha256': text_sha256(row['content'])})
            refs = json.loads(row['citations'])
        else:
            refs = result.get('sources', [])
        for ref in refs:
            if ref.get('path') and ref.get('sha256'):
                sources[ref['path']] = {'path': ref['path'], 'sha256': ref['sha256']}
    documents = []
    for key, hash_key, label in [('path', 'sha256', '文稿'),
                                 ('internal_path', 'internal_sha256', '内部核对稿（勿外发）')]:
        if result.get(key):
            path = cases.safe(result[key])
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if digest != result.get(hash_key):
                raise ValueError('生成文件版本已变化，不能确认交付。')
            documents.append({'path': str(path), 'sha256': digest, 'label': label})
    return {**result, 'delivery': {'version': 1, 'case_id': case_id,
            'summary': result['user_summary'], 'notes': notes,
            'sources': list(sources.values()), 'documents': documents}}
