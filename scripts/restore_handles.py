"""Read-only, best-effort Windows development diagnostics for this process only.

The internal NtQueryInformationProcess class/layout is not a stable Windows API.
Unsupported APIs, unresolved disk handles and snapshot races fail the scan; an
empty successful snapshot cannot establish the absence of external locks.
Non-disk/unknown handle types are skipped. The snapshot is not atomic: handles
may close or be reused while examined, so success only means sampling finished.
"""
import ctypes
from ctypes import wintypes
import os
from pathlib import Path


class _Entry(ctypes.Structure):
    _fields_ = [('value', ctypes.c_void_p), ('handle_count', ctypes.c_size_t),
        ('pointer_count', ctypes.c_size_t), ('access', wintypes.ULONG),
        ('type_index', wintypes.ULONG), ('attributes', wintypes.ULONG), ('reserved', wintypes.ULONG)]


def _absolute(path):
    value = os.fsdecode(os.fspath(path))
    if os.name == 'nt':
        if value[:8].casefold() == '\\\\?\\unc\\':
            value = '\\\\'+value[8:]
        elif value.startswith('\\\\?\\'):
            value = value[4:]
    return Path(os.path.abspath(value))


def own_process_handles(stage):
    """Return only stage-relative disk paths; never query another process."""
    if os.name != 'nt':
        raise RuntimeError('Windows diagnostic scan unavailable')
    stage = _absolute(stage)
    ntdll = ctypes.WinDLL('ntdll')
    query = ntdll.NtQueryInformationProcess
    query.argtypes = [wintypes.HANDLE, wintypes.ULONG, ctypes.c_void_p, wintypes.ULONG, ctypes.POINTER(wintypes.ULONG)]
    query.restype = wintypes.LONG
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    final = kernel.GetFinalPathNameByHandleW
    final.argtypes = [wintypes.HANDLE, wintypes.LPWSTR, wintypes.DWORD, wintypes.DWORD]
    final.restype = wintypes.DWORD
    file_type = kernel.GetFileType
    file_type.argtypes = [wintypes.HANDLE]
    file_type.restype = wintypes.DWORD
    length = wintypes.ULONG()
    capacity = 16384
    while True:
        data = ctypes.create_string_buffer(capacity)
        status = query(wintypes.HANDLE(-1), 51, data, capacity, ctypes.byref(length))
        if status == 0:
            break
        if status & 0xffffffff not in (0xc0000004, 0x80000005):
            raise OSError('Process handle snapshot unavailable')
        capacity = max(capacity*2, length.value)
        if capacity > 16*1024*1024:
            raise RuntimeError('Process handle snapshot limit')
    count = ctypes.c_size_t.from_buffer(data).value
    offset = 2*ctypes.sizeof(ctypes.c_size_t)
    if not offset <= length.value <= capacity or offset+count*ctypes.sizeof(_Entry) > length.value:
        raise RuntimeError('Invalid process handle snapshot')
    found = []
    for index in range(count):
        entry = _Entry.from_buffer(data, offset+index*ctypes.sizeof(_Entry))
        kind = file_type(wintypes.HANDLE(entry.value))
        if kind != 1:
            continue
        name = ctypes.create_unicode_buffer(32768)
        size = final(wintypes.HANDLE(entry.value), name, len(name), 0)
        if not 0 < size < len(name):
            raise OSError('Process disk handle path unavailable')
        path = _absolute(name.value)
        if path.is_relative_to(stage):
            found.append({'handle':entry.value, 'path':path.relative_to(stage).as_posix(), 'access':hex(entry.access)})
    return found
