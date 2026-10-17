"""Windows extended paths only at file I/O boundaries; logical refs stay portable."""
import os
from pathlib import Path


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
