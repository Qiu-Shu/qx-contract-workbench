"""Engineering CLI. Business review commands are added only when implemented."""
import argparse
import json
from pathlib import Path
import sys

from pydantic import ValidationError

from cn_contract.config import DEFAULTS_PATH, PROJECT_ROOT, load_settings


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog='cn-contract', description='群兴合同审查工作台 离线工程入口')
    commands = parser.add_subparsers(dest='command', required=True)
    config = commands.add_parser('config-validate', help='校验默认配置并报告实际哈希')
    config.add_argument('--path', type=Path, default=DEFAULTS_PATH)
    schema = commands.add_parser('schema', help='从唯一领域模型生成报告schema')
    schema.add_argument('--output', type=Path, default=PROJECT_ROOT / 'schemas/review-report.v2.schema.json')
    schema.add_argument('--check', action='store_true', help='比较保存schema与当前领域模型，不写文件')
    demo=commands.add_parser('demo',help='四类独立虚构DOCX离线工程演示')
    demo.add_argument('--fixture',required=True,help='sales/service/lease/nda或已登记虚构DOCX路径')
    demo.add_argument('--provider',default='mock')
    demo.add_argument('--qcc',default='off')
    demo.add_argument('--output-root',type=Path,default=None)
    server=commands.add_parser('demo-server',help='显式启动本机独立虚构合同演示服务；不接收真实材料')
    server.add_argument('--port',type=int,default=8765)
    server.add_argument('--directory',type=Path,default=None,help='必须是本项目.local内全新目录')
    args = parser.parse_args(argv)
    try:
        if args.command == 'config-validate':
            settings = load_settings(args.path)
            print(json.dumps({'ok': True, 'config_sha256': settings.config_sha256,
                              'qcc_enabled': settings.qcc_enabled_default,
                              'model_provider': settings.model_provider_default}, ensure_ascii=False))
        elif args.command == 'schema':
            from cn_contract.domain import ReviewRun
            generated = ReviewRun.model_json_schema()
            if args.check:
                saved = json.loads(args.output.read_text(encoding='utf-8'))
                if saved != generated:
                    print('SCHEMA_OUT_OF_DATE', file=sys.stderr)
                    return 1
            else:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(json.dumps(generated, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
            print(json.dumps({'ok': True, 'schema_path': str(args.output), 'operation': 'check' if args.check else 'generate'}))
        elif args.command=='demo-server':
            from cn_contract.web.demo_server import serve
            serve(port=args.port,directory=args.directory)
            return 0
        elif args.command=='demo':
            from cn_contract.review.demo import run_demo
            from cn_contract.security import ServiceError
            try:
                summary=run_demo(args.fixture,provider=args.provider,qcc=args.qcc,output_root=args.output_root)
            except ServiceError as error:
                print(json.dumps({'ok':False,'error_code':error.code,'qcc_calls':0,'model_sends':0},ensure_ascii=False))
                return 1
            print(json.dumps(summary,ensure_ascii=False))
            return 0 if summary['validation_ok'] and summary['run_status']=='completed' else 1
    except (OSError, ValueError, ValidationError) as error:
        code = 'CONFIG_INVALID' if args.command == 'config-validate' else 'DEMO_INVALID' if args.command=='demo' else 'SCHEMA_INVALID'
        print(f'{code}:{type(error).__name__}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
