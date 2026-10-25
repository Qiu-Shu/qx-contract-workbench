"""Windows extended paths only at file I/O boundaries; logical refs stay portable."""
import os
from pathlib import Path
from urllib.parse import quote


def filesystem_path(value):
    path = Path(os.path.abspath(value))
    if os.name != 'nt':
        return path
    name = str(path)
    if name.startswith('\\\\?\\'):
        return path
    if name.startswith('\\\\'):
        return Path('\\\\?\\UNC\\'+name[2:])
    return Path('\\\\?\\'+name)


def application_path(value):
    """Keep Windows filesystem namespace prefixes out of stored/application paths."""
    name = str(value)
    if os.name == 'nt':
        if name.startswith('\\\\?\\UNC\\'):
            return Path('\\\\'+name[8:])
        if name.startswith('\\\\?\\'):
            return Path(name[4:])
    return Path(value)


def sqlite_readonly_uri(value):
    """Encode the native filename, retaining the Windows extended namespace."""
    return 'file:'+quote(str(filesystem_path(value)),safe='/:')+'?mode=ro'
