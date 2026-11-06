"""Add full mip chains to single-mip BC1/BC3 textures in Valkyrie Drive .mib files.

  python -I miptool.py build <src_root> <out_root> <subdir> [subdir ...]
  e.g. python -I VDMod/miptool.py build DeploymentRoot/Resource VDMod/out_mips BG Stage

Entry layout (offset table at 0x10, one u32 per texture):
  +04 u32 data size   +08 u32 data offset (from entry)   +10 u32 fmt (8=BC1, 10=BC3)
  +14 u16 w, h        +1b u8 mip count                   +20 u32 data size (copy)
Data = mip levels back to back (largest first). Some entries hold a Vita GXT container
('GXT\0' + 64-byte header before the image data); those are skipped.

Level 0 is kept byte-for-byte. Levels 1..n come from texconv (DirectXTex, in
VDMod/tools): it decodes level 0, box-filters the chain and BC-encodes it.
Cut-out textures (mostly 0/255 alpha) use -keepcoverage so foliage/fences
don't thin out. Pillow is used only to *decode* (its BC encoder is buggy).
Only power-of-two, non-GXT textures whose size is exactly level 0 are touched.
"""
import os, struct, subprocess, sys, tempfile
import numpy as np
from PIL import Image

TEXCONV = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'tools', 'texconv.exe')
BC = {8: (1, b'DXT1', 'BC1_UNORM', 8), 10: (3, b'DXT5', 'BC3_UNORM', 16)}   # fmt -> pillow n, fourcc, dxgi, block bytes
REF = 0.5                                                                      # assumed alpha-test reference


def lvl_size(fmt, w, h):
    return max(1, (w + 3) // 4) * max(1, (h + 3) // 4) * BC[fmt][3]


def chain_size(fmt, w, h, n):
    return sum(lvl_size(fmt, max(1, w >> i), max(1, h >> i)) for i in range(n))


def entries(d):
    n = struct.unpack_from('<H', d, 0x0e)[0]
    offs = list(struct.unpack_from(f'<{n}I', d, 0x10)) + [len(d)]
    for i in range(n):
        o = offs[i]
        size, doff = struct.unpack_from('<II', d, o + 4)
        fmt = struct.unpack_from('<I', d, o + 0x10)[0]
        w, h = struct.unpack_from('<HH', d, o + 0x14)
        assert offs[i + 1] == o + doff + size, 'entries not contiguous'
        yield dict(hdr=d[o:o + doff], data=d[o + doff:o + doff + size], fmt=fmt, w=w, h=h, mips=d[o + 0x1b])


def eligible(e):
    w, h, f = e['w'], e['h'], e['fmt']
    if f not in BC or e['mips'] != 1 or w < 8 or h < 8 or w & (w - 1) or h & (h - 1):
        return False
    # Textures wrapped in a Vita GXT container (data starts with 'GXT\0' + 64-byte header) are left
    # alone: the header precedes the image data, so appending mips would split the image.
    return e['data'][:4] != b'GXT\0' and len(e['data']) == lvl_size(f, w, h)


def dds(fmt, w, h, level0):
    """Minimal legacy DDS (one level, DXT1/DXT5)."""
    hdr = struct.pack('<4s7I44x2I4s20x5I', b'DDS ', 124, 0x81007, h, w, len(level0), 0, 1,
                      32, 4, BC[fmt][1], 0x1000, 0, 0, 0, 0)
    assert len(hdr) == 128
    return hdr + level0


def read_dds_levels(path, fmt, w, h):
    raw = open(path, 'rb').read()
    assert raw[:4] == b'DDS ' and struct.unpack_from('<2I', raw, 12) == (h, w), path
    mips = struct.unpack_from('<I', raw, 28)[0]
    start = 148 if raw[84:88] == b'DX10' else 128
    n = max(w, h).bit_length()
    assert mips == n and len(raw) - start == chain_size(fmt, w, h, n), (path, mips, n)
    return raw[start + lvl_size(fmt, w, h):]                      # levels 1..n-1


def is_cutout(fmt, w, h, level0):
    a = np.asarray(Image.frombytes('RGBA', (w, h), level0, 'bcn', BC[fmt][0]))[..., 3]
    return a.min() < 128 and ((a < 16) | (a > 239)).mean() > 0.9


def make_mips(jobs, tmp):
    """jobs: list of (fmt, w, h, level0). Returns list of mip bytes (levels 1..n)."""
    groups = {}
    for k, (fmt, w, h, l0) in enumerate(jobs):
        p = os.path.join(tmp, 'in', f't{k}.dds')
        open(p, 'wb').write(dds(fmt, w, h, l0))
        groups.setdefault((fmt, is_cutout(fmt, w, h, l0)), []).append(p)
    out = os.path.join(tmp, 'out')
    for (fmt, cut), paths in groups.items():
        lst = os.path.join(tmp, 'list.txt')
        open(lst, 'w').write('\n'.join(paths))
        cmd = [TEXCONV, '-nologo', '-y', '-m', '0', '-f', BC[fmt][2], '-o', out, '-flist', lst]
        if cut: cmd[1:1] = ['-keepcoverage', str(REF)]
        r = subprocess.run(cmd, capture_output=True, text=True)
        assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-2000:]
    return [read_dds_levels(os.path.join(out, f't{k}.dds'), fmt, w, h) for k, (fmt, w, h, _) in enumerate(jobs)]


