"""Fix the strongest-attack cut-in overlay showing 2x2 tiled (PC port bug).

Its pixel shader computes  uv = SV_Position.xy / _g_regRenderTargetSize, but the game sets that
constant to the Vita screen size (960x544) while SV_Position is in real pixels -> uv runs 0..2 at
1080p and the cut-in repeats 2x2. The vertex shader already passes the correct screen uv in
TEXCOORD0 (v2), so the shader is rewritten (same length) to:
    dcl_input_ps linear centroid v2.xy      (+3 dwords)
    mov r0.xy, v2.xyxx                      (replaces the 8-dword div: -3 dwords)

  python -I VDMod/overlayfix.py apply DeploymentRoot      (originals are in VDMod/backup via shaderfix)
"""
import os, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import shaderfix as F

FILES = ['MeShaderQueCache_WIN.bin', 'MeShaderCache_WIN.bin', 'MeShaderPack_WIN.bin']
OP_DIV, OP_MOV, OP_DCL_INPUT_PS = 0x0e, 0x36, 0x62


def tokens(code):
    p, out = 8, []
    while p < len(code):
        tok = struct.unpack_from('<I', code, p)[0]
        ln = (tok >> 24) & 0x7f
        if tok & 0x7ff == 0x35: ln = struct.unpack_from('<I', code, p + 4)[0]
        out.append((p, list(struct.unpack_from(f'<{ln}I', code, p))))
        p += ln * 4
    return out


def rewrite(blob):
    """Return patched blob, or None if this is not the overlay shader pattern."""
    sc = F.shader_chunk(blob)
    if not sc: return None
    base, code = sc
    toks = tokens(code)
    div = [t for p, t in toks if t[0] & 0x7ff == OP_DIV]
    # pattern: first instruction 'div r0.xy, v1.xyxx, cb0[0].xyxx' and an input decl for v1 (position)
    if len(div) < 1 or len(div[0]) != 8: return None
    d = div[0]
    dst_op, dst_idx, src_op, src_idx = d[1], d[2], d[3], d[4]
    if dst_idx != 0 or src_idx != 1 or ((src_op >> 12) & 0xff) != 1: return None      # src must be v1 (input)
    if ((d[5] >> 12) & 0xff) != 8: return None                                          # third operand: constant buffer
    # build: declarations ... + dcl v2.xy centroid, instructions with div -> mov r0.xy, v2.xyxx
    v2_dcl_op = (src_op & ~0xffc) | 0x30                      # input operand, mask mode (bits 2-3 = 0), mask .xy
    new_dcl = [OP_DCL_INPUT_PS | (3 << 11) | (3 << 24), v2_dcl_op, 2]   # linear centroid
    new_mov = [OP_MOV | (5 << 24), dst_op, dst_idx, src_op, 2]
    out, inserted = [], False
    for p, t in toks:
        op = t[0] & 0x7ff
        if not inserted and op < 0x58 and op != 0x35:          # first real instruction: declarations done
            out += new_dcl; inserted = True
        out += new_mov if t is d else t
    assert inserted and len(out) * 4 == len(code) - 8, 'length changed'
    new_code = code[:8] + struct.pack(f'<{len(out)}I', *out)
    nb = bytearray(blob)
    nb[base:base + len(code)] = new_code
    nb[4:20] = F.dxbc_checksum(bytes(nb))
    return bytes(nb)


TARGET = '0c0f9311-95235def-ddd0c2df-0f729eb2'     # overlay PS (after centroid fix), from the capture


def checksum_str(blob):
    return '-'.join('%08x' % x for x in struct.unpack_from('<4I', blob, 4))


def run(root, apply):
    found = 0
    for f in FILES:
        path = os.path.join(root, f)
        d = bytearray(open(path, 'rb').read())
        for off, size in F.blobs(bytes(d)):
            blob = bytes(d[off:off + size])
            if checksum_str(blob) != TARGET: continue
            new = rewrite(blob)
            assert new and len(new) == len(blob)
            d[off:off + size] = new; found += 1
            print(f'{f} @ {off:#x}: patched ({size} bytes, new checksum {checksum_str(new)})')
        if apply and found: open(path, 'wb').write(d)
    if not found: print('overlay shader not found (already patched, or shaderfix not applied)')
    return found


if __name__ == '__main__':
    cmd, root = sys.argv[1:3]
    run(root, cmd == 'apply')
