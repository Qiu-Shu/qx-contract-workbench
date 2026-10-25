"""SQLite must read the exact native filename without creating or changing it."""
from contextlib import closing
from hashlib import sha256
import os
from pathlib import Path
import sqlite3
from urllib.parse import urlsplit

import pytest

from cn_contract.ops import file_paths


def uri(path):
    assert hasattr(file_paths,'sqlite_readonly_uri'),'Shared native SQLite read-only URI is required'
    return file_paths.sqlite_readonly_uri(path)


def create(path, value='independent synthetic sqlite value'):
    native=file_paths.filesystem_path(path)
    native.parent.mkdir(parents=True,exist_ok=True)
    with closing(sqlite3.connect(native)) as db:
        db.execute('CREATE TABLE sample(value TEXT NOT NULL)')
        db.execute('INSERT INTO sample VALUES (?)',(value,));db.commit()
    return native


def read_only(path, expected='independent synthetic sqlite value'):
    native=file_paths.filesystem_path(path);before=sha256(native.read_bytes()).hexdigest()
    with closing(sqlite3.connect(uri(path),uri=True)) as db:
        assert db.execute('SELECT value FROM sample').fetchall()==[(expected,)]
        with pytest.raises(sqlite3.OperationalError,match='readonly'):
            db.execute("INSERT INTO sample VALUES ('forbidden write')")
    assert sha256(native.read_bytes()).hexdigest()==before


@pytest.mark.parametrize('name',['独立 合成.db','literal%23.db','literal#.db','scope&mode=rw.db','percent%25.db','a=b.db','⚖.db'])
def test_special_filename_reads_exact_source_and_denies_writes(tmp_path,name):
    uri(tmp_path/name);create(tmp_path/name);read_only(tmp_path/name)


def test_percent_escape_cannot_alias_another_existing_database(tmp_path):
    uri(tmp_path/'literal%23.db')
    for name,value in [('literal%23.db','percent filename'),('literal#.db','hash filename')]:
        create(tmp_path/name,value)
    read_only(tmp_path/'literal%23.db','percent filename')
    read_only(tmp_path/'literal#.db','hash filename')


@pytest.mark.parametrize('length',[263,317])
@pytest.mark.parametrize('extended',[False,True])
def test_long_windows_filename_reads_without_changing_source(tmp_path,length,extended):
    if os.name!='nt':pytest.skip('Actual Windows namespace and SQLite runtime required')
    uri(tmp_path/'probe.db')
    parent=tmp_path
    while len(str(parent/'sample.db'))<length:
        parent/='中文 合成%23#资料'
    path=parent/'sample.db';create(path)
    assert len(str(path))>=length
    read_only(file_paths.filesystem_path(path) if extended else path)


@pytest.mark.parametrize('long',[False,True])
def test_read_only_missing_database_never_creates_a_file(tmp_path,long):
    uri(tmp_path/'probe.db');parent=tmp_path
    while long and len(str(parent/'missing.db'))<300:
        parent/='独立不存在的合成数据库'
    file_paths.filesystem_path(parent).mkdir(parents=True,exist_ok=True)
    path=parent/'missing.db'
    with pytest.raises(sqlite3.OperationalError):
        sqlite3.connect(uri(path),uri=True)
    assert not file_paths.filesystem_path(path).exists()


def test_relative_filename_is_resolved_before_sqlite_opens_it(tmp_path,monkeypatch):
    uri(tmp_path/'relative.db');create(tmp_path/'relative.db')
    monkeypatch.chdir(tmp_path);read_only(Path('relative.db'))


def test_unc_uri_construction_has_no_authority_or_network_io():
    if os.name!='nt':pytest.skip('Windows namespace construction only')
    value=uri(Path(r'\\independent-invalid-host\synthetic-share\literal%23# sample.db'))
    parsed=urlsplit(value)
    assert parsed.scheme=='file' and parsed.netloc=='' and parsed.query=='mode=ro'
