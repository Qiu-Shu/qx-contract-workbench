"""Isolated synthetic SQLite URI comparison; no product files or real data."""
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent
PROBE = ROOT / 'independent-probe-data'
PROBE.mkdir(exist_ok=True)


def extended(path):
    return Path('\\\\?\\' + str(path)) if os.name == 'nt' else path


def options(path):
    ext = extended(path)
    return {
        'normal_as_uri': path.as_uri() + '?mode=ro',
        'extended_as_uri': ext.as_uri() + '?mode=ro',
        'quoted_native': 'file:' + quote(str(ext), safe='/:') + '?mode=ro',
        'quoted_posix': 'file:' + quote(ext.as_posix(), safe='/:') + '?mode=ro',
        'quoted_posix_4slash': 'file://' + quote(ext.as_posix(), safe='/:') + '?mode=ro',
        'quoted_native_3slash': 'file:///' + quote(str(ext), safe='/:') + '?mode=ro',
    }


def run():
    assert os.name == 'nt', 'This probe exercises Windows SQLite paths.'
    cases = []
    for label, target_length, name in [
        ('short', 180, 'synthetic.db'),
        ('long', 300, 'synthetic.db'),
        ('long_special', 300, '独立 %23 # & = 合成.db'),
    ]:
        folder = PROBE / label
        while len(str(folder / name)) < target_length:
            folder /= '独立合成路径' * 3
        extended(folder).mkdir(parents=True, exist_ok=True)
        path = folder / name
        with sqlite3.connect(str(extended(path))) as db:
            db.execute('CREATE TABLE IF NOT EXISTS sentinel (v TEXT)')
            db.execute('DELETE FROM sentinel')
            db.execute('INSERT INTO sentinel VALUES (?)', ('synthetic:' + label,))
        before = hashlib.sha256(extended(path).read_bytes()).hexdigest()
        for variant, uri in options(path).items():
            record = {'case': label, 'variant': variant, 'path_length': len(str(path)), 'uri': uri}
            try:
                with sqlite3.connect(uri, uri=True) as db:
                    record['value'] = db.execute('SELECT v FROM sentinel').fetchone()[0]
                    try:
                        db.execute("INSERT INTO sentinel VALUES ('must not write')")
                    except sqlite3.OperationalError as error:
                        record['write_error'] = str(error)
                    else:
                        record['write_error'] = 'UNEXPECTED_WRITE_ALLOWED'
                record['status'] = 'OPENED'
            except sqlite3.Error as error:
                record.update(status='OPEN_FAILED', error=str(error))
            record['hash_stable'] = hashlib.sha256(extended(path).read_bytes()).hexdigest() == before
            cases.append(record)
        missing = folder / 'missing %23 # & =.db'
        for variant, uri in options(missing).items():
            record = {'case': label + '_missing', 'variant': variant}
            try:
                with sqlite3.connect(uri, uri=True) as db:
                    db.execute('SELECT 1')
                record['status'] = 'UNEXPECTED_OPENED'
            except sqlite3.Error as error:
                record.update(status='REJECTED', error=str(error))
            record['missing_not_created'] = not extended(missing).exists()
            cases.append(record)
    collision_root = PROBE / 'percent-collision'
    collision_root.mkdir(exist_ok=True)
    for filename in ('literal%23.db', 'literal#.db'):
        with sqlite3.connect(collision_root / filename) as db:
            db.execute('CREATE TABLE IF NOT EXISTS sentinel (v TEXT)')
            db.execute('DELETE FROM sentinel')
            db.execute('INSERT INTO sentinel VALUES (?)', (filename,))
    requested = collision_root / 'literal%23.db'
    legacy_uri = 'file:' + requested.as_posix() + '?mode=ro'
    safe_uri = options(requested)['quoted_native']
    raw_uri_ambiguity = {}
    for label, uri in [('legacy_unescaped', legacy_uri), ('quoted_native', safe_uri)]:
        with sqlite3.connect(uri, uri=True) as db:
            raw_uri_ambiguity[label] = db.execute('SELECT v FROM sentinel').fetchone()[0]
    assert raw_uri_ambiguity == {'legacy_unescaped': 'literal#.db', 'quoted_native': 'literal%23.db'}
    result = {'python': sys.version, 'sqlite': sqlite3.sqlite_version, 'cases': cases,
              'raw_uri_ambiguity': raw_uri_ambiguity}
    (ROOT / 'independent-uri-probe.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    for item in cases:
        print(json.dumps({key: value for key, value in item.items() if key != 'uri'}, ensure_ascii=False))
    print(json.dumps({'raw_uri_ambiguity': raw_uri_ambiguity}, ensure_ascii=False))
    assert all(item.get('hash_stable', True) and item.get('missing_not_created', True) for item in cases)
    assert all(item.get('write_error') != 'UNEXPECTED_WRITE_ALLOWED' for item in cases)


if __name__ == '__main__':
    run()
