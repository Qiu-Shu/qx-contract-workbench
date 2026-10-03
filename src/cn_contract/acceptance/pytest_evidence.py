"""Fixed server plugin recording native collection before any test executes."""
import json
from pathlib import Path


def pytest_addoption(parser):
    parser.addoption('--cn-collection-evidence', action='store', default=None)


def pytest_collection_finish(session):
    target = session.config.getoption('--cn-collection-evidence')
    if target is None:
        return
    data = {'nodeids': [item.nodeid for item in session.items]}
    # A fresh runner directory owns this one-shot evidence file. This plugin
    # name and option are fixed in the server argv, never selected by case data.
    with Path(target).open('xb') as stream:
        stream.write((json.dumps(data, ensure_ascii=False)+'\n').encode('utf-8'))
