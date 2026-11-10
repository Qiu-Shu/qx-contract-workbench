"""Existing record encoding and UTC timestamps, independent of HTTP storage."""
from datetime import datetime, timezone
import hashlib
import json


def now(): return datetime.now(timezone.utc)
def encode(value): return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
def sha(value): return hashlib.sha256(encode(value).encode('utf-8')).hexdigest()
