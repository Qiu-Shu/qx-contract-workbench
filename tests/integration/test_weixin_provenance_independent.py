"""Public provenance validation must independently verify its complete parents."""
import pytest
from sqlalchemy import text

from cn_contract.weixin_inbox.provenance_integrity import validate_descriptor_generations
from tests.helpers.synthetic_weixin_generation_service import append
from tests.helpers.synthetic_weixin_generations import setup_history
from tests.helpers.synthetic_weixin_provenance import chain, snapshot
from tests.integration.test_weixin_dispatch_integrity import corrupt
from tests.integration.test_weixin_generation_integrity import rehash_generation
from tests.integration.test_weixin_ingress_atomic import world
from tests.integration.test_weixin_provenance import rewrite


@pytest.mark.parametrize('with_sources', [False, True])
def test_public_provenance_checks_rehashed_parent_chain_even_without_sidecars(world, with_sources):
    if with_sources:
        history = chain(world)
        generation = history['second']
    else:
        history = setup_history(world)
        generation = append(history)
    database = history['database']
    with database.session() as db:
        assert validate_descriptor_generations(db, allow_provenance=True) == []
        corrupt(db, 'UPDATE weixin_peer_generations SET previous_scope_sha256=:sha WHERE id=:id',
            {'id':str(generation.id), 'sha':'f'*64})
        rehash_generation(db, generation.id)
        if with_sources:
            changed = db.scalar(text('SELECT generation_sha256 FROM weixin_peer_generations WHERE id=:id'),
                {'id':str(generation.id)})
            rewrite(db, history['two'][1].id, generation_sha256=changed)
    before = snapshot(database)
    with database.session() as db, pytest.raises(ValueError, match='WEIXIN_PROVENANCE_INTEGRITY'):
        validate_descriptor_generations(db, allow_provenance=True)
    assert snapshot(database) == before
