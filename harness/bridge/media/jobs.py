"""Persistent, fenced attempts; an unknown paid request is never retried."""
import asyncio
import json
from uuid import uuid4

from . import domain as d
from .store import digest, encoded


class KnownFailure(Exception):
    """The provider returned a definite failure, rather than an unknown outcome."""


class MediaJobs:
    def __init__(self, store):
        self.store = store

    def _row(self, db, identifier):
        row = db.execute('SELECT * FROM media_jobs WHERE id=?', (identifier,)).fetchone()
        if row is None: raise ValueError('NOT_FOUND')
        if row['workspace_id'] != self.store.actor.workspace_id or row['owner_user_id'] != self.store.actor.user_id:
            raise PermissionError('ACCESS_DENIED')
        return row

    @staticmethod
    def _view(row):
        value = dict(row)
        for name in ('input','output','receipt'):
            value[name] = json.loads(value[name]) if value[name] is not None else None
        return value

    def _validate_refs(self, db, request):
        refs = [request[k] for k in ('profile_ref','project_ref','review_ref','source_ref') if request.get(k)]
        refs += request.get('input_refs',[]) + request.get('expected_refs',[])
        from .reviews import collect_dependencies
        collect_dependencies(self.store,refs,transaction=db)
        if request['kind'] in ('brief','script','shooting_plan'):
            output=request.get('output_ref')
            if request['expected_output_revision']!= (output['revision'] if output else 0): raise ValueError('OUTPUT_REVISION_REQUIRED')
            if output:
                if output['kind']!=request['kind']: raise ValueError('REFERENCE_MISMATCH')
                # The old output's dependencies may be stale: regeneration is
                # precisely how it adopts the selected new input revisions.
                row=self.store._load(db,output,current=True)
                if row['value']['project_ref']['entity_id']!=request['project_ref']['entity_id']: raise ValueError('PROJECT_MISMATCH')
        for key,kind in [('profile_ref','profile'),('project_ref','project'),('review_ref','review'),('source_ref','source')]:
            if request.get(key) and request[key]['kind'] != kind: raise ValueError('REFERENCE_MISMATCH')
        if request['kind'] == 'export' and request['mode'] == 'approved' and not request.get('review_ref'):
            raise ValueError('REVIEW_REQUIRED')

    def submit(self, value):
        value = d.JOB_INPUT.validate_python(value).model_dump(mode='json')
        actor = self.store.actor
        sha = digest(value)
        with self.store.db(write=True) as db:
            previous = db.execute('SELECT * FROM media_jobs WHERE workspace_id=? AND owner_user_id=? AND request_id=?',
                                  (actor.workspace_id,actor.user_id,value['request_id'])).fetchone()
            if previous:
                if previous['input_digest'] != sha: raise ValueError('IDEMPOTENCY_CONFLICT')
                return self._view(previous)
            self._validate_refs(db, value)
            identifier, now = str(uuid4()), d.utc_stamp()
            db.execute('''INSERT INTO media_jobs(id,workspace_id,owner_user_id,request_id,input_digest,input,
                       kind,project_id,state,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)''',
                       (identifier,actor.workspace_id,actor.user_id,value['request_id'],sha,encoded(value),
                        value['kind'],value.get('project_ref',{}).get('entity_id'),'queued',now,now))
            return self._view(self._row(db, identifier))

    def get(self, identifier):
        with self.store.db() as db: return self._view(self._row(db,identifier))

    def by_request(self, request_id):
        with self.store.db() as db:
            row=db.execute('SELECT * FROM media_jobs WHERE workspace_id=? AND owner_user_id=? AND request_id=?',
                (self.store.actor.workspace_id,self.store.actor.user_id,request_id)).fetchone()
            return self._view(row) if row else None

    def list(self):
        with self.store.db() as db:
            return [self._view(row) for row in db.execute('''SELECT * FROM media_jobs WHERE workspace_id=?
                AND owner_user_id=? ORDER BY created_at,id''', (self.store.actor.workspace_id,self.store.actor.user_id))]

    def claim(self, worker_run_id):
        if not isinstance(worker_run_id,str) or not worker_run_id: raise ValueError('INVALID_WORKER')
        with self.store.db(write=True) as db:
            if db.execute("SELECT COUNT(*) FROM media_jobs WHERE state IN ('running','cancel_requested')").fetchone()[0] >= 2:
                return None
            candidates = db.execute('''SELECT * FROM media_jobs j WHERE state='queued' AND workspace_id=?
                AND owner_user_id=? AND (j.kind NOT LIKE 'source_%' OR NOT EXISTS(SELECT 1 FROM media_jobs b
                WHERE b.kind LIKE 'source_%' AND b.state IN ('running','cancel_requested')))
                AND (project_id IS NULL OR NOT EXISTS(SELECT 1 FROM media_jobs a
                WHERE a.project_id=j.project_id AND a.kind=j.kind AND a.state IN ('running','cancel_requested')))
                ORDER BY created_at,id''', (self.store.actor.workspace_id,self.store.actor.user_id)).fetchall()
            if not candidates: return None
            row = candidates[0]
            db.execute("UPDATE media_jobs SET state='running',attempt_id=?,worker_run_id=?,sent=0,updated_at=? WHERE id=?",
                       (str(uuid4()),worker_run_id,d.utc_stamp(),row['id']))
            return self._view(self._row(db,row['id']))

    def _attempt(self, db, claim):
        row = self._row(db,claim['id'])
        if row['attempt_id'] != claim['attempt_id'] or row['worker_run_id'] != claim['worker_run_id'] or row['state'] not in ('running','cancel_requested'):
            raise ValueError('STALE_ATTEMPT')
        return row

    def mark_sent(self, claim):
        with self.store.db(write=True) as db:
            row = self._attempt(db,claim)
            if row['state'] == 'cancel_requested': raise ValueError('CANCELLED')
            self._validate_refs(db,json.loads(row['input']))
            db.execute('UPDATE media_jobs SET sent=1,updated_at=? WHERE id=?',(d.utc_stamp(),row['id']))

    def finish(self, claim, output=None, *, receipt=None, error=None, unknown=False, publish=None):
        with self.store.db(write=True) as db:
            row = self._attempt(db,claim)
            state = 'succeeded'
            if row['state'] == 'cancel_requested': state = 'cancelled'
            elif unknown: state = 'outcome_unknown'
            elif error: state = 'failed'
            else:
                try: self._validate_refs(db,json.loads(row['input']))
                except (ValueError,PermissionError): state,error = 'failed','STALE_INPUT'
            if state=='succeeded' and publish:
                db.execute('SAVEPOINT publish_output')
                try:
                    output=publish(db,output)
                    db.execute('RELEASE publish_output')
                except (ValueError,PermissionError):
                    db.execute('ROLLBACK TO publish_output');db.execute('RELEASE publish_output')
                    state,error,output='failed','STALE_OUTPUT',None
            if receipt is None and row['receipt']: receipt=json.loads(row['receipt'])
            db.execute('UPDATE media_jobs SET state=?,output=?,receipt=?,error=?,updated_at=? WHERE id=?',
                       (state,encoded(output) if state=='succeeded' else None,
                        encoded(receipt) if receipt is not None else None,error,d.utc_stamp(),row['id']))
            return self._view(self._row(db,row['id']))

    def record_receipt(self,claim,receipt):
        with self.store.db(write=True) as db:
            row=self._attempt(db,claim)
            previous=json.loads(row['receipt']) if row['receipt'] else {'attempts':[]}
            previous.setdefault('attempts',[]).append(receipt)
            db.execute('UPDATE media_jobs SET receipt=?,updated_at=? WHERE id=?',(encoded(previous),d.utc_stamp(),row['id']))

    def cancel(self, identifier):
        with self.store.db(write=True) as db:
            row = self._row(db,identifier)
            if row['state'] in ('queued','running'):
                state = 'cancel_requested' if row['state']=='running' else 'cancelled'
                db.execute('UPDATE media_jobs SET state=?,updated_at=? WHERE id=?',(state,d.utc_stamp(),identifier))
            return self._view(self._row(db,identifier))

    def recover(self, old_worker_run_id):
        with self.store.db(write=True) as db:
            db.execute('''UPDATE media_jobs SET state=CASE WHEN sent=1 THEN 'outcome_unknown'
                WHEN state='cancel_requested' THEN 'cancelled' ELSE 'queued' END,updated_at=?
                WHERE worker_run_id=? AND workspace_id=? AND owner_user_id=?
                AND state IN ('running','cancel_requested')''',
                (d.utc_stamp(),old_worker_run_id,self.store.actor.workspace_id,self.store.actor.user_id))

    async def run_next(self, worker_run_id, handler):
        claim = self.claim(worker_run_id)
        if claim is None: return False
        try:
            output,receipt = await handler(claim,lambda:self.mark_sent(claim))
            self.finish(claim,output,receipt=receipt)
        except (Exception,asyncio.CancelledError) as error:
            state = self.get(claim['id'])
            unknown = bool(state['sent']) and not isinstance(error,KnownFailure)
            self.finish(claim,error=type(error).__name__,unknown=unknown)
            if isinstance(error,asyncio.CancelledError): raise
        return True
