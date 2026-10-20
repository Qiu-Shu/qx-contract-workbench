"""Read-only host inspection for the synthetic native control driver."""
import argparse
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
import sqlite3

from cn_contract import domain as d
from cn_contract.assistant.providers.jev_codec import input_hash
from cn_contract.config import canonical_json


def inspect(database, run_id=None, source_hash=None):
    connection = sqlite3.connect(Path(database).resolve().as_uri() + '?mode=ro', uri=True)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute('PRAGMA query_only=ON')
        tables = ('assistant_messages', 'assistant_runs', 'assistant_model_attempts',
                  'assistant_model_receipts', 'assistant_model_outputs', 'assistant_judge_attempts',
                  'assistant_judge_receipts', 'assistant_judge_decisions')
        counts = {table: connection.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
                  for table in tables}
        if run_id is None:
            assert set(counts.values()) == {0}
            return {'counts': counts, 'result': 'empty'}
        assert set(counts.values()) == {1}
        run = connection.execute('SELECT * FROM assistant_runs WHERE id=?', (run_id,)).fetchone()
        main = connection.execute('SELECT * FROM assistant_model_attempts').fetchone()
        judge = connection.execute('SELECT * FROM assistant_judge_attempts').fetchone()
        message = connection.execute('SELECT * FROM assistant_messages').fetchone()
        receipt = json.loads(connection.execute('SELECT receipt_json FROM assistant_judge_receipts').fetchone()[0])
        decision = json.loads(connection.execute('SELECT decision_json FROM assistant_judge_decisions').fetchone()[0])
        request = d.JudgeRequest.model_validate_json(judge['request_json'])
        config = d.JevConfig.model_validate_json(judge['config_json'])
        policy = d.JudgePolicy.model_validate_json(judge['policy_json'])
        assert run['id'] == main['run_id'] == judge['run_id'] == decision['run_id']
        assert run['message_id'] == judge['message_id'] == message['id']
        assert run['request_id'] == str(request.local_request_id)
        assert request.scope == d.ScopeSnapshot.model_validate_json(run['scope_snapshot'])
        assert sha256(message['content'].encode('utf-8')).hexdigest() == source_hash == judge['source_sha256']
        assert request.text == message['content']
        assert input_hash(request, config) == judge['input_hash'] == receipt['result']['input_hash']
        assert policy.permissions[0].input_hash == judge['input_hash'] and policy.max_calls == 1
        assert sha256(canonical_json(policy.model_dump(mode='json')).encode('utf-8')).hexdigest() == judge['policy_sha256']
        assert receipt['cost_status'] == 'unknown'
        assert Decimal(receipt['occupied_usd']) == Decimal(judge['reserved_usd']) == Decimal('.02')
        assert receipt['result']['evidence'] == judge['state'] == 'received'
        assert receipt['result']['status'] == 'ok'
        assert decision['review_status'] == 'unverified' and decision['audience'] == 'internal'
        assert decision['decision']['workflow'] == 'client_reply'
        return {'counts': counts, 'result': 'same_run_verified', 'source_sha256': source_hash,
                'judge_input_sha256': judge['input_hash'], 'judge_state': judge['state'],
                'judge_cost_status': receipt['cost_status'], 'judge_occupied_usd': receipt['occupied_usd'],
                'judge_review_status': decision['review_status']}
    finally:
        connection.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('database')
    parser.add_argument('--run')
    parser.add_argument('--hash')
    options = parser.parse_args()
    assert bool(options.run) == bool(options.hash)
    print(json.dumps(inspect(options.database, options.run, options.hash)))
