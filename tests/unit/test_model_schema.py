"""T06 real raw JSON and bounded local model operations."""
import importlib
import pytest


def api(module, name):
    try:
        target = importlib.import_module('cn_contract.review.' + module)
    except ModuleNotFoundError as exc:
        assert not (exc.name or '').startswith('cn_contract.review'), 'T06 missing controlled service: ' + name
        raise
    result = getattr(target, name, None)
    assert callable(result), 'T06 missing controlled service: ' + name
    return result


@pytest.mark.parametrize('raw', ['{broken', '{"a":1,"a":2}', '{"a":NaN}', '{"a":Infinity}', '[]', '"text"'])
def test_strict_raw_rejects(raw):
    with pytest.raises(ValueError):
        api('model_adapter', 'strict_json')(raw)


def test_raw_size_limit():
    with pytest.raises(ValueError):
        api('model_adapter','strict_json')('{"a":"' + 'x'*262145 + '"}')


def test_raw_requires_text():
    with pytest.raises(ValueError):
        api('model_adapter','strict_json')({'a': 1})


def test_strict_valid_exact_values():
    assert api('model_adapter','strict_json')('{"a":"0.10","b":1}') == {'a':'0.10','b':1}


def test_nonfinite_exponent():
    with pytest.raises(ValueError): api('model_adapter','strict_json')('{"x":1e999}')


@pytest.mark.parametrize('depth',[80,980,1200])
def test_deep_json_is_controlled(depth):
    with pytest.raises(ValueError):api('model_adapter','strict_json')('{"x":'+'['*depth+'0'+']'*depth+'}')


def test_deep_raw_preserves_attempt_usage(tmp_path):
    from tests.helpers.synthetic_review import prepare
    p,s,database,actor,matter,ctx,parsed=prepare(tmp_path)
    raw='{"x":'+'['*980+'0'+']'*980+'}'
    with database.session() as db:
        run=api('workflow','run_review')(ctx,api('model_adapter','MockProvider')(raw_outputs=(raw,raw)),actor=actor,db=db)
        assert run.status=='failed' and run.error_code=='MODEL_OUTPUT_INVALID' and len(run.model_usage)==2


@pytest.mark.parametrize('raw',['{"examined_anchor_ids":[],"facts":[],"observations":[],"Approval":{}}',
    '{"examined_anchor_ids":[],"facts":[],"observations":[{"authority_id":"fake","analysis":"违法"}]}'])
def test_extra_or_arbitrary_claims_rejected(tmp_path,raw):
    from tests.helpers.synthetic_review import prepare
    p,s,database,actor,matter,ctx,parsed=prepare(tmp_path)
    with database.session() as db:
        run=api('workflow','run_review')(ctx,api('model_adapter','MockProvider')(raw_outputs=(raw,raw)),actor=actor,db=db)
        assert run.status=='failed' and run.error_code=='MODEL_OUTPUT_INVALID'
        assert len(run.model_usage)==2 and not run.findings
