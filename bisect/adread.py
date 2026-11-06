"""Dump the live Articulated Dynamics nodes (bust physics) from the running game.
   python -I adread.py            (game must be running, e.g. in the dressing room)"""
import struct, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ctypes as C
from ctypes import wintypes as W
k32, psapi = C.WinDLL('kernel32'), C.WinDLL('psapi')


def find_pid(name='VD_BHIKKHUNI.exe'):
    arr = (W.DWORD * 4096)(); got = W.DWORD()
    psapi.EnumProcesses(arr, C.sizeof(arr), C.byref(got))
    for pid in arr[:got.value // 4]:
        h = k32.OpenProcess(0x410, False, pid)
        if not h: continue
        buf = C.create_unicode_buffer(260)
        psapi.GetModuleBaseNameW(h, None, buf, 260)
        if buf.value.lower() == name.lower(): return h
        k32.CloseHandle(h)


def module_base(h):
    mods = (C.c_void_p * 1024)(); need = W.DWORD()
    psapi.EnumProcessModulesEx(h, mods, C.sizeof(mods), C.byref(need), 0x01)
    return mods[0]


def raw(h, a, n):
    buf = C.create_string_buffer(n); got = C.c_size_t()
    return buf.raw if k32.ReadProcessMemory(h, C.c_void_p(a), buf, n, C.byref(got)) else None


def u32(h, a): b = raw(h, a, 4); return struct.unpack('<I', b)[0] if b else 0
def f32(h, a): b = raw(h, a, 4); return struct.unpack('<f', b)[0] if b else float('nan')


def cstr(h, a):
    b = raw(h, a, 48)
    if not b: return None
    s = b.split(b'\0')[0]
    return s.decode() if len(s) >= 3 and all(32 <= c < 127 for c in s) else None


h = find_pid()
if not h: sys.exit('game not running')
base = module_base(h)
G = lambda va: base + (va - 0x400000)
mgr = u32(h, G(0xc3fec4))
cnt = u32(h, mgr + 0x13860)
print(f'manager {mgr:#x} timescale {f32(h, mgr + 0x13868)} nodes {cnt} frame dt {f32(h, u32(h, G(0xc3fe90)) + 0x14):.5f}')
for i in range(cnt):
    n = u32(h, mgr + 0x13060 + 4 * i)
    if not n: continue
    nb = raw(h, n, 0xa0)
    names = [s for o in range(0, 0xa0, 4) for s in [cstr(h, struct.unpack_from('<I', nb, o)[0])] if s]
    npart, ncon, nanc = u32(h, n + 0x68), u32(h, n + 0x6c), u32(h, n + 0x30)
    print(f'\nnode {i} @{n:#x} names={names} mode={u32(h, n + 0x48)} blend54={f32(h, n + 0x54):.3f} '
          f'scale84={f32(h, n + 0x84):.3f} outer88={u32(h, n + 0x88)} iters74={u32(h, n + 0x74)} '
          f'parts={npart} cons={ncon} anchors={nanc} flags93-95={nb[0x93]},{nb[0x94]},{nb[0x95]}')
    pa = u32(h, n + 0x18)
    for j in range(min(npart, 12)):
        p = pa + 0xf0 * j
        prm = u32(h, p + 0xe0)
        print(f'   part {j}: flags={u32(h, p + 0xec) & 0xffff:#06x} mass={f32(h, p + 0xd0):.3f} damp={f32(h, p + 0xd8):.3f} '
              f'grav58={f32(h, prm + 0x58):.3f} forces={u32(h, prm + 0x40)} v=({f32(h, p + 0xa0):.3f},{f32(h, p + 0xa4):.3f},{f32(h, p + 0xa8):.3f})')
    ca = u32(h, n + 0x1c)
    for j in range(min(ncon, 12)):
        c = ca + 0x28 * j
        print(f'   con {j}: type={u32(h, c + 0x20)} k={f32(h, c + 0xc):.4f} rest={f32(h, c + 0x18):.4f} '
              f'raw={[round(x, 4) for x in struct.unpack("<10f", raw(h, c, 0x28))]}')
