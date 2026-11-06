"""Self-check for gallery_zoom: capstone round-trip + run the bytes in a tiny emulator.
  python -I VDMod/test_patch.py
"""
import re, struct, sys, os
sys.path.insert(0, os.path.dirname(__file__))
import capstone
import gallery_zoom as G

code, listing = G.assemble()
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
got = [(i.address, f'{i.mnemonic} {i.op_str}'.strip()) for i in md.disasm(code, G.VA)][:len(listing)]
for (a, want), (b, have) in zip(listing, got):
    assert a == b and want == have, f'{a:x}: want "{want}" got "{have}" at {b:x}'
assert len(got) == len(listing)

# ---- tiny emulator for exactly the instructions used ----
f32 = lambda x: struct.unpack('<f', struct.pack('<f', x))[0]


class CPU:
    def __init__(s):
        s.mem = {}; s.r = dict(eax=0, ecx=0, edx=0, esp=0x30000, ebp=0); s.x = [0.0] * 8; s.flags = None

    def rd(s, a, n=4): return int.from_bytes(bytes(s.mem.get(a + i, 0) for i in range(n)), 'little')
    def wr(s, a, v, n=4):
        for i, b in enumerate((v & (1 << 8 * n) - 1).to_bytes(n, 'little')): s.mem[a + i] = b
    def rf(s, a): return struct.unpack('<f', s.rd(a).to_bytes(4, 'little'))[0]
    def wf(s, a, v): s.wr(a, int.from_bytes(struct.pack('<f', v), 'little'))

    def addr(s, op):
        inner = re.search(r'\[(.*)\]', op).group(1).replace(' - ', ' + -')
        return sum(s.r[t] if t in s.r else int(t, 0) for t in inner.split(' + ')) & 0xffffffff

    def val(s, op):                 # float source operand
        return s.x[int(op[3:])] if op.startswith('xmm') else s.rf(s.addr(op))

    def run(s, code, base):
        pc = base
        while True:
            i = next(md.disasm(code[pc - base:], pc, 1)); pc = i.address + i.size
            m, ops = i.mnemonic, [o.strip() for o in i.op_str.split(', ')] if i.op_str else []
            if m == 'push': s.r['esp'] -= 4; s.wr(s.r['esp'], s.r[ops[0]])
            elif m == 'pop': s.r[ops[0]] = s.rd(s.r['esp']); s.r['esp'] += 4
            elif m == 'ret': s.r['esp'] += 4; return
            elif m == 'sub': s.r[ops[0]] -= int(ops[1], 16)
            elif m == 'mov':
                d, src = ops
                v = s.r[src] if src in s.r else int(src, 16) if src.startswith('0x') or src.isdigit() else s.rd(s.addr(src))
                n = 1 if d.startswith('byte') else 4
                if d in s.r: s.r[d] = v
                else: s.wr(s.addr(d), v, n)
            elif m == 'or': a = s.addr(ops[0]); s.wr(a, s.rd(a, 1) | int(ops[1], 16), 1)
            elif m == 'imul': s.r[ops[0]] = s.rd(s.addr(ops[1])) * int(ops[2], 16) & 0xffffffff
            elif m == 'cmp': s.flags = ('u', s.r[ops[0]], int(ops[1], 16))
            elif m == 'comiss': s.flags = ('f', s.x[int(ops[0][3:])], s.val(ops[1]))
            elif m in ('ja', 'jmp'):
                if m == 'jmp' or s.flags[1] > s.flags[2]: pc = int(ops[0], 16)
            elif m == 'movss':
                if ops[0].startswith('xmm'): s.x[int(ops[0][3:])] = f32(s.val(ops[1]))
                else: s.wf(s.addr(ops[0]), s.x[int(ops[1][3:])])
            elif m in ('movaps',): s.x[int(ops[0][3:])] = s.val(ops[1])
            elif m == 'xorps' and ops[0] == ops[1]: s.x[int(ops[0][3:])] = 0.0
            else:
                d, v = int(ops[0][3:]), s.val(ops[1]); a = s.x[d]
                s.x[d] = f32({'addss': lambda: a + v, 'subss': lambda: a - v, 'mulss': lambda: a * v,
                              'divss': lambda: a / v, 'minss': lambda: a if a < v else v,
                              'maxss': lambda: a if a > v else v}[m]())


