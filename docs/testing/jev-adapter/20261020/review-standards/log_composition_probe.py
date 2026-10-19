"""Synthetic-only regression: coexisting adapters must not grow log factories."""
import json
import logging
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT/'src'))
from cn_contract.assistant.providers import jev, main

original = logging.getLogRecordFactory()
count = 0
def record(name, message):
    return logging.getLogger(name).makeRecord(name, logging.INFO, __file__, 1, message, (), None)

try:
    for _ in range(600):
        main._protect_logs()
        jev._protect_logs()
        count += 1
    # An ordinary application logger must remain usable after repeated calls.
    result = record('independent.application', 'synthetic outside record')
    assert result.getMessage() == 'synthetic outside record'
    token = jev._private.set(True)
    try:
        protected = record('httpx2.synthetic', 'synthetic-private-marker')
        assert 'synthetic-private-marker' not in protected.getMessage()
    finally:
        jev._private.reset(token)
    token = main._private.set(True)
    try:
        protected = record('httpcore2.synthetic', 'synthetic-main-marker')
        assert 'synthetic-main-marker' not in protected.getMessage()
    finally:
        main._private.reset(token)
    assert record('httpx2.synthetic', 'outside-context-marker').getMessage() == 'outside-context-marker'
    print(json.dumps({'status': 'passed', 'alternating_pairs': count,
        'network_calls': 0, 'secret_reads': 0}))
except Exception as error:
    print(json.dumps({'status': 'failed', 'alternating_pairs': count,
        'error_type': type(error).__name__, 'network_calls': 0, 'secret_reads': 0}))
    raise
finally:
    logging.setLogRecordFactory(original)
