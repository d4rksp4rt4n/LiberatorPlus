"""Valkyrie Drive CG (.mib) <-> PNG.

  python cgtool.py topng   in.mib out.png
  python cgtool.py frompng in.png template.mib out.mib   # template = original CG
  python cgtool.py selftest Resource/UI/advstill         # round-trip every CG

Single-texture MIB layout (from samples):
  0x00 'MIB '  0x0e u16 entry count  0x10 u32 entry offset (=0x20)
  entry @0x20: +0x04 u32 data size, +0x10 u32 fmt (0x10 RGB24, 0x00 RGBA32),
               +0x14 u16 w, +0x16 u16 h, +0x1b u8 mips, +0x20 u32 data size,
               +0x28 name[32]; pixels at entry + 0x40 (= 0x60)
"""
import struct, sys, os
import numpy as np
from PIL import Image

E = 0x20                      # entry offset in single-texture CG files
CH = {0x10: 3, 0x00: 4}       # fmt -> bytes per pixel


def parse(d):
    assert d[:4] == b'MIB ', 'not a MIB'
    assert struct.unpack_from('<H', d, 0x0e)[0] == 1, 'multi-texture MIB, not a CG'
    assert struct.unpack_from('<I', d, 0x10)[0] == E
    fmt = struct.unpack_from('<I', d, E + 0x10)[0]
    w, h = struct.unpack_from('<HH', d, E + 0x14)
    assert fmt in CH, f'unsupported fmt {fmt:#x}'
    assert d[E + 0x1b] == 1, 'CG has mips?'
    return fmt, w, h


def topng(src, dst):
    d = open(src, 'rb').read()
    fmt, w, h = parse(d)
    c = CH[fmt]
    px = np.frombuffer(d, np.uint8, w * h * c, E + 0x40).reshape(h, w, c)
    Image.fromarray(px, 'RGB' if c == 3 else 'RGBA').save(dst)


def frompng(src, template, dst):
    t = bytearray(open(template, 'rb').read())
    fmt, _, _ = parse(t)
    c = CH[fmt]
    img = Image.open(src).convert('RGB' if c == 3 else 'RGBA')
    w, h = img.size
    assert w <= 0xFFFF and h <= 0xFFFF
    px = np.asarray(img, np.uint8).tobytes()
    hdr = t[:E + 0x40]
    struct.pack_into('<I', hdr, E + 0x04, len(px))
    struct.pack_into('<HH', hdr, E + 0x14, w, h)
    struct.pack_into('<I', hdr, E + 0x20, len(px))
    open(dst, 'wb').write(bytes(hdr) + px)


def selftest(folder):
    import tempfile
    tmp = tempfile.mkdtemp()
    n = 0
    for f in sorted(os.listdir(folder)):
        if not f.endswith('.mib'): continue
        src = os.path.join(folder, f)
        png, out = os.path.join(tmp, 'a.png'), os.path.join(tmp, 'a.mib')
        topng(src, png); frompng(png, src, out)
        assert open(src, 'rb').read() == open(out, 'rb').read(), f'round-trip mismatch: {f}'
        n += 1
    print(f'ok: {n} CGs round-trip byte-identical')


def build(mapfile, srcdir, gamecg, outdir, scale):
    """Resize each mapped upscale to original*scale (Lanczos) and write <name>.mib."""
    import tempfile
    scale = int(scale)
    os.makedirs(outdir, exist_ok=True)
    tmp = os.path.join(tempfile.mkdtemp(), 'x.png')
    for line in open(mapfile):
        line = line.split('#')[0].split()
        if not line: continue
        h, name = line
        tpl = os.path.join(gamecg, name + '.mib')
        _, w0, h0 = parse(open(tpl, 'rb').read())
        assert h0 == 544, f'{tpl}: template must be the original CG (use VDMod/backup/UI/advstill)'
        img = Image.open(os.path.join(srcdir, h + '.png'))
        img.resize((w0 * scale, h0 * scale), Image.LANCZOS).save(tmp)
        frompng(tmp, tpl, os.path.join(outdir, name + '.mib'))
        print(name, w0 * scale, 'x', h0 * scale)


if __name__ == '__main__':
    cmd, *a = sys.argv[1:]
    {'topng': topng, 'frompng': frompng, 'selftest': selftest, 'build': build}[cmd](*a)
