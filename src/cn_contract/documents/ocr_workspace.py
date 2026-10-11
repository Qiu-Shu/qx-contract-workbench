"""Bounded, non-following cleanup of this invocation's temporary OCR directory."""
import os,re,shutil,stat
from .pdfjs_assets import _regular
from ..security import ServiceError

PREFIX='managed-'


def require_ready(parent):
    _regular(parent,directory=True)
    with os.scandir(parent) as entries:
        for count,entry in enumerate(entries,1):
            if count>4096 or entry.name.startswith(PREFIX):
                raise ServiceError('OCR_CLEANUP_REQUIRED',503)
    if shutil.disk_usage(parent).free<256*1024**2:
        raise ServiceError('OCR_STORAGE_LIMIT',503)


def require_budget(work,parent):
    try:entries=inventory(work,parent)
    except (OSError,ValueError):raise ServiceError('OCR_STORAGE_LIMIT',503) from None
    if len(entries)>256 or sum(size for _,directory,size in entries if not directory)>128*1024**2:
        raise ServiceError('OCR_STORAGE_LIMIT',503)


def inventory(work,parent):
    _regular(parent,directory=True)
    if (not parent.is_absolute() or work.parent!=parent
        or re.fullmatch(r'managed-[0-9a-f]{32}',work.name) is None
        or work.resolve(strict=True).parent!=parent.resolve(strict=True)):
        raise ValueError('job boundary')
    _regular(work,directory=True)
    entries=[];pending=[(work,0)]
    while pending:
        directory,depth=pending.pop()
        if depth>16:raise ValueError('job depth')
        with os.scandir(directory) as children:
            for child in children:
                path=directory/child.name;info=child.stat(follow_symlinks=False)
                is_directory=stat.S_ISDIR(info.st_mode)
                _regular(path,directory=is_directory)
                entries.append((path,is_directory,info.st_size))
                if len(entries)>4096:raise ValueError('job entries')
                if is_directory:pending.append((path,depth+1))
    return entries


def cleanup(work,parent):
    """Never accept a caller-selected root or delete historical jobs."""
    try:
        entries=inventory(work,parent)
        for path,is_directory,_ in sorted(entries,key=lambda item:len(item[0].parts),reverse=True):
            _regular(path,directory=is_directory)
            if is_directory:path.rmdir()
            else:path.unlink()
        _regular(work,directory=True);work.rmdir()
    except (OSError,ValueError):
        raise ServiceError('OCR_CLEANUP_REQUIRED',503) from None
