"""Explicit storage composition shared by HTTP, acceptance and backup tools."""


def initialize_storage(database):
    from sqlalchemy import text
    from .storage_schema import identify_schema, VERSIONS
    with database.session() as db:
        rows = [tuple(row) for row in db.execute(text('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name'))]
    try:
        version = identify_schema(rows,native=any(row[1]=='local_workspace_identity' for row in rows))
    except ValueError:
        version = None
    # weixin-personal-v1 及其之后的版本都含表重建迁移。已经落在这一段里的库不能再
    # 走一遍完整初始化链：那条链上的族校验（如 task_drafts）比的是各族建表语句的
    # 原始形态，而 personal / runtime / knowledge 的重建已经把那几张表（例如
    # task_channel_bindings）改写成带引号的新形态，重跑必然报 DATABASE_SCHEMA_MISMATCH。
    # 这里按版本序号判断，而不是列举版本名——后续再加版本时不会漏。
    if version is not None and VERSIONS.index(version) >= VERSIONS.index('weixin-personal-v1'):
        # 统一交给 schema_migrations：它对 CURRENT_VERSION 直接返回，对旧版本
        # 走带 FK OFF 窗口与前后哈希核对的原子链式升级，重复调用安全。
        from .weixin_inbox.personal_schema import initialize_storage as upgrade
        upgrade(database)
        mark_storage_initialized(database)
        return
    # Existing families keep their order; versioned extensions are additive.
    from .authorities.storage import initialize_storage as authorities
    from .rules.storage import initialize_storage as rules
    from .facts.storage import initialize_storage as facts
    from .review.storage import initialize_storage as reviews
    from .providers.storage import initialize_storage as providers
    from .queries.storage import initialize_storage as queries
    from .exports.storage import initialize_storage as exports
    from .web.storage import initialize_storage as jobs
    from .ops.storage import initialize_storage as operations
    from .documents.proofreading import initialize_storage as proofreading
    from .documents.ocr_candidates import initialize_storage as ocr_candidates
    from .intake.schema import initialize_storage as intake
    from .assistant.schema import initialize_storage as assistant
    from .assistant.attachment_schema import initialize_storage as attachments
    from .assistant.model_schema import initialize_storage as model
    from .assistant.judge_schema import initialize_storage as judge
    from .assistant.library_schema import initialize_storage as library
    from .assistant.context_schema import initialize_storage as context
    from .assistant.rounds_schema import initialize_storage as rounds
    from .assistant.rounds_v2_schema import initialize_storage as rounds_v2
    from .assistant.profile_schema import initialize_storage as profiles
    from .assistant.profile_model_schema import initialize_storage as profile_model
    from .task_drafts.schema import initialize_storage as task_drafts
    from .weixin_inbox.schema import initialize_storage as weixin_inbox
    from .weixin_inbox.dispatch_schema import initialize_storage as weixin_dispatch
    from .weixin_inbox.grant_schema import initialize_storage as weixin_grant
    from .weixin_inbox.generation_schema import initialize_storage as weixin_generation
    from .weixin_inbox.provenance_schema import initialize_storage as weixin_provenance
    from .weixin_inbox.generation_dispatch_schema import initialize_storage as weixin_generation_dispatch
    from .assistant.evidence_schema import initialize_storage as evidence
    from .assistant.followup_schema import initialize_storage as followups
    from .assistant.material_model_schema import initialize_storage as material_model
    from .weixin_inbox.personal_schema import initialize_storage as personal
    # 注意：assistant-knowledge-v1 不在这里就地加宽回执表。初始化链只建到
    # weixin-personal-v1 之前的结构，personal(database) 再交给 schema_migrations
    # 从 personal-v1 一路链式升到 CURRENT_VERSION；knowledge 的加宽是那条链上的
    # 一步。若在链中段先加宽，会出现"旧版本结构 + 新回执表"的混合形态，
    # identify_schema 认不出任何版本，整条升级链直接失败。
    for init in (authorities, rules, facts, reviews, providers, queries, exports,
                 jobs, operations, proofreading, ocr_candidates, intake, assistant, attachments, model, judge, library, context, rounds, rounds_v2, profiles, profile_model, task_drafts, weixin_inbox, weixin_dispatch, weixin_grant, weixin_generation, weixin_provenance, weixin_generation_dispatch, evidence, followups, material_model):
        init(database)
    personal(database)


def mark_storage_initialized(database):
    """After exact schema validation, enable existing services without DDL."""
    for prefix in ('authorities', 'rules', 'facts', 'review', 'provider', 'query',
                   'export', 'web', 'ops'):
        setattr(database, '_' + prefix + '_storage_initialized', True)
