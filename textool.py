"""Extract every texture (top mip level) from Valkyrie Drive .mib files to PNG.

  python -I VDMod/textool.py extract <src_root> <out_dir> <subdir> [subdir ...]
  e.g. python -I VDMod/textool.py extract DeploymentRoot/Resource VDMod/extract UI UI_Eng_Dt Character

Output mirrors the game tree: <out>/<subdir>/<file>.mib/<index>_<name>.png
Identical images are written once; manifest.csv lists every texture and the PNG it uses
(column 'png'), so a re-import step can put an upscaled PNG back everywhere it's used.
"""
import csv, hashlib, os, re, struct, subprocess, sys, tempfile
from PIL import Image
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from miptool import entries, pack, chain_size, TEXCONV, BC as MIPBC

FMT = {0: ('RGBA', 4), 16: ('RGB', 3), 8: ('bcn', 1), 9: ('bcn', 2), 10: ('bcn', 3)}   # fmt -> decoder
BC_BLOCK = {1: 8, 2: 16, 3: 16}


def decode(e):
    kind, n = FMT[e['fmt']]
    w, h = e['w'], e['h']
    if kind != 'bcn':
        return Image.frombytes(kind, (w, h), e['data'][:w * h * n])
    pw, ph = (w + 3) // 4 * 4, (h + 3) // 4 * 4               # BC data covers whole 4x4 blocks
    size = pw // 4 * ph // 4 * BC_BLOCK[n]
    return Image.frombytes('RGBA', (pw, ph), e['data'][:size], 'bcn', n).crop((0, 0, w, h))


def extract(src_root, out_dir, *subdirs):
    seen, rows, skipped = {}, [], []
    for sub in subdirs:
        for dp, _, fs in os.walk(os.path.join(src_root, sub)):
            for f in sorted(fs):
                if not f.endswith('.mib'): continue
                p = os.path.join(dp, f)
                rel = os.path.relpath(p, src_root).replace('\\', '/')
                for i, e in enumerate(entries(open(p, 'rb').read())):
                    name = e['hdr'][0x28:].split(b'\0')[0].decode('latin1')
                    if e['fmt'] not in FMT:
                        skipped.append((rel, i, name, e['fmt'])); continue
                    im = decode(e)
                    if im.mode == 'RGBA' and im.getextrema()[3] == (255, 255):
                        im = im.convert('RGB')                    # opaque: smaller PNG, nicer for upscalers
                    key = hashlib.sha1(im.tobytes() + im.mode.encode() + bytes(str(im.size), 'ascii')).hexdigest()
                    if key not in seen:
                        png = f'{rel}/{i:02d}_{re.sub(r"[^A-Za-z0-9_.-]", "_", name) or "tex"}.png'
                        os.makedirs(os.path.dirname(os.path.join(out_dir, png)), exist_ok=True)
                        im.save(os.path.join(out_dir, png))
                        seen[key] = png
                    rows.append([seen[key], rel, i, name, e['fmt'], e['w'], e['h'], e['mips'], im.mode])
        print(f'{sub}: {len(rows)} textures so far, {len(seen)} unique PNGs')
    with open(os.path.join(out_dir, 'manifest.csv'), 'w', newline='', encoding='utf-8') as fh:
        wr = csv.writer(fh)
        wr.writerow(['png', 'mib', 'entry', 'name', 'fmt', 'w', 'h', 'mips', 'mode'])
        wr.writerows(rows)
    print(f'done: {len(rows)} textures -> {len(seen)} PNGs; skipped {len(skipped)} unknown-format: {skipped}')


def rgba_dds(im):
    """Uncompressed R8G8B8A8_UNORM DDS (no sRGB tag, so texconv does no gamma conversion)."""
    w, h = im.size
    hdr = struct.pack('<4s7I44x2I4s5I5I', b'DDS ', 124, 0x100f, h, w, w * 4, 0, 1,
                      32, 0x41, b'\0\0\0\0', 32, 0xff, 0xff00, 0xff0000, 0xff000000, 0x1000, 0, 0, 0, 0)
    return hdr + im.convert('RGBA').tobytes()


def encode(im, fmt, mips):
    """Image -> MIB pixel data in the entry's format; BC via texconv (full chain if mips > 1)."""
    w, h = im.size
    if fmt == 0: return im.convert('RGBA').tobytes(), 1
    if fmt == 16: return im.convert('RGB').tobytes(), 1
    assert fmt in MIPBC and w % 4 == 0 and h % 4 == 0, (fmt, w, h)
    n = max(w, h).bit_length() if mips > 1 else 1
    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, 'img.dds')
        open(src, 'wb').write(rgba_dds(im))
        os.makedirs(os.path.join(tmp, 'out'))
        r = subprocess.run([TEXCONV, '-nologo', '-y', '-m', str(n), '-f', MIPBC[fmt][2], '-o', tmp + '/out', src],
                           capture_output=True, text=True)
        assert r.returncode == 0, r.stdout[-1500:] + r.stderr[-1500:]
        raw = open(os.path.join(tmp, 'out', 'img.dds'), 'rb').read()
    start = 148 if raw[84:88] == b'DX10' else 128
    assert len(raw) - start == chain_size(fmt, w, h, n), (len(raw), chain_size(fmt, w, h, n))
    return raw[start:], n


def inject(mib_in, mib_out, *pairs):
    """Replace entries: inject in.mib out.mib 4=a.png 17=logo.dds ... (any size; format kept)."""
    d = open(mib_in, 'rb').read()
    ents = list(entries(d))
    for pair in pairs:
        i, path = pair.split('=', 1)
        e = ents[int(i)]
        im = Image.open(path)
        old_w, old_h = e['w'], e['h']
        data, n = encode(im, e['fmt'], e['mips'])
        e['data'] = data
        hdr = bytearray(e['hdr'])
        struct.pack_into('<I', hdr, 4, len(data)); struct.pack_into('<I', hdr, 0x20, len(data))
        struct.pack_into('<HH', hdr, 0x14, *im.size); hdr[0x1b] = n
        e['hdr'] = bytes(hdr)
        # self-check: decode what we wrote and compare with the source image
        back = decode(dict(e, w=im.size[0], h=im.size[1], mips=n)).convert('RGBA')
        diff = sum(abs(a - b) for a, b in zip(back.resize((64, 64)).tobytes(), im.convert('RGBA').resize((64, 64)).tobytes())) / (64 * 64 * 4)
        assert diff < 6, f'entry {i}: decoded result differs from source (mean {diff:.1f})'
        print(f'  entry {i}: {old_w}x{old_h} -> {im.size[0]}x{im.size[1]} fmt {e["fmt"]} mips {n} (check diff {diff:.2f})')
    os.makedirs(os.path.dirname(mib_out) or '.', exist_ok=True)
    out = pack(d, ents)
    assert [x['data'] for x in entries(out)] == [x['data'] for x in ents]
    open(mib_out, 'wb').write(out)


if __name__ == '__main__':
    cmd, *a = sys.argv[1:]
    {'extract': extract, 'inject': inject}[cmd](*a)
