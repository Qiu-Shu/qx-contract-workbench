"""Independent offline checks against C1; no database or network access."""
import ast
import asyncio
from decimal import Decimal, Inexact, Rounded, localcontext
from hashlib import sha256
from pathlib import Path
import subprocess
import sys

import pytest

from cn_contract import domain as d
from cn_contract.assistant.providers import profile_codec, profile_preparation
from cn_contract.assistant.providers.deepseek_protocol import configuration, json_bytes
from cn_contract.assistant.providers.main import DeepSeekProvider
from tests.integration.test_assistant_main_provider import config
from tests.unit.test_assistant_profile_codec import fixture
from tests.unit.test_assistant_profile_preparation import draft, saved

BASE='37773d92f08e0b3bc2fed27064ceb011e8a72cd6'


def old_text(path):
    return subprocess.check_output(['git','show',BASE+':'+path]).decode('utf-8').replace('\r\n','\n')


def make(request=None, settings=None):
    request=request or fixture()[1]
    settings=settings or config()
    basis=profile_preparation.build_basis(draft(request),settings,
        base_profile_revision=request.base_profile_revision,project_intake=True)
    prepared=profile_preparation.prepare(*saved(request),basis,settings,composer_revision=4)
    return basis,prepared


def test_existing_dto_source_is_unchanged():
    name='src/cn_contract/domain.py'
    assert Path(name).read_text(encoding='utf-8').startswith(old_text(name))


@pytest.mark.parametrize('text',['独立合成：资料待核。','双引号"与反斜线\\及\r\n换行','😀e\u0301\u200d混合文字','合成'+('法'*16000)],
    ids=['chinese','escaped','unicode','long_text'])
def test_preparation_and_shared_builder_equal_fixed_c1_wire(text):
    syntax=ast.parse(old_text('src/cn_contract/assistant/providers/profile_codec.py'))
    nodes=[n for n in syntax.body if isinstance(n,ast.FunctionDef) and n.name in ('_validated','build_request')
        or isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='_SYSTEM' for t in n.targets)]
    namespace={'d':d,'configuration':configuration,'json_bytes':json_bytes}
    exec(compile(ast.Module(body=nodes,type_ignores=[]),'<fixed C1 profile wire>','exec'),namespace)
    request=fixture(text)[1]
    basis,prepared=make(request)
    expected=json_bytes(namespace['build_request'](request,config()))
    assert prepared.wire_payload_json.encode()==expected==json_bytes(profile_codec.build_request(request,config()))
    assert basis.wire_bytes==len(expected) and basis.wire_sha256==sha256(expected).hexdigest()


def test_decimal_traps_and_precision_do_not_change_fee_configuration_binding():
    settings=config().model_copy(update={'input_usd_per_million':Decimal('1234.123456'),
        'output_usd_per_million':Decimal('4321.654321')})
    normal=make(settings=settings)
    with localcontext() as context:
        context.prec=1;context.traps[Inexact]=True;context.traps[Rounded]=True
        unusual=make(settings=settings)
    assert unusual==normal
    assert profile_preparation.basis_digest(unusual[0])==profile_preparation.basis_digest(normal[0])


def test_coherent_fake_wire_hash_and_length_do_not_replace_server_wire():
    basis,_=make()
    forged=basis.model_copy(update={'wire_sha256':sha256(b'{}').hexdigest(),'wire_bytes':2})
    with pytest.raises(ValueError):
        profile_preparation.prepare(*saved(),forged,config(),composer_revision=4)


def test_preparation_does_not_enable_existing_default_denied_provider():
    _,prepared=make()
    keys=[]
    def blocked_secret():
        keys.append(True)
        raise AssertionError('No secret access is authorized by an offline basis')
    provider=DeepSeekProvider(config(),blocked_secret)
    reply=asyncio.run(provider.generate_profile(prepared.request))
    assert reply.error_code=='BLOCKED_LIVE' and reply.state=='failed_before_send' and keys==[]


def test_offline_preparation_import_is_independent_of_heavy_runtime_modules():
    result=subprocess.run([sys.executable,'-X','utf8','-c',
        "import sys; import cn_contract.assistant.providers.profile_preparation; "
        "assert not any(x in sys.modules for x in ('httpx2','sqlalchemy','fastapi','pdfplumber'))"],
        capture_output=True,text=True,check=False)
    assert result.returncode==0,result.stderr
