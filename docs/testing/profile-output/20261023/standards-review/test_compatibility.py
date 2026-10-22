"""Independent compatibility checks against the fixed committed baseline."""
import ast
from decimal import Decimal
from pathlib import Path
import subprocess

from cn_contract import domain as d
from cn_contract.assistant.providers import main
from cn_contract.assistant.providers.deepseek_protocol import json_bytes, configuration
from tests.integration.test_assistant_main_provider import config, request

BASE='1a7072bb905568a24292a53f3f3133c7c9fbb4f6'


def previous(path):
    return subprocess.check_output(['git','show',BASE+':'+path]).decode('utf-8').replace('\r\n','\n')


def test_existing_domain_definitions_are_byte_identical():
    path='src/cn_contract/domain.py'
    assert Path(path).read_text(encoding='utf-8').startswith(previous(path))


def test_provider_existing_ast_is_identical_except_new_opt_in_method():
    path='src/cn_contract/assistant/providers/main.py'
    old=ast.parse(previous(path)); current=ast.parse(Path(path).read_text(encoding='utf-8'))
    cls=next(n for n in current.body if isinstance(n,ast.ClassDef) and n.name=='DeepSeekProvider')
    cls.body=[n for n in cls.body if getattr(n,'name',None)!='generate_profile']
    assert ast.dump(old,include_attributes=False)==ast.dump(current,include_attributes=False)


def test_ordinary_request_final_bytes_match_baseline_function():
    old=ast.parse(previous('src/cn_contract/assistant/providers/main.py'))
    nodes=[n for n in old.body if (isinstance(n,ast.FunctionDef) and n.name=='build_request')
        or (isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='_SYSTEM' for t in n.targets))]
    namespace={'d':d,'_json_bytes':json_bytes,'_configuration':configuration}
    exec(compile(ast.Module(body=nodes,type_ignores=[]),'<fixed baseline request builder>','exec'),namespace)
    value=request(); settings=config()
    assert json_bytes(namespace['build_request'](value,settings))==json_bytes(main.build_request(value,settings))


def test_shared_manual_money_still_accepts_exact_integer():
    value=d.ProfileEdit(field='principal_amount',value={'kind':'money','value':250,'unit':'CNY'})
    assert value.value.value==Decimal('250')
