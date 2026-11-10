"""Private answers are preserved; only explicit confirmation releases a version."""

from . import domain as d


def add_memory(store,profile_ref,category,original,*,summary=None):
    store.load(profile_ref,current=True)
    return store.save('memory',dict(profile_ref=profile_ref.model_dump(),category=category,
        original=original,summary=summary if summary is not None else original,confirmation='unconfirmed'),expected_revision=0)


def confirm_memory(store,ref):
    row=store.load(ref,current=True)
    if ref.kind!='memory': raise ValueError('REFERENCE_MISMATCH')
    profile=next(r for r in store.list('profile') if r['ref']['entity_id']==row['value']['profile_ref']['entity_id'])
    return store.save('memory',{**row['value'],'profile_ref':profile['ref'],'confirmation':'confirmed'},entity_id=ref.entity_id,expected_revision=ref.revision)


def revoke_memory(store,ref):
    row=store.load(ref,current=True)
    if ref.kind!='memory': raise ValueError('REFERENCE_MISMATCH')
    return store.save('memory',{**row['value'],'confirmation':'revoked'},entity_id=ref.entity_id,expected_revision=ref.revision,
                      visibility='owner_only')


def public_memories(store,profile_ref,*,include_style=False):
    store.load(profile_ref,current=True)
    return [row for row in store.list('memory') if row['value']['profile_ref']==profile_ref.model_dump()
            and row['value']['confirmation']=='confirmed' and
            (include_style or row['value']['category'] not in ('style_sample','client_question'))]
