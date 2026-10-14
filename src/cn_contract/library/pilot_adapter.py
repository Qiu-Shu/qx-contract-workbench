"""Run directly with the existing pilot Python; no workbench dependency imports."""
import json
import sys


def export_metadata(database):
    import duckdb
    if duckdb.__version__ != '1.5.6':
        raise ValueError('PILOT_RUNTIME_VERSION')
    con = duckdb.connect(database, read_only=True, config={
        'memory_limit': '1GB', 'threads': 2, 'enable_external_access': False,
        'autoinstall_known_extensions': False, 'autoload_known_extensions': False})
    try:
        count = con.execute('SELECT count(*) FROM records').fetchone()[0]
        if count > 10000:
            raise ValueError('PILOT_SCOPE_EXCEEDED')
        paths = [row[0] for row in con.execute('SELECT DISTINCT source_file FROM records ORDER BY source_file').fetchall()]
        print(json.dumps({'type': 'sources', 'count': count, 'paths': paths}, ensure_ascii=False))
        cursor = con.execute('SELECT record_id,source_file,ordinal,byte_start,byte_end,raw_sha256,body_sha256 FROM records ORDER BY source_file,ordinal')
        columns = [item[0] for item in cursor.description]
        while rows := cursor.fetchmany(500):
            for row in rows:
                print(json.dumps(dict(zip(columns, row)), ensure_ascii=False))
    finally:
        con.close()


if __name__ == '__main__':
    try:
        if len(sys.argv) != 2:
            raise ValueError('ARGUMENTS_INVALID')
        export_metadata(sys.argv[1])
    except Exception:
        print('PILOT_ADAPTER_REJECTED', file=sys.stderr)
        raise SystemExit(1)
