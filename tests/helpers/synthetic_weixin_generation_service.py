"""Independent public-service generation callers over existing synthetic history."""
import importlib
import importlib.util
from uuid import uuid4

from sqlalchemy import text

from cn_contract import domain as d
from tests.helpers.synthetic_weixin_generations import setup_history, state


def api():
    name='cn_contract.weixin_inbox.generations'
    assert importlib.util.find_spec(name) is not None,'D2g1 needs atomic public generation append/find services'
    return importlib.import_module(name)


def request(history, previous=None, **changes):
    assert hasattr(d,'WeixinPeerGenerationInput'),'D2g1 explicit eight-field input required'
    target,binding=history['targets'][previous.generation if previous else 0]
    with history['database'].session() as db:
        checkpoint=db.scalar(text('SELECT checkpoint_revision FROM weixin_accounts WHERE id=:id'),
            {'id':str(history['account'].id)})
    return d.WeixinPeerGenerationInput(**{**dict(request_id=uuid4(),expected_generation=previous.generation if previous else 0,
        expected_previous_generation_sha256=previous.generation_sha256 if previous else None,
        expected_previous_scope_sha256=previous.scope_sha256 if previous else history['grant'].scope_sha256,
        expected_checkpoint_revision=checkpoint,task_binding_id=binding.id,expected_scope=target.scope,
        reason='独立合成明确追加目标记录；仍保持收件暂停'),**changes})


def append(history, value=None):
    return api().append_synthetic_generation(history['actor'],history['mapping'].id,
        value or request(history),database=history['database'])


def find(history, request_id):
    return api().find_peer_generation(history['actor'],history['mapping'].id,request_id,database=history['database'])


def chain(world):
    history=setup_history(world)
    before=state(history['database'],generations=False)
    first=append(history)
    second=append(history,request(history,first))
    assert state(history['database'],generations=False)==before
    return history,first,second
