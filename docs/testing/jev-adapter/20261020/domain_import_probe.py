"""Development-only same-process-kind import observation, not a desktop benchmark."""
import ctypes
from ctypes import wintypes
import importlib.util
import json
import sys
from time import perf_counter


class Memory(ctypes.Structure):
    _fields_ = [('cb', wintypes.DWORD), ('PageFaultCount', wintypes.DWORD)] + [
        (n, ctypes.c_size_t) for n in ('PeakWorkingSetSize', 'WorkingSetSize', 'QuotaPeakPagedPoolUsage',
        'QuotaPagedPoolUsage', 'QuotaPeakNonPagedPoolUsage', 'QuotaNonPagedPoolUsage', 'PagefileUsage',
        'PeakPagefileUsage', 'PrivateUsage')]


def memory():
    data = Memory(); data.cb = ctypes.sizeof(data)
    current = ctypes.windll.kernel32.GetCurrentProcess
    current.restype = wintypes.HANDLE
    function = ctypes.windll.psapi.GetProcessMemoryInfo
    function.argtypes = [wintypes.HANDLE, ctypes.POINTER(Memory), wintypes.DWORD]
    if not function(current(), ctypes.byref(data), data.cb): raise ctypes.WinError()
    return {'working_set_bytes': data.WorkingSetSize, 'private_bytes': data.PrivateUsage}


before = memory(); started = perf_counter()
spec = importlib.util.spec_from_file_location('qx_probe_domain', sys.argv[1])
module = importlib.util.module_from_spec(spec);sys.modules[spec.name] = module
spec.loader.exec_module(module)
elapsed = (perf_counter() - started) * 1000; after = memory()
print(json.dumps({'import_ms': round(elapsed,3), 'before': before, 'after': after,
    'delta': {k: after[k]-before[k] for k in before}, 'httpx2_imported': 'httpx2' in sys.modules,
    'model_types': sum(isinstance(v,type) and issubclass(v,module.DomainModel) for v in vars(module).values())}))
