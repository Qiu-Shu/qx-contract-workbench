"""Explicit local-library maintenance. No downloads, server startup or model calls."""
import argparse
import json
from pathlib import Path
import sys


def main(argv=None):
    parser = argparse.ArgumentParser(description='群兴本地法律资料库：保留原件的导入与核对')
    commands = parser.add_subparsers(dest='command', required=True)
    cases = commands.add_parser('import-cases')
    cases.add_argument('--library-root', required=True, type=Path)
    cases.add_argument('--input', required=True, type=Path)
    cases.add_argument('--batch-id', required=True)
    cases.add_argument('--limit', type=int, help='本来源累计记录上限；省略表示直到文件结束')
    cases.add_argument('--batch-size', type=int, default=1000)
    pilot = commands.add_parser('import-pilot')
    pilot.add_argument('--library-root', required=True, type=Path)
    pilot.add_argument('--pilot-root', required=True, type=Path)
    pilot.add_argument('--source-root', required=True, type=Path)
    pilot.add_argument('--batch-id', default='cases-2025')
    args = parser.parse_args(argv)
    try:
        if args.command == 'import-cases':
            from .csv_source import import_case_file
            result = import_case_file(args.library_root, args.input, args.batch_id,
                                      limit=args.limit, batch_size=args.batch_size)
            print(json.dumps(result, ensure_ascii=False))
            return 0 if not result['failed'] else 2
        if args.command == 'import-pilot':
            from .pilot import import_pilot
            result = import_pilot(args.library_root, args.pilot_root, args.source_root, batch_id=args.batch_id)
            print(json.dumps(result, ensure_ascii=False))
            return 0 if not result['mismatched'] else 2
    except (ValueError, OSError) as error:
        # Never reflect original rows, credentials or arbitrary exception paths.
        safe = {'SOURCE_CHANGED', 'LIBRARY_BUSY', 'HEADER_INVALID', 'ASSET_HASH_MISMATCH',
                'IMPORT_LIMIT_INVALID', 'RECORD_REPLAY_MISMATCH', 'SOURCE_OUTPUT_OVERLAP', 'REDIRECTED_PATH'}
        code = str(error) if type(error) is ValueError and str(error) in safe else 'LIBRARY_OPERATION_REJECTED'
        print(json.dumps({'ok': False, 'code': code}), file=sys.stderr)
        return 1
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
