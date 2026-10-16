"""Fixed supported SQLite structures, independent of application initialization."""
from .assistant.schema import expected_objects as assistant_objects
from .schema_baseline import INTAKE_V1_ROWS


CURRENT_VERSION = 'assistant-v1'
VERSIONS = ('pre-intake', 'intake-v1', CURRENT_VERSION)
SUPPORTED_VERSIONS = VERSIONS
_INTAKE_TABLES = frozenset(('intake_cases', 'intake_revisions'))
_ASSISTANT_ROWS = tuple(assistant_objects())
_IDENTITY_ROWS = (
    ('index', 'sqlite_autoindex_local_workspace_identity_1', 'local_workspace_identity', None),
    ('table', 'local_workspace_identity', 'local_workspace_identity',
     'CREATE TABLE local_workspace_identity (id TEXT PRIMARY KEY NOT NULL)'),
)


def schema_rows(version, *, native=False):
    """Return a fresh exact sqlite_master row list; never initialize an old DB."""
    if version not in VERSIONS:
        raise ValueError('DATABASE_SCHEMA_MISMATCH')
    result = [row for row in INTAKE_V1_ROWS
              if version != 'pre-intake' or row[2] not in _INTAKE_TABLES]
    if version == CURRENT_VERSION:
        result.extend(_ASSISTANT_ROWS)
    if native:
        result.extend(_IDENTITY_ROWS)
    if len({row[1] for row in result}) != len(result):
        raise ValueError('DATABASE_SCHEMA_MISMATCH')
    return sorted(result, key=lambda row: (row[0], row[1]))


def normalized_schema(version, *, native=False):
    """Preserve the existing archive algorithm, distinct from native hashes."""
    return [(kind, name, table, ' '.join(sql.split()))
            for kind, name, table, sql in schema_rows(version, native=native)
            if sql is not None and not name.startswith('sqlite_')]


def identify_schema(rows, *, native=False):
    actual = list(rows)
    for version in VERSIONS:
        if actual == schema_rows(version, native=native):
            return version
    raise ValueError('DATABASE_SCHEMA_MISMATCH')
