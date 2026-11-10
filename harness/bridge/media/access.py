"""The caller is bound by the authenticated host, never inferred from content."""


def require_access(actor, entity, *, write=False):
    if entity['workspace_id'] != actor.workspace_id:
        raise PermissionError('ACCESS_DENIED')
    if entity['owner_user_id'] == actor.user_id:
        return
    if not write and entity['visibility'] == 'workspace':
        return
    raise PermissionError('ACCESS_DENIED')
