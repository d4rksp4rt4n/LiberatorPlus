"""Sample the game's own measured FPS (CVSyncManager: [exe+0x83fe90] -> +0x10 = 1/frametime).
   python -I fpsread.py [seconds]"""
import ctypes as C, sys, time, statistics
from ctypes import wintypes as W
k32, psapi = C.WinDLL('kernel32'), C.WinDLL('psapi')
PROCESS_VM_READ, PROCESS_QUERY_INFORMATION = 0x10, 0x400


def find_pid(name='VD_BHIKKHUNI.exe'):
    arr = (W.DWORD * 4096)(); got = W.DWORD()
    psapi.EnumProcesses(arr, C.sizeof(arr), C.byref(got))
    for pid in arr[:got.value // 4]:
        h = k32.OpenProcess(PROCESS_VM_READ | PROCESS_QUERY_INFORMATION, False, pid)
        if not h: continue
        buf = C.create_unicode_buffer(260)
        psapi.GetModuleBaseNameW(h, None, buf, 260)
        if buf.value.lower() == name.lower(): return pid, h
        k32.CloseHandle(h)
    return None, None


def module_base(h):
    mods = (C.c_void_p * 1024)(); need = W.DWORD()
    psapi.EnumProcessModulesEx(h, mods, C.sizeof(mods), C.byref(need), 0x01)   # LIST_MODULES_32BIT
    return mods[0]


def read(h, addr, fmt):
    import struct
    size = struct.calcsize(fmt); buf = C.create_string_buffer(size); n = C.c_size_t()
    if not k32.ReadProcessMemory(h, C.c_void_p(addr), buf, size, C.byref(n)): return None
    return struct.unpack(fmt, buf.raw)[0]


secs = float(sys.argv[1]) if len(sys.argv) > 1 else 5
pid, h = find_pid()
if not h: sys.exit('game not running')
base = module_base(h)
mgr = read(h, base + (0xc3fe90 - 0x400000), '<I')
vals = []
end = time.time() + secs
while time.time() < end:
    v = read(h, mgr + 0x10, '<f')
    if v: vals.append(v)
    time.sleep(0.05)
q = sorted(vals)
print(f'fps samples={len(vals)} median={statistics.median(vals):.1f} p10={q[len(q)//10]:.1f} p90={q[9*len(q)//10]:.1f}')
