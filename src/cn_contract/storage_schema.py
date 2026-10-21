"""Fixed supported SQLite structures, independent of application initialization."""
from .assistant.context_schema import FAMILY_TABLES as _CONTEXT_FAMILY_TABLES
from .assistant.context_schema import expected_objects as context_objects
from .assistant.library_schema import expected_objects as library_objects
from .assistant.rounds_schema import expected_objects as rounds_objects
from .assistant.rounds_v2_schema import expected_objects as rounds_v2_objects
from .assistant_judge_schema_baseline import ASSISTANT_JUDGE_V1_ROWS
from .assistant_model_schema_baseline import ASSISTANT_MODEL_V1_ROWS
from .assistant_attachment_schema_baseline import ASSISTANT_ATTACHMENTS_V1_ROWS
from .assistant_schema_baseline import ASSISTANT_V1_ROWS
from .schema_baseline import INTAKE_V1_ROWS


CURRENT_VERSION = 'assistant-rounds-v2'
VERSIONS = ('pre-intake', 'intake-v1', 'assistant-v1', 'assistant-attachments-v1', 'assistant-model-v1', 'assistant-judge-v1', 'assistant-library-v1', 'assistant-context-v1', 'assistant-rounds-v1', CURRENT_VERSION)
SUPPORTED_VERSIONS = VERSIONS
_INTAKE_TABLES = frozenset(('intake_cases', 'intake_revisions'))
_LIBRARY_ROWS = tuple(library_objects())
_CONTEXT_ROWS = tuple(context_objects())
_ROUNDS_ROWS = tuple(rounds_objects())
_ROUNDS_V2_ROWS = tuple(rounds_v2_objects())
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
    if version in VERSIONS[2:]:
        result.extend(ASSISTANT_V1_ROWS)
    if version in VERSIONS[3:]:
        result.extend(ASSISTANT_ATTACHMENTS_V1_ROWS)
    if version in VERSIONS[4:]:
        result.extend(ASSISTANT_MODEL_V1_ROWS)
    if version in VERSIONS[5:]:
        result.extend(ASSISTANT_JUDGE_V1_ROWS)
    if version in VERSIONS[6:]:
        result.extend(_LIBRARY_ROWS)
    if version in ('assistant-context-v1', 'assistant-rounds-v1', 'assistant-rounds-v2'):
        # The context migration alters the model family in place; replace its
        # frozen V1 rows with the exact migrated structure. The two rounds
        # rebuilds replace the attempts table once more on top of that.
        result = [row for row in result if row[2] not in _CONTEXT_FAMILY_TABLES]
        result.extend(_CONTEXT_ROWS if version == 'assistant-context-v1'
                      else _ROUNDS_ROWS if version == 'assistant-rounds-v1'
                      else _ROUNDS_V2_ROWS)
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
