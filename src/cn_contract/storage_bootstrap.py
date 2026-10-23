"""Explicit storage composition shared by HTTP, acceptance and backup tools."""


def initialize_storage(database):
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
    for init in (authorities, rules, facts, reviews, providers, queries, exports,
                 jobs, operations, proofreading, ocr_candidates, intake, assistant, attachments, model, judge, library, context, rounds, rounds_v2, profiles, profile_model):
        init(database)


def mark_storage_initialized(database):
    """After exact schema validation, enable existing services without DDL."""
    for prefix in ('authorities', 'rules', 'facts', 'review', 'provider', 'query',
                   'export', 'web', 'ops'):
        setattr(database, '_' + prefix + '_storage_initialized', True)
