"""Durable, natural-language mock-hearing turns over the local case store."""
from datetime import datetime, timezone
import hashlib
import json
from uuid import uuid4
from business_store import window

# Stage/role order reused from qx-contract-workbench a26ae24,
# src/cn_contract/integrations/chiheng.py:21-23. No private engine is loaded.
ROLES = {'issues': ('moderator', 'plaintiff', 'defendant'),
         'evidence': ('plaintiff', 'defendant'),
         'questions': ('moderator', 'plaintiff', 'defendant'),
         'debate': ('plaintiff', 'defendant'), 'review': ('reviewer',)}
STAGES = tuple(ROLES)
SOURCE_NOTE_KINDS = ('consultation', 'fact', 'stance')
SCHEDULE = tuple((stage, role) for stage in STAGES for role in ROLES[stage])
ROLE_GUIDANCE = {
    'moderator': '围绕当前争点提出中立追问，区分已提供材料与待核事项；不预测裁判。',
    'plaintiff': '从原告立场说明请求、事实依据和证据，回应反方质疑；不把模拟说法当成事实。',
    'defendant': '从被告立场检验请求、事实和证据，提出具体反驳与替代解释；不编造反证。',
    'reviewer': '按已记录双方发言复盘争点、证据缺口、尚未回答的问题及下一步准备，不给胜诉概率。',
}
NOTICE = '本记录为模拟演练，原证据与模拟言论分开；角色上下文不代表独立模型或相互隔离的智能体。'


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def stamp():
    return datetime.now(timezone.utc).isoformat()


