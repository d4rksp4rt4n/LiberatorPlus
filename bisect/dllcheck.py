"""Compare the running game (clean exe + dinput8.dll) with an exe patched by patch_exe.py.
  python -I dllcheck.py path/to/patched_reference.exe
Plain edits must match byte for byte; call-site hooks are shown as disassembly (DLL stub vs exe cave)."""
import struct, sys, os, capstone, pefile
ref = sys.argv[1]; sys.argv = sys.argv[:1]
src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'adread.py')).read()
exec(src.split('h = find_pid()')[0])
h = find_pid()
if not h: sys.exit('game not running')
base = module_base(h)
pe = pefile.PE(ref); img = pe.get_memory_mapped_image()
live = lambda va, n: raw(h, base + va - 0x400000, n)
file = lambda va, n: img[va - 0x400000:va - 0x400000 + n]
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
bad = 0

for name, va, n in [('zoom', 0x5c3d70, 731), ('mip jne', 0x86307c, 2), ('mip lod', 0x863087, 7),
                    ('fps imm', 0x85af9a, 7), ('fps tables', 0x8eac80, 32), ('limiter', 0x855d9c, 3),
                    ('vsync', 0x85afaf, 3), ('intro jl', 0x706587, 2)]:
    ok = live(va, n) == file(va, n); bad += not ok
    print(f'{name:12} {"OK" if ok else "DIFF  live " + live(va, n).hex() + "  ref " + file(va, n).hex()}')


def dis(read, a, label):
    code = read(a, 64); out = []
    for i in md.disasm(code, a):
        out.append(f'{i.mnemonic} {i.op_str}');
        if i.mnemonic == 'ret': break
    return out


for name, va, n in [('size w', 0x5c3aef, 10), ('size h', 0x5c3b19, 10), ('aniso', 0x86304c, 7),
                    ('intro 1', 0x705e1b, 5), ('intro 2', 0x705e38, 5), ('dlc', 0x6d886c, 6)]:
    L, F = live(va, n), file(va, n)
    lt = base + va - 0x400000 + 5 + struct.unpack('<i', L[1:5])[0]
    ft = va + 5 + struct.unpack('<i', F[1:5])[0]
    ok = L[0] == 0xe8 and L[5:] == F[5:]; bad += not ok
    print(f'--- {name}: site {"OK" if ok else "DIFF"} ({L.hex()}), stub at {lt:#x}')
    a, b = dis(lambda x, k: raw(h, x, k), lt, 'dll'), dis(file, ft, 'exe')
    for i in range(max(len(a), len(b))):
        x, y = (a[i] if i < len(a) else ''), (b[i] if i < len(b) else '')
        print(f'   {x:42} {"" if x == y else "| exe: " + y}')

j = live(0x8914bb, 5); t = base + 0x8914c0 - 0x400000 + struct.unpack('<i', j[1:])[0]
print('physics jmp ->', hex(t), 'OK (DLL)' if not base <= t < base + 0x900000 else 'NOT hooked')
e = pe.OPTIONAL_HEADER.AddressOfEntryPoint
print('entry restored', 'OK' if raw(h, base + e, 5) == img[e:e + 5] else 'DIFF')
ch = struct.unpack('<H', raw(h, base + struct.unpack('<I', raw(h, base + 0x3c, 4))[0] + 22, 2))[0]
print('LAA in memory', 'OK' if ch & 0x20 else 'MISSING', '| base', hex(base))
print('byte mismatches:', bad)
