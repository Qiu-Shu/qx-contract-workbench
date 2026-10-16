"""Explicit storage composition shared by HTTP, acceptance and backup tools."""


def initialize_storage(database):
    # Keep registration order and DDL identical to the existing intake-v1 schema.
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
    for init in (authorities, rules, facts, reviews, providers, queries, exports,
                 jobs, operations, proofreading, ocr_candidates, intake):
        init(database)
