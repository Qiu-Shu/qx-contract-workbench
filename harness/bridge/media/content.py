"""References are program-checked; legal judgment remains with the reviewer."""
import re

from . import domain as d


def references(value):
    if isinstance(value,dict):
        if set(value)=={'kind','entity_id','revision','content_sha256'}:
            yield d.MediaRevisionRef.model_validate(value)
        else:
            for item in value.values(): yield from references(item)
    elif isinstance(value,list):
        for item in value: yield from references(item)


def validate_dependencies(store,value):
    for ref in references(value):
        row=store.load(ref,current=True)
        if ref.kind=='memory' and row['value']['confirmation']!='confirmed':
            raise ValueError('MEMORY_NOT_PUBLIC')


def validate_brief(store,brief):
    validate_dependencies(store,brief)
    project=store.load(brief['project_ref'],current=True)['value']
    if project['profile_ref']!=brief['profile_ref']: raise ValueError('PROFILE_MISMATCH')
    for claim in brief['claims']:
        source=store.load(claim['source_ref'],current=True)['value']
        if claim['source_ref']['kind']!='source' or source['content_scope']=='metadata' or claim['evidence_quote'] not in source['text']:
            raise ValueError('NO_EVIDENCE')
        if claim['status']=='confirmed' and source['verification']!='verified': raise ValueError('UNVERIFIED_SOURCE')
    for ref in brief['memory_refs']:
        memory=store.load(ref,current=True)['value']
        if ref['kind']!='memory' or memory['profile_ref']['entity_id']!=brief['profile_ref']['entity_id']:
            raise ValueError('MEMORY_PROFILE_MISMATCH')


def validate_script(store,value):
    script=d.MediaScriptSnapshot.model_validate(value).model_dump(mode='json')
    validate_dependencies(store,script)
    brief=store.load(script['brief_ref'],current=True)['value']
    if script['brief_ref']['kind']!='brief' or brief['project_ref']!=script['project_ref']:
        raise ValueError('PROJECT_MISMATCH')
    validate_brief(store,brief)
    claims={claim['id']:claim for claim in brief['claims']}
    allowed_memories={ref['entity_id']:ref for ref in brief['memory_refs']}
    errors=[]
    for segment in script['segments']:
        if segment['kind'] in ('fact','law') and not segment['claim_refs']: errors.append('MISSING_CLAIM')
        for identifier in segment['claim_refs']:
            claim=claims.get(identifier)
            if claim is None: errors.append('UNKNOWN_CLAIM'); continue
            if claim['status']!='confirmed': errors.append('UNCONFIRMED_CLAIM')
            if segment['kind']=='law' and (claim['kind']!='law' or claim['law_status']!='effective' or not claim['law_name'] or not claim['applicability']):
                errors.append('LAW_NOT_EFFECTIVE')
        for ref in segment['memory_refs']:
            if allowed_memories.get(ref['entity_id'])!=ref: errors.append('UNKNOWN_MEMORY'); continue
            memory=store.load(ref,current=True)['value']
            if memory['category'] in ('style_sample','client_question'): errors.append('NOT_PERSONAL_EXPERIENCE')
        if re.search(r'我(?:曾|办过|代理过|处理过|亲历|经历过)',segment['text']) and not segment['memory_refs']:
            errors.append('UNCONFIRMED_EXPERIENCE')
    if len({s['id'] for s in script['segments']})!=len(script['segments']): errors.append('DUPLICATE_SEGMENT')
    if brief['pending']: errors.append('PENDING_FACTS')
    return d.MediaValidationResult(blocking_errors=list(dict.fromkeys(errors)),
        warnings=['程序核对引用与版本，语义及法律适用仍须律师审阅。'])


def save_content(store,kind,value,*,entity_id=None,expected_revision):
    value=d.INPUT_MODELS[kind].model_validate(value).model_dump(mode='json')
    if kind=='brief': validate_brief(store,value)
    elif kind=='script': validate_script(store,value)
    else: raise ValueError('UNKNOWN_CONTENT_KIND')
    return store.save(kind,value,entity_id=entity_id,expected_revision=expected_revision)
