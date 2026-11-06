"""Tiny PE helper for VD_BHIKKHUNI.exe (32-bit): VA<->file offset, string xrefs, disasm."""
import struct, sys
import capstone

EXE = 'DeploymentRoot/VD_BHIKKHUNI.exe'
D = open(EXE, 'rb').read()
_pe = struct.unpack_from('<I', D, 0x3c)[0]
BASE = struct.unpack_from('<I', D, _pe + 0x34)[0]
_ns = struct.unpack_from('<H', D, _pe + 6)[0]
_so = _pe + 24 + struct.unpack_from('<H', D, _pe + 20)[0]
SECT = []
for i in range(_ns):
    nm, vs, va, rs, ra = struct.unpack_from('<8sIIII', D, _so + 40 * i)
    SECT.append((nm.rstrip(b'\0').decode(), BASE + va, vs, ra, rs))
MD = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)


def off2va(o):
    for _, va, vs, ra, rs in SECT:
        if ra <= o < ra + rs: return va + o - ra


def va2off(v):
    for _, va, vs, ra, rs in SECT:
        if va <= v < va + max(vs, rs): return ra + v - va


def text():
    return next(s for s in SECT if s[0] == '.text')


def xrefs(va):
    """Offsets in .text where the 4-byte little-endian VA appears (push/mov imm)."""
    _, tva, _, ra, rs = text()
    pat = struct.pack('<I', va); out = []; i = D.find(pat, ra, ra + rs)
    while i != -1:
        out.append(off2va(i)); i = D.find(pat, i + 1, ra + rs)
    return out


def dis(va, n=40):
    o = va2off(va)
    for ins in MD.disasm(D[o:o + n * 8], va, n):
        print(f'{ins.address:08x}  {ins.mnemonic:6s} {ins.op_str}')
