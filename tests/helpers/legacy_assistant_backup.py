"""Independent fictional old databases built from frozen 0.4.1 DDL, not new tables."""
from contextlib import closing
from datetime import datetime, timezone
from io import BytesIO
import json
from pathlib import Path
import sqlite3
from uuid import uuid4
from zipfile import ZipFile, ZIP_STORED

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from cn_contract.config import load_settings
from cn_contract.domain import Matter, Role, UploadMeta, IntakeCreateInput, IntakeDraft
from cn_contract.persistence import Database, provision_matter
from cn_contract.schema_baseline import INTAKE_V1_ROWS
from cn_contract.security import provision_user, login, authenticate
from cn_contract.review.synthetic import select_fixture
from cn_contract.documents import ingest
from cn_contract.ops import backup

USERNAME = '旧版合成律师'
PASSWORD = 'fiction123'
PASSPHRASE = 'independent-fiction-archive'


def legacy_world(parent, *, native, version='intake-v1', name='old'):
    root = parent/name; root.mkdir(parents=True)
    path = root/('workbench.db' if native else 'database.db')
    rows = [row for row in INTAKE_V1_ROWS
            if version != 'pre-intake' or row[2] not in ('intake_cases', 'intake_revisions')]
    with closing(sqlite3.connect(path)) as connection:
        for kind in ('table', 'index', 'trigger'):
            for row in rows:
                if row[0] == kind and row[3] is not None:
                    connection.execute(row[3])
        if native:
            from cn_contract.web.local_server import _marker, _schema_hash
            marker = {**_marker(), 'workspace_id': str(uuid4())}
            connection.execute('CREATE TABLE local_workspace_identity (id TEXT PRIMARY KEY NOT NULL)')
            connection.execute('INSERT INTO local_workspace_identity VALUES (?)', (marker['workspace_id'],))
            marker['schema_sha256'] = _schema_hash(connection)
            (root/'workspace.json').write_text(json.dumps(marker), encoding='utf-8')
        connection.commit()
    database = Database('sqlite:///'+str(path), root/'protected', load_settings(), initialize_schema=False)
    backup._mark_storage_flags(database)
    with database.session() as db:
        user = provision_user(USERNAME, PASSWORD, {Role.ADMIN, Role.HANDLING_LAWYER}, db,
                              local_workbench_password=True)
        token, _ = login(USERNAME, PASSWORD, db)
        actor = authenticate(token, db)
        matter = Matter(id=uuid4(), client_ref='SYNTHETIC', title='旧版独立虚构材料',
                        jurisdiction='CN-mainland', contract_type='sales', review_mode='pre_sign',
                        position='buyer', objectives=(), member_ids={user}, status='intake',
                        active_fact_version=None, active_policy_version=None, gate_issues=())
        provision_matter(matter, db)
        _, _, name, raw = select_fixture('sales')
        document = ingest(BytesIO(raw), UploadMeta(matter_id=matter.id, original_name=name.name,
            mime='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            baseline_view='original', supersedes_id=None), actor, db=db)
        intake = None
        if version == 'intake-v1':
            from cn_contract.intake.service import create
            intake = create(IntakeCreateInput(request_id=uuid4(), draft=IntakeDraft(
                title='旧版合成接待', consultation='仅为版本恢复测试，非真实咨询。')), actor, db)
    return root, database, actor, matter, document, intake, raw


def write_old_cnbak(database, target):
    """Emit the fixed existing v1 envelope with frozen old-schema records."""
    from tests.helpers.synthetic_operations import keys
    path = Path(database.engine.url.database)
    with database.session() as db:
        files, refs = backup._collect_files(db)
    with closing(sqlite3.connect(path)) as connection:
        schema = backup._schema(connection)
        tables = backup._tables(connection)
    raw = path.read_bytes()
    identifier = str(uuid4())
    manifest = {'version': 1, 'archive_id': identifier, 'synthetic_only': True,
        'created_at': datetime.now(timezone.utc).isoformat(),
        'source_database_sha256': backup.digest(raw), 'schema_sha256': backup.digest(backup.encode(schema)),
        'tables': tables, 'files': refs, 'retention_days': 30, 'latest_external_checkpoint': None,
        'limitations': ['INDEPENDENT_FICTIONAL_DATA_ONLY']}
    buffer = BytesIO()
    with ZipFile(buffer, 'w', compression=ZIP_STORED) as archive:
        archive.writestr('manifest.json', backup.encode(manifest))
        archive.writestr('database.db', raw)
        for name, data in files.items(): archive.writestr(name, data)
    header = backup.encode({'version': 1, 'archive_id': identifier, 'key_ref': 'synthetic-key-1',
                            'synthetic_only': True})
    # Public synthetic fixture key; never production credentials.
    nonce = uuid4().bytes[:12]
    aad = backup.MAGIC+len(header).to_bytes(4, 'big')+header
    target.write_bytes(aad+nonce+AESGCM(keys().resolve('synthetic-key-1')).encrypt(
        nonce, buffer.getvalue(), aad))
