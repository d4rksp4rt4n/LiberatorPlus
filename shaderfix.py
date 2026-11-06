"""MSAA fix: make pixel-shader inputs 'centroid' in Valkyrie Drive's shader caches.

With MSAA, edge pixels run the pixel shader at the pixel centre even when it lies outside
the triangle, so 'linear' inputs are extrapolated. Overlay shaders (alpha = tex.a * vertex
colour) then output alpha far outside 0..1 (e.g. -44.9); the FP16 scene buffer doesn't clamp,
the blend explodes to values ~500 and bloom turns it into flashing blobs.
'linear centroid' samples inside the covered area - the standard MSAA-correct mode.

  python -I VDMod/shaderfix.py check DeploymentRoot      # verify checksums, count patchable shaders
  python -I VDMod/shaderfix.py apply DeploymentRoot      # patch files (originals -> VDMod/backup)
"""
import os, shutil, struct, sys

FILES = ['MeShaderQueCache_WIN.bin', 'MeShaderCache_WIN.bin', 'MeShaderPack_WIN.bin', 'MeigeUtilWinShaderPack.bin']
BACKUP = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'backup')

# ---- DXBC checksum (MD5 compression with DXBC's own padding) ----
_S = [7, 12, 17, 22] * 4 + [5, 9, 14, 20] * 4 + [4, 11, 16, 23] * 4 + [6, 10, 15, 21] * 4
_K = [int(abs(__import__('math').sin(i + 1)) * 2 ** 32) & 0xffffffff for i in range(64)]


def _md5_block(st, block):
    M = struct.unpack('<16I', block)
    a, b, c, d = st
    for i in range(64):
        if i < 16: f, g = (b & c) | (~b & d), i
        elif i < 32: f, g = (d & b) | (~d & c), (5 * i + 1) % 16
        elif i < 48: f, g = b ^ c ^ d, (3 * i + 5) % 16
        else: f, g = c ^ (b | ~d), (7 * i) % 16
        f = (f + a + _K[i] + M[g]) & 0xffffffff
        a, d, c = d, c, b
        b = (b + ((f << _S[i]) | (f >> (32 - _S[i])))) & 0xffffffff
    return [(x + y) & 0xffffffff for x, y in zip(st, (a, b, c, d))]


def dxbc_checksum(blob):
    data = blob[20:]
    n = len(data); bits = n * 8
    st = [0x67452301, 0xefcdab89, 0x98badcfe, 0x10325476]
    full = n - n % 64
    for i in range(0, full, 64): st = _md5_block(st, data[i:i + 64])
    rest = data[full:]
    if len(rest) >= 56:
        st = _md5_block(st, (rest + b'\x80').ljust(64, b'\0'))
        st = _md5_block(st, struct.pack('<I', bits) + b'\0' * 56 + struct.pack('<I', (bits >> 2) | 1))
    else:
        blk = struct.pack('<I', bits) + rest + b'\x80'
        st = _md5_block(st, blk.ljust(60, b'\0') + struct.pack('<I', (bits >> 2) | 1))
    return struct.pack('<4I', *st)


# ---- DXBC parsing ----
OP_DCL_INPUT_PS = 0x62
LINEAR, LINEAR_CENTROID = 2, 3


def blobs(d):
    i = d.find(b'DXBC')
    while i != -1:
        size = struct.unpack_from('<I', d, i + 24)[0]
        if 32 < size < 1 << 20 and i + size <= len(d):
            yield i, size
            i = d.find(b'DXBC', i + size)
        else:
            i = d.find(b'DXBC', i + 4)


def shader_chunk(blob):
    """(offset of SHDR/SHEX payload within blob, payload bytes) or None."""
    n = struct.unpack_from('<I', blob, 28)[0]
    for k in range(n):
        o = struct.unpack_from('<I', blob, 32 + 4 * k)[0]
        if blob[o:o + 4] in (b'SHDR', b'SHEX'):
            ln = struct.unpack_from('<I', blob, o + 4)[0]
            return o + 8, blob[o + 8:o + 8 + ln]
    return None


def centroid_patch(blob):
    """Return (patched blob, number of inputs changed); None if not a pixel shader."""
    sc = shader_chunk(blob)
    if not sc: return None
    base, code = sc
    ver = struct.unpack_from('<I', code, 0)[0]
    if ver >> 16 != 0: return None                       # program type 0 = pixel shader
    out = bytearray(blob); changed = 0
    p = 8                                                # skip version + length tokens
    while p < len(code):
        tok = struct.unpack_from('<I', code, p)[0]
        op = tok & 0x7ff
        ln = (tok >> 24) & 0x7f
        if op == 0x35: ln = struct.unpack_from('<I', code, p + 4)[0]     # customdata: length in next dword
        assert ln, f'bad token at {p}'
        if op == OP_DCL_INPUT_PS and (tok >> 11) & 0xf == LINEAR:
            struct.pack_into('<I', out, base + p, (tok & ~(0xf << 11)) | (LINEAR_CENTROID << 11))
            changed += 1
        p += ln * 4
    assert p == len(code), 'token walk did not end exactly at the end of the program'
    if changed:
        out[4:20] = dxbc_checksum(bytes(out))
    return bytes(out), changed


def process(root, apply):
    tot_ps = tot_in = bad = 0
    for f in FILES:
        path = os.path.join(root, f)
        d = open(path, 'rb').read()
        new = bytearray(d); ps = inputs = 0
        for off, size in blobs(d):
            blob = d[off:off + size]
            if dxbc_checksum(blob) != blob[4:20]:
                bad += 1; continue
            r = centroid_patch(blob)
            if r and r[1]:
                assert dxbc_checksum(r[0]) == r[0][4:20]
                new[off:off + size] = r[0]; ps += 1; inputs += r[1]
        print(f'{f}: {ps} pixel shaders, {inputs} inputs -> centroid')
        tot_ps += ps; tot_in += inputs
        if apply and new != d:
            os.makedirs(BACKUP, exist_ok=True)
            b = os.path.join(BACKUP, f)
            if not os.path.exists(b): shutil.copy2(path, b)
            open(path, 'wb').write(new)
    print(f'total {tot_ps} shaders / {tot_in} inputs; blobs with unexpected checksum (skipped): {bad}')


if __name__ == '__main__':
    cmd, root = sys.argv[1:3]
    process(root, cmd == 'apply')
