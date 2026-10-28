"""Rebuild exact historical source tables in synthetic-only test fixtures."""
from cn_contract.task_drafts import schema as tasks
from cn_contract.weixin_inbox import schema as inbox


def _statements(table, schema):
    temporary=table+'_legacy_fixture'
    triggers=[row for row in schema.expected_objects() if row[0]=='trigger' and row[2]==table]
    return ('CREATE TABLE '+temporary+' AS SELECT * FROM '+table,
        *('DROP TRIGGER '+row[1] for row in triggers), 'DROP TABLE '+table,
        schema.STATEMENTS[0], 'INSERT INTO '+table+' SELECT * FROM '+temporary,
        'DROP TABLE '+temporary, *(row[3] for row in triggers))


def downgrade_statements(execute):
    statements=()
    for table,column,schema in (('task_channel_bindings','channel',tasks),('weixin_accounts','mode',inbox)):
        row=execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='"+table+"'").fetchone()
        if row is None or 'weixin_personal' not in row[0]:continue
        if execute("SELECT 1 FROM "+table+" WHERE "+column+"!='synthetic' LIMIT 1").fetchone():
            raise ValueError('synthetic-only historical fixture required')
        statements+=_statements(table,schema)
    return statements


def downgrade_runtime_statements(execute):
    """Remove later personal-runtime objects from synthetic pre-material fixtures."""
    statements=()
    for name in ('weixin_personal_runs_no_update','weixin_personal_runs_no_delete',
                 'weixin_personal_outbox_no_delete','weixin_personal_outbox_update'):
        if execute("SELECT 1 FROM sqlite_master WHERE type='trigger' AND name='"+name+"'").fetchone():
            statements+=('DROP TRIGGER '+name,)
    for name in ('weixin_personal_outbox','weixin_personal_runs'):
        if execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='"+name+"'").fetchone():
            statements+=('DROP TABLE '+name,)
    return statements
