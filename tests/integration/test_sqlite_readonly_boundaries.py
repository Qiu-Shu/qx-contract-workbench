"""Synthetic database readers preserve exact targets and reject writes."""
from contextlib import closing
from hashlib import sha256
import json
import sqlite3

import pytest

from cn_contract.library import catalog, service as library_service
from cn_contract.ops import backup, workspace_backup
from cn_contract.ops.file_paths import filesystem_path
from tests.integration.test_local_workbench import local, PASSWORD
from tests.unit.test_library_search import query, world as library_world


def write_sentinel(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path)) as connection:
        connection.execute('CREATE TABLE sentinel (value TEXT)')
        connection.executemany('INSERT INTO sentinel VALUES (?)', [(value,) for value in rows])
        connection.commit()


@pytest.mark.parametrize('collision', ['filename', 'parent'])
def test_raw_database_validation_reads_literal_percent_filename(tmp_path, collision):
    if collision == 'filename':
        requested, decoy = tmp_path/'literal%23.db', tmp_path/'literal#.db'
    else:
        requested, decoy = tmp_path/'literal%23'/'probe.db', tmp_path/'literal#'/'probe.db'
    write_sentinel(requested, ['requested synthetic row'])
    write_sentinel(decoy, ['unrelated synthetic row one', 'unrelated synthetic row two'])
    before = {path: sha256(path.read_bytes()).hexdigest() for path in (requested, decoy)}

    result = backup.validate_raw_database(requested, None,
        expected_schema=[('table', 'sentinel', 'sentinel', 'CREATE TABLE sentinel (value TEXT)')])

    assert {path: sha256(path.read_bytes()).hexdigest() for path in before} == before
    assert result['sentinel']['count'] == 1
    assert result['sentinel']['sha256'] == sha256(b'[["requested synthetic row"]]').hexdigest()


def deep_directory(path):
    while len(str(path)) < 300:
        path /= '独立合成资料' * 3
    return path


@pytest.fixture
def deep_native(local, tmp_path):
    module, initial = local
    module.initialize_workspace(initial, 'local-lawyer', PASSWORD)
    marker = json.loads((initial/'workspace.json').read_text(encoding='utf-8'))
    destination = deep_directory(tmp_path/'native %23 # & =')
    filesystem_path(destination.parent).mkdir(parents=True)
    filesystem_path(initial).rename(filesystem_path(destination))
    return module, destination, marker


@pytest.mark.parametrize('reader', ['archive_validation', 'workspace_identity'])
def test_native_readers_validate_long_exact_workspace(deep_native, tmp_path, reader):
    module, root, marker = deep_native
    database = filesystem_path(root/'workbench.db')
    before = sha256(database.read_bytes()).hexdigest()

    if reader == 'archive_validation':
        assert workspace_backup._validate_database(filesystem_path(root)) == marker
    else:
        assert module._open_workspace(filesystem_path(root),
            data_parent=filesystem_path(tmp_path)) == filesystem_path(root).resolve()

    assert sha256(database.read_bytes()).hexdigest() == before
    assert json.loads(filesystem_path(root/'workspace.json').read_text(encoding='utf-8')) == marker


@pytest.mark.parametrize('layout', ['special', 'long'])
@pytest.mark.parametrize('reader', ['catalog', 'search'])
def test_library_readers_keep_exact_target_and_readonly(tmp_path, layout, reader):
    original, generation = library_world(tmp_path)
    destination = tmp_path/'library %23 # & ='
    if layout == 'long':
        destination = deep_directory(destination)
    filesystem_path(destination.parent).mkdir(parents=True, exist_ok=True)
    filesystem_path(original).rename(filesystem_path(destination))
    databases = [filesystem_path(destination/'catalog.sqlite'),
                 filesystem_path(destination/'generations'/generation/'search.sqlite')]
    before = {path: sha256(path.read_bytes()).hexdigest() for path in databases}
    library_root = filesystem_path(destination) if layout == 'long' else destination

    if reader == 'catalog':
        with catalog.connection(library_root) as connection:
            assert connection.execute('SELECT COUNT(*) FROM sources').fetchone()[0] == 1
            with pytest.raises(sqlite3.OperationalError, match='readonly'):
                connection.execute('DELETE FROM records')
    else:
        page = library_service.search(library_root, query(text='离婚', kind='case_csv'))
        assert page.generation_id == generation
        assert {hit.title for hit in page.hits} == {'虚构案1', '虚构案2'}

    assert {path: sha256(path.read_bytes()).hexdigest() for path in before} == before