class HearingStore:
    def __init__(self, cases):
        self.cases = cases
        self.store = cases.store
        with self.store.db() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS legal_hearings(
                    id TEXT PRIMARY KEY,case_id TEXT NOT NULL,our_role TEXT NOT NULL,
                    focus TEXT NOT NULL,previous_id TEXT NOT NULL,snapshot_json TEXT NOT NULL,
                    source_notes_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,request_id TEXT UNIQUE,request_json TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS legal_hearing_turns(
                    id TEXT PRIMARY KEY,hearing_id TEXT NOT NULL,seq INTEGER NOT NULL,
                    stage TEXT NOT NULL,role TEXT NOT NULL,text TEXT NOT NULL,
                    citations TEXT NOT NULL,unresolved TEXT NOT NULL,warnings TEXT NOT NULL,
                    created_at TEXT NOT NULL,request_id TEXT,request_json TEXT NOT NULL,
                    UNIQUE(hearing_id,seq),UNIQUE(hearing_id,request_id));
                CREATE INDEX IF NOT EXISTS legal_hearing_case ON legal_hearings(case_id,created_at);
            ''')

    @staticmethod
    def _hearing(db, hearing_id):
        row = db.execute('SELECT * FROM legal_hearings WHERE id=?', (hearing_id,)).fetchone()
        if row is None:
            raise ValueError('演练不存在，请使用明确的演练编号。')
        return dict(row)

    @staticmethod
    def _turn(row, start=0, limit=None):
        result = dict(row)
        for field in ('citations', 'warnings'):
            result[field] = json.loads(result[field])
        result.pop('request_json', None)
        result['kind'] = 'simulation'
        result['review_status'] = 'unverified'
        text = result['text']
        end = len(text) if limit is None else start+limit
        result.update(text=text[start:end], text_chars=len(text), start=start,
                      next_start=end if end < len(text) else None, read_tool='read_hearing_turn')
        return result

    @staticmethod
    def _snapshot(materials):
        return sorted(({key: item[key] for key in ('path', 'sha256', 'link_id', 'version')}
                       for item in materials), key=lambda item: item['path'])

    def _material_status(self, db, row):
        current = self.cases._materials(db, row['case_id'])
        snapshot = json.loads(row['snapshot_json'])
        changed = snapshot != self._snapshot(current) or any(item['changed'] or item['missing'] for item in current)
        warnings = list(dict.fromkeys(warning for item in current for warning in item['warnings']))
        if changed:
            warnings.append('案件材料已变化或不可读取；旧轮次保留。请关联当前材料后，以 previous_id 明确新开演练。')
        return snapshot, changed, warnings

    @staticmethod
    def _source_notes(db, case_id):
        rows = db.execute('SELECT * FROM legal_notes n WHERE case_id=? AND kind IN (?,?,?) '
            'AND NOT EXISTS(SELECT 1 FROM legal_notes newer WHERE newer.case_id=n.case_id AND newer.supersedes=n.id) '
            'ORDER BY created_at,id', (case_id, *SOURCE_NOTE_KINDS)).fetchall()
        return [{'id': row['id'], 'kind': row['kind'], 'source': row['source'],
                 'sha256': hashlib.sha256(row['content'].encode('utf-8')).hexdigest(),
                 'review_status': 'unverified', 'created_at': row['created_at'],
                 'content_preview': row['content'][:4000], 'total_chars': len(row['content']),
                 'content_complete': len(row['content']) <= 4000,
                 'next_start': 4000 if len(row['content']) > 4000 else None,
                 'read_tool': 'read_case_note', 'case_id': case_id,
                 'citations': json.loads(row['citations']), 'warnings': json.loads(row['warnings'])}
                for row in rows]

    def _context_status(self, db, row):
        snapshot, materials_changed, warnings = self._material_status(db, row)
        frozen_notes = json.loads(row['source_notes_json'])
        current_notes = self._source_notes(db, row['case_id'])
        identity = lambda notes: [(note['id'], note['sha256']) for note in notes]
        notes_changed = identity(frozen_notes) != identity(current_notes)
        if notes_changed:
            warnings.append('客户原话、事实或立场记录已新增或更正；旧事实基础保留，请通过 previous_id 新开演练。')
        return {'evidence_materials': snapshot, 'source_notes': frozen_notes,
                'materials_changed': materials_changed, 'source_notes_changed': notes_changed,
                'context_changed': materials_changed or notes_changed, 'warnings': warnings}

    @staticmethod
    def _progress(db, hearing_id):
        count = db.execute('SELECT COUNT(*) FROM legal_hearing_turns WHERE hearing_id=?', (hearing_id,)).fetchone()[0]
        next_stage, next_role = SCHEDULE[count] if count < len(SCHEDULE) else (None, None)
        return {'turn_count': count, 'total_turns': len(SCHEDULE),
                'status': 'completed' if count == len(SCHEDULE) else 'active',
                'next_stage': next_stage, 'next_role': next_role}

    def _view(self, db, row, offset=0, limit=30):
        context = self._context_status(db, row)
        result = {key: value for key, value in row.items() if key not in ('snapshot_json', 'source_notes_json', 'request_json')}
        progress = self._progress(db, row['id'])
        rows = db.execute('SELECT * FROM legal_hearing_turns WHERE hearing_id=? ORDER BY seq LIMIT ? OFFSET ?',
                          (row['id'], limit, offset)).fetchall()
        result.update(progress, **context,
                      turns=[self._turn(turn, limit=4000) for turn in rows], notice=NOTICE,
                      next_offset=offset + len(rows) if offset + len(rows) < progress['turn_count'] else None)
        return result

    def start(self, case_id, our_role, focus='', request_id='', previous_id=''):
        our_role = {'原告': 'plaintiff', '被告': 'defendant'}.get(our_role, our_role)
        if our_role not in ('plaintiff', 'defendant'):
            raise ValueError('请明确我方为原告或被告；其他程序请使用一般庭前准备，不套用本演练。')
        if not isinstance(focus, str):
            raise ValueError('演练重点请使用自然语言。')
        payload = encoded(dict(case_id=case_id, our_role=our_role, focus=focus, previous_id=previous_id))
        with self.store.db() as db:
            db.execute('BEGIN IMMEDIATE')
            self.cases._case(db, case_id)
            if request_id:
                old = db.execute('SELECT * FROM legal_hearings WHERE request_id=?', (request_id,)).fetchone()
                if old:
                    if old['request_json'] != payload:
                        raise ValueError('同一 request_id 不能用于不同演练内容。')
                    return self._view(db, dict(old))
            if previous_id and self._hearing(db, previous_id)['case_id'] != case_id:
                raise ValueError('不能把其他案件的演练作为前序。')
            snapshot = self._snapshot(self.cases._materials(db, case_id))
            source_notes = self._source_notes(db, case_id)
            hid = str(uuid4())
            db.execute('INSERT INTO legal_hearings VALUES(?,?,?,?,?,?,?,?,?,?)',
                       (hid, case_id, our_role, focus, previous_id, encoded(snapshot), encoded(source_notes), stamp(), request_id or None, payload))
            return self._view(db, self._hearing(db, hid))

    def get(self, hearing_id, offset=0, limit=30):
        offset, limit = max(0, int(offset)), max(1, min(int(limit), 100))
        with self.store.db() as db:
            db.execute('BEGIN')
            return self._view(db, self._hearing(db, hearing_id), offset, limit)

    def list(self, case_id, offset=0, limit=20):
        offset, limit = window(offset, limit)
        with self.store.db() as db:
            db.execute('BEGIN')
            self.cases._case(db, case_id)
            total = db.execute('SELECT COUNT(*) FROM legal_hearings WHERE case_id=?', (case_id,)).fetchone()[0]
            rows = db.execute('SELECT id,case_id,our_role,focus,previous_id,created_at FROM legal_hearings '
                'WHERE case_id=? ORDER BY created_at,id LIMIT ? OFFSET ?', (case_id, limit, offset)).fetchall()
            return {'case_id': case_id, 'hearings': [dict(row) | self._progress(db, row['id']) for row in rows],
                    'total': total, 'next_offset': offset+len(rows) if offset+len(rows) < total else None}

    def read_turn(self, hearing_id, turn_id, start=0, limit=8000):
        start, limit = window(start, limit, 16000)
        with self.store.db() as db:
            row = db.execute('SELECT * FROM legal_hearing_turns WHERE hearing_id=? AND id=?', (hearing_id, turn_id)).fetchone()
            if row is None:
                raise ValueError('本次演练不存在这条发言。')
            return self._turn(row, start, limit)

    def _citations(self, db, row, citations):
        results, warnings = [], []
        allowed = {item['path']: item['sha256'] for item in json.loads(row['snapshot_json'])}
        for number, item in enumerate(citations, 1):
            try:
                checked, notes = self.cases._citations(db, row['case_id'], [item])
            except (ValueError, OSError):
                checked = [{**item, 'status': 'unverified'}] if isinstance(item, dict) else [{'provided': item, 'status': 'unverified'}]
                notes = [f'引文{number}未能绑定本案来源，正文保留待核。']
            for citation in checked:
                if (citation.get('path') not in allowed or citation.get('sha256') != allowed.get(citation.get('path'))):
                    citation['status'] = 'unverified'
                    notes.append(f'引文{number}不属于本轮冻结的材料版本，正文保留待核。')
            results.extend(checked)
            warnings.extend(notes)
        return results, list(dict.fromkeys(warnings))

    def append_turn(self, hearing_id, stage, role, text, citations=None, unresolved='', request_id=''):
        if not isinstance(text, str) or not text.strip():
            raise ValueError('请提供本次实际发言正文。')
        if not isinstance(unresolved, str):
            raise ValueError('待核事项请使用自然语言。')
        citations = [] if citations is None else citations
        if not isinstance(citations, list):
            raise ValueError('citations 应为可选来源列表，正文无需结构化。')
        payload = encoded(dict(stage=stage, role=role, text=text, citations=citations, unresolved=unresolved))
        with self.store.db() as db:
            db.execute('BEGIN IMMEDIATE')
            hearing = self._hearing(db, hearing_id)
            if request_id:
                old = db.execute('SELECT * FROM legal_hearing_turns WHERE hearing_id=? AND request_id=?',
                                 (hearing_id, request_id)).fetchone()
                if old:
                    if old['request_json'] != payload:
                        raise ValueError('同一 request_id 不能用于不同发言内容。')
                    return {'recorded': True, 'idempotent': True, 'hearing_id': hearing_id,
                            'turn': self._turn(old), **self._progress(db, hearing_id)}
            progress = self._progress(db, hearing_id)
            if progress['status'] == 'completed':
                raise ValueError('本次演练已结束。继续演练请关联 previous_id 新开，旧记录保留。')
            if (stage, role) != (progress['next_stage'], progress['next_role']):
                raise ValueError(f"发言顺序不符；下一项为 {progress['next_stage']} / {progress['next_role']}。")
            context = self._context_status(db, hearing)
            if context['context_changed']:
                return {'recorded': False,
                        'reason': 'context_changed' if context['source_notes_changed'] else 'materials_changed',
                        'hearing_id': hearing_id, **context, **progress,
                        'unsaved_turn': dict(stage=stage, role=role, text=text, citations=citations, unresolved=unresolved)}
            checked, warnings = self._citations(db, hearing, citations)
            tid = str(uuid4())
            db.execute('INSERT INTO legal_hearing_turns VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                       (tid, hearing_id, progress['turn_count'] + 1, stage, role, text, encoded(checked), unresolved,
                        encoded(warnings), stamp(), request_id or None, payload))
            turn = db.execute('SELECT * FROM legal_hearing_turns WHERE id=?', (tid,)).fetchone()
            return {'recorded': True, 'idempotent': False, 'hearing_id': hearing_id,
                    'turn': self._turn(turn), **self._progress(db, hearing_id)}

    def role_context(self, hearing_id, role):
        if role not in ROLE_GUIDANCE:
            raise ValueError('未知演练角色。')
        hearing = self.get(hearing_id)
        return {key: hearing[key] for key in ('case_id', 'our_role', 'focus', 'next_stage', 'next_role',
                'status', 'previous_id', 'materials_changed', 'source_notes_changed', 'context_changed',
                'warnings', 'evidence_materials', 'source_notes', 'notice')} | {
                    'hearing_id': hearing_id, 'role': role, 'role_instruction': ROLE_GUIDANCE[role],
                    'simulation_turns': hearing['turns']}