def model(W, H, z, px, py, typ):
    z = min(max(z, 1.0), 1.75)
    fit = min(960 / W, 544 / H); smax = max(1.75 * fit, 1.0); s = fit + (z - 1) / 0.75 * (smax - fit)
    ox, oy = max(0, (W * s - 960) / 2), max(0, (H * s - 544) / 2)
    if 0 <= typ <= 8: ox = W * s / 2
    if z > 1: px, py = max(-ox, min(px, ox)), max(-oy, min(py, oy))
    else: py = 0.0
    cy_py = -py if 0 <= typ <= 8 else py
    cx, cy = 480 + px, 272 + cy_py
    return dict(z=z, s=s, px=px, py=py, x=cx - W / 2, y=cy - H / 2, cx=cx, cy=cy)


THIS, SPR = 0x100000, 0x200000
cases = [  # W, H, z, px, py, type
    (960, 544, 1.0, 0, 0, 20), (960, 544, 1.75, 1000, -1000, 20), (960, 544, 1.3, 50, 20, 20),
    (960, 544, 1.0, -480, 0, 20),                    # slide animation offset kept at z=1
    (1440, 544, 1.0, 0, 0, 20), (1440, 544, 1.75, -9999, 9999, 20),
    (1190, 1346, 1.0, 0, 0, 0), (1190, 1346, 1.75, 0, 5000, 0), (1190, 1346, 1.75, 0, -5000, 0),
    (2136, 3124, 1.2, 300, 300, 7), (892, 1894, 2.5, 0, 0, 2), (960, 544, 0.5, 0, 0, 20),
    (1190, 1346, 1.75, 9999, 0, 0), (1190, 1346, 1.75, -9999, 0, 0),   # solo: center any column
    (1190, 1346, 1.3, 400, 0, 3), (1190, 1346, 1.0, 400, 0, 3),        # z=1: px free (slide)
    (1440, 544, 1.75, 9999, 0, -1),                                     # CG keeps edge clamp
]
for W, H, z, px, py, typ in cases:
    c = CPU(); c.r['ecx'] = THIS
    c.wr(THIS + 0xd80, SPR); c.wf(SPR + 0x108, W); c.wf(SPR + 0x10c, H)
    c.wf(THIS + 0xdb4, z); c.wf(THIS + 0xda0, px); c.wf(THIS + 0xda4, py)
    c.wr(THIS + 0xda8, 0); c.wf(THIS + 0xdac, 1.0); c.wr(THIS + 0xbb0, 3); c.wr(THIS + 3 * 0x1c + 0xd4, typ & 0xffffffff)
    c.wr(c.r['esp'] - 4, 0); c.r['esp'] -= 4                 # fake return address
    c.run(code, G.VA)
    m = model(W, H, z, px, py, typ)
    have = dict(z=c.rf(THIS + 0xdb4), s=c.rf(SPR + 0x114), px=c.rf(THIS + 0xda0), py=c.rf(THIS + 0xda4),
                x=c.rf(SPR + 0xb8), y=c.rf(SPR + 0xbc), cx=c.rf(SPR + 0xd8), cy=c.rf(SPR + 0xdc))
    for k in m: assert abs(have[k] - m[k]) < 1e-3 * max(1, abs(m[k])), (W, H, z, px, py, typ, k, have[k], m[k])
    assert c.rf(SPR + 0x118) == have['s'] and c.rf(SPR + 0xc4) == 1.0 and c.rd(SPR + 0x120, 1) == 0x41
    assert c.rd(SPR + 0x11e, 1) == 1 and c.r['esp'] == 0x30000
    print(f'ok {W}x{H} z={z:<4} -> s={have["s"]:.3f} pan=({have["px"]:.0f},{have["py"]:.0f}) pos=({have["x"]:.0f},{have["y"]:.0f})')
print(f'all {len(cases)} cases ok, {len(listing)} instructions, {len(code.rstrip(bytes([0xcc])))} bytes')
