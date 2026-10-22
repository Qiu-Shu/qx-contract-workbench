"""Independent synthetic Standards probes; no product database or real original."""
from pathlib import Path
import subprocess
import sys
import traceback

import pytest
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'tests' / 'integration'))
from test_assistant_storage import workspace
from test_assistant_attachments import material_workspace
from test_assistant_profile_sources import parsed_source
from cn_contract.assistant.profile_sources import read_profile_sources
from cn_contract.security import ServiceError


@pytest.mark.parametrize('raw', ['null', '7', '{"synthetic-private-marker": [1]}'])
def test_malformed_material_shape_is_redacted(material_workspace, raw):
    database, actors, *_ = material_workspace
    proposal, _ = parsed_source(material_workspace)
    with database.session() as db:
        db.execute(text('DROP TRIGGER immutable_assistant_material_snapshots_update'))
        db.execute(text('UPDATE assistant_material_snapshots SET items_json=:raw'), {'raw':raw})
    with pytest.raises(ServiceError) as error:
        read_profile_sources(actors['lawyer'], proposal, database=database)
    assert error.value.code == 'VERSION_CONFLICT'
    assert str(error.value) == 'request blocked'
    assert 'synthetic-private-marker' not in ''.join(traceback.format_exception(error.value))


@pytest.mark.parametrize('table,column,trigger,raw', [
    ('assistant_attachment_parses', 'result_json', 'immutable_assistant_attachment_parses_update', '{"synthetic-private-marker":'),
    ('assistant_attachments', 'policy_json', 'immutable_assistant_attachments_update', '{"synthetic-private-marker":"not-a-policy"}'),
])
def test_malformed_attachment_metadata_is_redacted(material_workspace, table, column, trigger, raw):
    database, actors, *_ = material_workspace
    proposal, _ = parsed_source(material_workspace)
    with database.session() as db:
        db.execute(text('DROP TRIGGER ' + trigger))
        db.execute(text('UPDATE ' + table + ' SET ' + column + '=:raw'), {'raw':raw})
    with pytest.raises(ServiceError) as error:
        read_profile_sources(actors['lawyer'], proposal, database=database)
    assert error.value.code == 'VERSION_CONFLICT'
    assert str(error.value) == 'request blocked'
    assert 'synthetic-private-marker' not in ''.join(traceback.format_exception(error.value))


@pytest.mark.parametrize('ref', ['../synthetic-private-marker/original.bin', 'C:/synthetic-private-marker/original.bin'])
def test_altered_original_path_does_not_open_other_file(material_workspace, monkeypatch, ref):
    from cn_contract.assistant import attachment_files
    database, actors, *_ = material_workspace
    proposal, _ = parsed_source(material_workspace)
    with database.session() as db:
        db.execute(text('DROP TRIGGER immutable_assistant_attachments_update'))
        db.execute(text('UPDATE assistant_attachments SET storage_ref=:ref'), {'ref':ref})
    def forbidden_read(*args):
        raise AssertionError('tampered path reached file I/O')
    monkeypatch.setattr(attachment_files, 'checked_file', forbidden_read)
    with pytest.raises(ServiceError) as error:
        read_profile_sources(actors['lawyer'], proposal, database=database)
    assert error.value.code == 'VERSION_CONFLICT'


def test_cold_import_has_no_parser_web_or_provider(material_workspace):
    result = subprocess.run([sys.executable, '-X', 'utf8', '-c',
        'import sys; import cn_contract.assistant.profile_sources; '
        'assert "docx" not in sys.modules; '
        'assert not any(n.startswith(("cn_contract.web.", "cn_contract.parsers.", "cn_contract.assistant.providers.")) for n in sys.modules)'],
        capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
