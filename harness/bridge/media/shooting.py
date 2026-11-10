"""Validate executable phone instructions, not generated or measured footage."""
from . import domain as d
from .content import validate_dependencies


def validate_shooting_plan(store,value):
    plan=d.MediaShootingPlanSnapshot.model_validate(value)
    validate_dependencies(store,plan.model_dump(mode='json'))
    script=store.load(plan.script_ref,current=True)['value']
    project=store.load(plan.project_ref,current=True)['value']
    if plan.script_ref.kind!='script' or script['project_ref']!=plan.project_ref.model_dump(): raise ValueError('PROJECT_MISMATCH')
    segments={s['id'] for s in script['segments']}; used=set();errors=[]
    if plan.constraints.model_dump()!=project['constraints']: errors.append('CONSTRAINTS_MISMATCH')
    for shot in plan.shots:
        if not set(shot.script_segment_ids)<=segments: errors.append('UNKNOWN_SEGMENT')
        used.update(shot.script_segment_ids)
        if not set(shot.equipment_required)<=set(plan.constraints.equipment): errors.append('MISSING_EQUIPMENT')
        if shot.movement_intent!='static' and (plan.constraints.people_count<2 or plan.constraints.capture_mode=='phone_tripod'):
            errors.append('CREW_REQUIRED')
    if used!=segments: errors.append('MISSING_SEGMENT')
    if len({s.id for s in plan.shots})!=len(plan.shots): errors.append('DUPLICATE_SHOT')
    if sum(s.estimated_duration_ms for s in plan.shots)!=plan.planned_duration_ms or plan.planned_duration_ms!=project['target_duration_ms']:
        errors.append('DURATION_MISMATCH')
    return d.MediaValidationResult(blocking_errors=list(dict.fromkeys(errors)),warnings=['时长为拍摄计划估计，不是音频对齐或实测。'])


def save_plan(store,value,*,entity_id=None,expected_revision=0):
    validation=validate_shooting_plan(store,value)
    if validation.blocking_errors: raise ValueError(','.join(validation.blocking_errors))
    return store.save('shooting_plan',value,entity_id=entity_id,expected_revision=expected_revision)
