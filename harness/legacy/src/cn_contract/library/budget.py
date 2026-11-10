"""Cooperative resource guards, not OS isolation. Raise at durable boundaries."""
import ctypes
import os
from pathlib import Path
import shutil
import time

GIB = 1024 ** 3
_last = {}


def process_bytes():
    if os.name == 'nt':
        from ctypes import wintypes
        class Counters(ctypes.Structure):
            _fields_ = [('cb', wintypes.DWORD), ('PageFaultCount', wintypes.DWORD)] + [
                (name, ctypes.c_size_t) for name in ('PeakWorkingSetSize', 'WorkingSetSize',
                'QuotaPeakPagedPoolUsage', 'QuotaPagedPoolUsage', 'QuotaPeakNonPagedPoolUsage',
                'QuotaNonPagedPoolUsage', 'PagefileUsage', 'PeakPagefileUsage', 'PrivateUsage')]
        counters = Counters()
        counters.cb = ctypes.sizeof(counters)
        current = ctypes.windll.kernel32.GetCurrentProcess
        current.restype = wintypes.HANDLE
        get_memory = ctypes.windll.psapi.GetProcessMemoryInfo
        get_memory.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
        if not get_memory(current(), ctypes.byref(counters), counters.cb):
            raise OSError('MEMORY_MEASUREMENT_FAILED')
        return max(counters.WorkingSetSize, counters.PrivateUsage)
    try:
        return int(Path('/proc/self/statm').read_text().split()[1]) * os.sysconf('SC_PAGE_SIZE')
    except (FileNotFoundError, AttributeError):
        import resource
        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * (1 if sys_platform_mac() else 1024)


def sys_platform_mac():
    import sys
    return sys.platform == 'darwin'


def check_budget(root, *, additional_bytes=0, force=False):
    root = Path(root)
    if not force and not additional_bytes and time.monotonic() - _last.get(str(root), -100) < 5:
        return
    existing = root
    while not existing.exists():
        existing = existing.parent
    if shutil.disk_usage(existing).free < 40 * GIB + additional_bytes:
        raise ValueError('LIBRARY_DISK_BUDGET')
    if process_bytes() > 8 * GIB:
        raise ValueError('LIBRARY_MEMORY_BUDGET')
    derived = 0
    # Asset bytes have their own free-space guard and are not derived-index bytes.
    for directory, folders, files in os.walk(root, followlinks=False):
        if Path(directory) == root:
            folders[:] = [name for name in folders if name != 'assets']
        for name in files:
            derived += (Path(directory) / name).stat().st_size
    if derived > 200 * GIB:
        raise ValueError('LIBRARY_DERIVED_BUDGET')
    _last[str(root)] = time.monotonic()
