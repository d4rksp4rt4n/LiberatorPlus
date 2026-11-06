"""Check shaderfix output with the real D3D11 runtime: every patched pixel shader must be accepted
by ID3D11Device::CreatePixelShader, and the culprit overlay shader must show 'linear centroid'.
  python -I VDMod/test_shaderfix.py DeploymentRoot
"""
import ctypes, os, sys
from ctypes import c_void_p, c_uint, c_int, POINTER, byref
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import shaderfix as F

d3d11 = ctypes.WinDLL('d3d11')
dev = c_void_p(); ctx = c_void_p(); fl = c_uint()
hr = d3d11.D3D11CreateDevice(None, 1, None, 0, None, 0, 7, byref(dev), byref(fl), byref(ctx))  # HARDWARE, SDK 7
assert hr == 0, hex(hr & 0xffffffff)
vt = ctypes.cast(ctypes.cast(dev, POINTER(c_void_p))[0], POINTER(c_void_p))
CreatePS = ctypes.WINFUNCTYPE(c_int, c_void_p, c_void_p, ctypes.c_size_t, c_void_p, POINTER(c_void_p))(vt[15])

comp = ctypes.WinDLL(r'C:\Windows\System32\d3dcompiler_47.dll')
def disasm(b):
    out = c_void_p()
    comp.D3DDisassemble(b, len(b), 0, None, byref(out))
    v = ctypes.cast(ctypes.cast(out, POINTER(c_void_p))[0], POINTER(c_void_p))
    s = ctypes.string_at(ctypes.WINFUNCTYPE(c_void_p, c_void_p)(v[3])(out), ctypes.WINFUNCTYPE(ctypes.c_size_t, c_void_p)(v[4])(out))
    return s.decode('latin1')

ok = fail = 0; culprit = None
for f in F.FILES:
    d = open(os.path.join(sys.argv[1], f), 'rb').read()
    for off, size in F.blobs(d):
        r = F.centroid_patch(d[off:off + size])
        if not r or not r[1]: continue
        ps = c_void_p()
        hr = CreatePS(dev, r[0], len(r[0]), None, byref(ps))
        if hr == 0:
            ok += 1; ctypes.WINFUNCTYPE(c_uint, c_void_p)(ctypes.cast(ctypes.cast(ps, POINTER(c_void_p))[0], POINTER(c_void_p))[2])(ps)
        else:
            fail += 1; print('REJECTED', f, hex(off), hex(hr & 0xffffffff))
        if f == 'MeShaderQueCache_WIN.bin' and off == 0x86fc: culprit = r[0]
print(f'CreatePixelShader accepted {ok}, rejected {fail}')
print('\n'.join(l for l in disasm(culprit).splitlines() if 'dcl_input_ps' in l))
