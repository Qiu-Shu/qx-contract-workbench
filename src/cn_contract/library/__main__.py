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
    laws = commands.add_parser('import-laws')
    laws.add_argument('--library-root', required=True, type=Path)
    laws.add_argument('--input', required=True, type=Path)
    laws.add_argument('--batch-id', required=True)
    build = commands.add_parser('build-index')
    build.add_argument('--library-root', required=True, type=Path)
    build.add_argument('--activate', action='store_true')
    build.add_argument('--resume', help='继续未发布的索引代际')
    for name in ('verify', 'activate', 'export-manifest'):
        maintenance = commands.add_parser(name)
        maintenance.add_argument('--library-root', required=True, type=Path)
        if name == 'activate':
            maintenance.add_argument('--generation-id', required=True)
        if name == 'export-manifest':
            maintenance.add_argument('--destination', required=True, type=Path)
    search = commands.add_parser('search')
    search.add_argument('--library-root', required=True, type=Path)
    search.add_argument('--query', default='')
    search.add_argument('--kind', choices=['all', 'case_csv', 'law_markdown'], default='all')
    search.add_argument('--mode', choices=['phrase', 'all'], default='all')
    for name in ('case-no', 'court', 'cause', 'province', 'date-from', 'date-to', 'cursor'):
        search.add_argument('--' + name)
    search.add_argument('--limit', type=int, default=20)
    show = commands.add_parser('show')
    show.add_argument('--library-root', required=True, type=Path)
    show.add_argument('--record-id', required=True)
    show.add_argument('--version-id', required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == 'build-index':
            from .index import build_generation, activate_generation
            generation = build_generation(args.library_root, resume=args.resume)
            if args.activate:
                activate_generation(args.library_root, generation)
            print(json.dumps({'generation_id': generation, 'activated': args.activate}))
            return 0
        if args.command == 'activate':
            from .index import activate_generation
            activate_generation(args.library_root, args.generation_id)
            print(json.dumps({'activated': True, 'generation_id': args.generation_id}))
            return 0
        if args.command == 'verify':
            from .portability import relocate_library
            print(json.dumps(relocate_library(args.library_root)))
            return 0
        if args.command == 'export-manifest':
            from .portability import export_manifest
            export_manifest(args.library_root, args.destination)
            print(json.dumps({'exported': True}))
            return 0
        if args.command == 'search':
            from ..domain import LibraryQuery
            from .service import search as search_library
            values = vars(args).copy()
            for name in ('command', 'library_root', 'query'):
                values.pop(name)
            result = search_library(args.library_root, LibraryQuery(text=args.query, **values))
            print(result.model_dump_json())
            return 0 if result.state == 'ready' else 2
        if args.command == 'show':
            from .service import read_original
            print(read_original(args.library_root, args.record_id, args.version_id).model_dump_json())
            return 0
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
        if args.command == 'import-laws':
            from .law_sections import import_laws
            result = import_laws(args.library_root, args.input, args.batch_id)
            print(json.dumps(result, ensure_ascii=False))
            return 0 if not result['failed'] else 2
    except (ValueError, OSError) as error:
        # Never reflect original rows, credentials or arbitrary exception paths.
        safe = {'SOURCE_CHANGED', 'LIBRARY_BUSY', 'HEADER_INVALID', 'ASSET_HASH_MISMATCH',
                'IMPORT_LIMIT_INVALID', 'RECORD_REPLAY_MISMATCH', 'SOURCE_OUTPUT_OVERLAP', 'REDIRECTED_PATH',
                'LIBRARY_DISK_BUDGET', 'LIBRARY_MEMORY_BUDGET', 'LIBRARY_DERIVED_BUDGET',
                'CATALOG_CHANGED_SINCE_BUILD', 'GENERATION_NOT_PENDING'}
        code = str(error) if type(error) is ValueError and str(error) in safe else 'LIBRARY_OPERATION_REJECTED'
        print(json.dumps({'ok': False, 'code': code}), file=sys.stderr)
        return 1
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
