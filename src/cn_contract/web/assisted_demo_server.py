"""Explicit loopback-only CR-01 fiction workbench; manual candidates, no model."""
import argparse
import hashlib
import json
from pathlib import Path

from ..config import PROJECT_ROOT
from ..domain import SyntheticAssistedPolicy
from ..security import ServiceError
from .demo_server import build_demo, DEMO_PASSWORD

SEED_MANIFEST=PROJECT_ROOT/'tests/fixtures/assisted-v1/manifest.json'
SEED_MANIFEST_SHA256='16a8d213a16e6741459085fe72409b36849a410595d1043ee9ad1ea193feedce'


def load_seed_policy(*,manifest_path=SEED_MANIFEST):
    """Only the author-registered inventory, not a client 'fictional' assertion."""
    try:
        raw=Path(manifest_path).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=SEED_MANIFEST_SHA256:
            raise ValueError('inventory differs')
        inventory=json.loads(raw)
        cases=inventory['cases']
        if len(cases)!=12 or {c['contract_type'] for c in cases}!={'sales','service','lease','nda'}:
            raise ValueError('seed scope differs')
        for case in cases:
            relative=Path(case['path'])
            path=(PROJECT_ROOT/relative).resolve()
            approved=(PROJECT_ROOT/'tests/fixtures/assisted-v1').resolve()
            if relative.is_absolute() or not path.is_relative_to(approved) or not approved.is_relative_to(PROJECT_ROOT.resolve()):
                raise ValueError('seed location differs')
            data=path.read_bytes()
            if len(data)!=case['bytes'] or hashlib.sha256(data).hexdigest()!=case['sha256'] or case['fictional'] is not True:
                raise ValueError('seed bytes differ')
        return SyntheticAssistedPolicy(policy_id='assisted-v1-fiction-only',purpose='assisted_draft',
            document_hashes=tuple(c['sha256'] for c in cases),candidate_source='manual_synthetic')
    except (ValueError,TypeError,KeyError,OSError):
        raise ServiceError('DATA_POLICY_UNAPPROVED',409) from None


def build_assisted_demo(directory=None):
    policy=load_seed_policy()
    local=(PROJECT_ROOT/'.local').resolve()
    if not local.is_relative_to(PROJECT_ROOT.resolve()):
        raise ServiceError('DATA_POLICY_UNAPPROVED',409)
    return build_demo(directory,purpose='assisted_draft',assisted_policy=policy)


def serve(*,port=8766,directory=None):
    if type(port) is not int or not 1024<=port<=65535:raise ValueError('local unprivileged port required')
    import uvicorn
    app,root=build_assisted_demo(directory)
    print('独立虚构材料；离线人工候选；真实模型推理未运行，QCC关闭；不是正式法律意见。',flush=True)
    print(f'http://127.0.0.1:{port}/login',flush=True)
    print('虚构用户名：lawyer / reviewer / assistant / admin；虚构密码：'+DEMO_PASSWORD,flush=True)
    print('材料目录：'+str(PROJECT_ROOT/'tests/fixtures/assisted-v1'),flush=True)
    print('本次独立工作目录：'+str(root),flush=True)
    uvicorn.run(app,host='127.0.0.1',port=port,workers=1,access_log=False,log_level='warning')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description='首轮律师辅助工作稿，仅12份独立虚构合同与离线人工候选')
    parser.add_argument('--port',type=int,default=8766)
    parser.add_argument('--directory',type=Path,default=None,help='本项目.local内全新目录')
    args=parser.parse_args()
    serve(port=args.port,directory=args.directory)