def rebuild(d, mips_for):
    ents = list(entries(d))
    for e in ents:
        if not eligible(e): continue
        L0 = lvl_size(e['fmt'], e['w'], e['h'])
        e['data'] = e['data'][:L0] + mips_for(e) + e['data'][L0:]
        hdr = bytearray(e['hdr'])
        struct.pack_into('<I', hdr, 4, len(e['data'])); struct.pack_into('<I', hdr, 0x20, len(e['data']))
        hdr[0x1b] = max(e['w'], e['h']).bit_length()
        e['hdr'] = bytes(hdr)
    return pack(d, ents)


def pack(d, ents):
    """Re-assemble a MIB: original file header + entries (hdr+data) with a fresh offset table."""
    n = len(ents)
    out = bytearray(d[:0x10 + 4 * n])
    for i, e in enumerate(ents):
        struct.pack_into('<I', out, 0x10 + 4 * i, len(out))
        out += e['hdr'] + e['data']
    return bytes(out)


def check(old, new):
    """Untouched textures identical; changed ones keep level 0 + filler and have a full chain."""
    for a, b in zip(entries(old), entries(new), strict=True):
        if b['mips'] == a['mips']:
            assert a == b; continue
        f, w, h = a['fmt'], a['w'], a['h']
        L0, full = lvl_size(f, w, h), chain_size(f, w, h, b['mips'])
        assert b['mips'] == max(w, h).bit_length()
        assert b['data'][:L0] == a['data'][:L0] and b['data'][full:] == a['data'][L0:]
        assert len(b['data']) == full + len(a['data']) - L0
        keep = lambda x: x[:4] + x[8:0x1b] + x[0x1c:0x20] + x[0x24:]
        assert keep(a['hdr']) == keep(b['hdr'])


def build(src_root, out_root, *subdirs):
    files = []
    for sub in subdirs:
        for dp, _, fs in os.walk(os.path.join(src_root, sub)):
            files += [os.path.join(dp, f) for f in fs if f.endswith('.mib')]
    jobs, where = [], {}
    for p in files:
        for i, e in enumerate(entries(open(p, 'rb').read())):
            if eligible(e):
                where[(p, i)] = len(jobs)
                jobs.append((e['fmt'], e['w'], e['h'], e['data'][:lvl_size(e['fmt'], e['w'], e['h'])]))
    print(f'{len(jobs)} textures to mip in {len({p for p, _ in where})} files')
    with tempfile.TemporaryDirectory() as tmp:
        os.makedirs(os.path.join(tmp, 'in')); os.makedirs(os.path.join(tmp, 'out'))
        mips = make_mips(jobs, tmp)
    nfiles = 0
    for p in files:
        d = open(p, 'rb').read()
        idx = iter(i for i, e in enumerate(entries(d)) if eligible(e))
        keys = [(p, i) for i in idx]
        if not keys: continue
        it = iter(keys)
        new = rebuild(d, lambda e: mips[where[next(it)]])
        check(d, new)
        q = os.path.join(out_root, os.path.relpath(p, src_root))
        os.makedirs(os.path.dirname(q), exist_ok=True)
        open(q, 'wb').write(new); nfiles += 1
    print(f'wrote {nfiles} files to {out_root}')


if __name__ == '__main__':
    cmd, *a = sys.argv[1:]
    {'build': build}[cmd](*a)
