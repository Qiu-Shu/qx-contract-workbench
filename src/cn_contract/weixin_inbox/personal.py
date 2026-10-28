"""Trusted native-runtime services; no HTTP routes or transport credentials.

The caller authenticates the remote bot and its one private peer before binding.
Only the current backend principal and stored exact target determine authority.
"""
from uuid import uuid4

from sqlalchemy import text

from .. import domain as d
from ..assistant.service import _at, _current, _snapshot, _workspace_id
from ..ops.storage import require_active
from ..security import ServiceError
from ..storage_schema import identify_schema
from ..task_drafts import service as tasks
from . import accounts, dispatch, generation_dispatch, ingress

MODE = 'weixin_personal'


def _validate(db):
    rows = [tuple(row) for row in db.execute(text('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name'))]
    try:
        if identify_schema(rows,native=True) not in ('weixin-personal-v1', 'weixin-personal-runtime-v1'):
            raise ValueError('personal schema required')
    except ValueError:
        raise ServiceError('VERSION_CONFLICT',409) from None
    generation_dispatch._validate(db)


def bind_personal_peer(actor, request, *, sender_peer_id, expected_scope, database):
    """Atomically bind confirmed bot/peer to one exact owned conversation.

    Returns (WeixinAccountSnapshot, WeixinPeerBindingSnapshot). Reconnection may
    recover the same pair; another owner, peer or target never replaces it.
    request is WeixinAccountCreateInput, expected_scope is ScopeSnapshot.
    """
    request = d.WeixinAccountCreateInput.model_validate(request.model_dump(mode='python'))
    expected_scope = d.ScopeSnapshot.model_validate(expected_scope.model_dump(mode='python'))
    sender_peer_id = d.WeixinPeerBindInput(sender_peer_id=sender_peer_id,
        task_binding_id=uuid4(),expected_scope=expected_scope).sender_peer_id
    with accounts._transaction(database) as db:
        current = _current(actor,db)
        require_active(db)
        _validate(db)
        workspace = _workspace_id(db)
        conversation = tasks._write(current,expected_scope.conversation_id,db)
        if _snapshot(conversation) != expected_scope:
            raise ServiceError('VERSION_CONFLICT',409)
        previous = db.scalar(text('SELECT id FROM weixin_accounts WHERE workspace_id=:workspace AND bot_account_id=:bot'),
            {'workspace':str(workspace),'bot':request.bot_account_id})
        if previous is None:
            account = d.WeixinAccountSnapshot(id=uuid4(),workspace_id=workspace,owner_id=current.user_id,
                bot_account_id=request.bot_account_id,mode=MODE,initial_cursor=request.initial_cursor,
                checkpoint_revision=0,upstream_cursor=request.initial_cursor,created_at=_at())
            ingress._insert('weixin_accounts',account.model_dump(mode='json'),db)
        else:
            account,current = accounts._account(current,previous,db,mode=MODE)
            if account.initial_cursor != request.initial_cursor:
                raise ServiceError('VERSION_CONFLICT',409)
        binding = tasks._create_binding(current,expected_scope.conversation_id,db,channel=MODE)
        prior = db.execute(text('SELECT * FROM weixin_peer_bindings WHERE account_id=:id'),
            {'id':str(account.id)}).mappings().all()
        if prior and (len(prior)!=1 or prior[0]['sender_peer_id']!=sender_peer_id
                or prior[0]['task_binding_id']!=str(binding.id)):
            raise ServiceError('VERSION_CONFLICT',409)
        if prior:
            mapping = accounts._mapping(prior[0])
            if accounts._effective_scope(mapping,db)!=expected_scope:
                raise ServiceError('VERSION_CONFLICT',409)
            accounts._require_mapping(accounts._mapping_reason(current,account,mapping,db))
        else:
            mapping = accounts._bind_in_transaction(current,account,d.WeixinPeerBindInput(
                sender_peer_id=sender_peer_id,task_binding_id=binding.id,expected_scope=expected_scope),db)
        _validate(db)
    return account,mapping


def refresh_personal_peer(actor, mapping_id, request, *, database):
    """Append existing WeixinPeerRefreshInput CAS to same-target grant history."""
    return accounts._refresh_peer(actor,mapping_id,request,database=database,mode=MODE,validator=_validate)


def record_personal_poll(actor, account_id, request, raw_response, *, database):
    """Persist safe descriptors/hash and cursor CAS from raw bytes; never raw secrets.

    Caller must durably register downloaded originals before invoking this method.
    The original wire file descriptors remain pending; later material resolution
    records the registered attachment through existing TaskDraft services.
    """
    request = d.WeixinPollInput.model_validate(request.model_dump(mode='python'))
    with accounts._transaction(database) as db:
        account,current = accounts._account(actor,account_id,db,mode=MODE)
        _validate(db)
        rows = db.execute(text('SELECT * FROM weixin_peer_bindings WHERE account_id=:id'),
            {'id':str(account.id)}).mappings().all()
        if len(rows)!=1:
            raise ServiceError('STATE_CONFLICT',409)
        accounts._require_mapping(accounts._mapping_reason(current,account,accounts._mapping(rows[0]),db))
        receipt = ingress._record_poll(current,account,request,raw_response,db,database)
        _validate(db)
    return receipt


def dispatch_personal_descriptor(actor, account_id, descriptor_id, *, database):
    """Deliver one earliest accepted descriptor, scoped to the caller's account."""
    # Shared delivery retains exact source, scope, dedup and task-cursor checks.
    return dispatch._dispatch_descriptor(actor,descriptor_id,database=database,mode=MODE,
        account_id=account_id,validator=_validate)


def revoke_personal_account(actor, account_id, request, *, database):
    """Persist irreversible account revocation with existing WeixinRevokeInput."""
    return accounts._revoke(actor,account_id,request,database,peer=False,mode=MODE)


def revoke_personal_peer(actor, mapping_id, request, *, database):
    """Persist irreversible fixed-peer revocation with existing WeixinRevokeInput."""
    return accounts._revoke(actor,mapping_id,request,database,peer=True,mode=MODE)
