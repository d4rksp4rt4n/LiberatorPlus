"""Callers of imported functions: python -I VDMod/re/imp.py Name1 Name2 ...  (run from the game root)"""
import struct, sys
sys.path.insert(0, 'VDMod/re')
from pe import D, BASE, _pe, va2off, text, MD

def imports():
    rva = struct.unpack_from('<I', D, _pe + 0x80)[0]
    out = {}
    o = va2off(BASE + rva)
    while True:
        oft, _, _, name, ft = struct.unpack_from('<IIIII', D, o)
        if not name: break
        dll = D[va2off(BASE + name):].split(b'\0')[0].decode()
        i = 0
        while True:
            t = struct.unpack_from('<I', D, va2off(BASE + (oft or ft)) + 4 * i)[0]
            if not t: break
            if not t & 0x80000000:
                fn = D[va2off(BASE + t) + 2:].split(b'\0')[0].decode()
                out[fn] = (dll, BASE + ft + 4 * i)
            i += 1
        o += 20
    return out

if __name__ == '__main__':
    imp = imports()
    _, tva, tvs, tra, trs = text()
    code = D[tra:tra + trs]
    for name in sys.argv[1:]:
        if name not in imp: print(name, 'not imported'); continue
        dll, iat = imp[name]
        pat = struct.pack('<I', iat)
        hits = []
        i = code.find(pat)
        while i >= 0:
            hits.append(tva + i - 2); i = code.find(pat, i + 1)
        print(f'{name} ({dll}) IAT {iat:#x}: {len(hits)} refs ' + ' '.join(f'{h:#x}' for h in hits[:20]))
