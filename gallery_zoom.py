"""Replacement for the gallery zoom/pan function (VA 0x5c3d70, 731 bytes).

Original: zoom z in [1,1.75] scales the picture; pan limits assume a 960x544
picture, so large solo images / the wide CG can barely be panned.

New (edx=this, ecx=sprite; sprite size W,H at +108h/+10Ch):
  fit  = min(960/W, 544/H)            whole picture visible at z=1
  smax = max(1.75*fit, 1.0)           max zoom: 1.75x fit, at least 1:1 pixels
  s    = fit + (z-1)/0.75*(smax-fit)
  pan  clamped to the scaled picture: |px| <= max(0,(W*s-960)/2), same for y
       solo images (type 0..8): |px| <= W*s/2, so any column can be centered
  z<=1: py=0 and px left free (the picture-switch slide animation uses px)
16:9 CGs (960x544 sprite) behave exactly as before (fit=1, s=z).
Position-independent: constants live on the stack, no absolute addresses.
"""
import struct

VA, SIZE = 0x5c3d70, 0x5c404b - 0x5c3d70


def f32(x): return struct.pack('<f', x)


# (expected capstone text, bytes). Labels: ('L', name). Short jumps: ('J', opcode, label, text_prefix)
_ = bytes.fromhex
EBP = lambda d: struct.pack('<b', d)
D32 = lambda d: struct.pack('<I', d)
SSE = {'movss': 0x10, 'addss': 0x58, 'mulss': 0x59, 'subss': 0x5c, 'minss': 0x5d, 'divss': 0x5e, 'maxss': 0x5f}
H = lambda n: str(n) if n < 10 else hex(n)   # capstone style
R32 = ['eax', 'ecx', 'edx', 'ebx', 'esp', 'ebp', 'esi', 'edi']


def ss_m(op, x, base, disp):                    # op xmm, dword ptr [base + disp32]
    return (f'{op} xmm{x}, dword ptr [{base} + {hex(disp)}]',
            _('f30f') + bytes([SSE[op], 0x80 | x << 3 | R32.index(base)]) + D32(disp))


def ss_st(base, disp, x):                       # movss dword ptr [base + disp32], xmm
    return (f'movss dword ptr [{base} + {hex(disp)}], xmm{x}',
            _('f30f11') + bytes([0x80 | x << 3 | R32.index(base)]) + D32(disp))


def ss_k(op, x, k):                             # op xmm, dword ptr [ebp - k]
    return (f'{op} xmm{x}, dword ptr [ebp - {H(k)}]', _('f30f') + bytes([SSE[op], 0x40 | x << 3 | 5]) + EBP(-k))


def ss_r(op, d, s):                             # op xmm, xmm
    return (f'{op} xmm{d}, xmm{s}', _('f30f') + bytes([SSE[op], 0xc0 | d << 3 | s]))


def ps_r(op, d, s):                             # movaps/xorps xmm, xmm
    return (f'{op} xmm{d}, xmm{s}', _('0f') + bytes([{'movaps': 0x28, 'xorps': 0x57}[op], 0xc0 | d << 3 | s]))


def k_const(k, v):                              # mov dword ptr [ebp - k], float
    return (f'mov dword ptr [ebp - {H(k)}], {hex(struct.unpack("<I", f32(v))[0])}', _('c745') + EBP(-k) + f32(v))


ONE, MAXZ, SW, SH, HALF, RNG = 4, 8, 0xc, 0x10, 0x14, 0x18
THIS, SPR = 'edx', 'ecx'

PROG = [
    ('push ebp', _('55')), ('mov ebp, esp', _('8bec')), ('sub esp, 0x20', _('83ec20')), ('mov edx, ecx', _('8bd1')),
    k_const(ONE, 1.0), k_const(MAXZ, 1.75), k_const(SW, 960.0), k_const(SH, 544.0), k_const(HALF, 0.5), k_const(RNG, 0.75),
    # z = clamp(z, 1, 1.75)
    ss_m('movss', 0, THIS, 0xdb4), ss_k('maxss', 0, ONE), ss_k('minss', 0, MAXZ), ss_st(THIS, 0xdb4, 0),
    ('mov ecx, dword ptr [edx + 0xd80]', _('8b8a800d0000')),
    ss_m('movss', 1, SPR, 0x108), ss_m('movss', 2, SPR, 0x10c),          # W, H
    ss_k('movss', 3, SW), ss_r('divss', 3, 1), ss_k('movss', 4, SH), ss_r('divss', 4, 2),
    ss_r('minss', 3, 4),                                                    # fit
    ps_r('movaps', 4, 3), ss_k('mulss', 4, MAXZ), ss_k('maxss', 4, ONE),    # smax
    ss_r('subss', 4, 3), ss_k('subss', 0, ONE), ss_r('mulss', 0, 4), ss_k('divss', 0, RNG), ss_r('addss', 0, 3),  # s
    ss_r('mulss', 1, 0), ss_k('subss', 1, SW), ss_k('mulss', 1, HALF),      # (W*s-960)/2
    ss_r('mulss', 2, 0), ss_k('subss', 2, SH), ss_k('mulss', 2, HALF),      # (H*s-544)/2
    ps_r('xorps', 5, 5), ss_r('maxss', 1, 5), ss_r('maxss', 2, 5),         # ox, oy
    # eax = picture type; solo images (0..8): ox = W*s/2
    ('imul eax, dword ptr [edx + 0xbb0], 0x1c', _('6b82b00b00001c')),
    ('mov eax, dword ptr [edx + eax + 0xd4]', _('8b8402d4000000')),
    ('cmp eax, 8', _('83f808')), ('J', 0x77, 'cgpan', 'ja'),
    ss_m('movss', 1, SPR, 0x108), ss_r('mulss', 1, 0), ss_k('mulss', 1, HALF),
    ('L', 'cgpan'),
    ss_m('movss', 3, THIS, 0xda0), ss_m('movss', 4, THIS, 0xda4),          # px, py
    ss_m('movss', 6, THIS, 0xdb4), (f'comiss xmm6, dword ptr [ebp - {H(ONE)}]', _('0f2f75') + EBP(-ONE)),
    ('J', 0x77, 'zoomed', 'ja'),
    ps_r('xorps', 4, 4), ('J', 0xeb, 'store', 'jmp'),
    ('L', 'zoomed'),
    ss_r('minss', 3, 1), ss_r('minss', 4, 2),
    ps_r('xorps', 6, 6), ss_r('subss', 6, 1), ss_r('maxss', 3, 6),
    ps_r('xorps', 6, 6), ss_r('subss', 6, 2), ss_r('maxss', 4, 6),
    ('L', 'store'),
    ss_st(THIS, 0xda0, 3), ss_st(THIS, 0xda4, 4),
    # solo images (type 0..8, eax still = type) have inverted Y pan input
    ('cmp eax, 8', _('83f808')), ('J', 0x77, 'notchar', 'ja'),
    ps_r('xorps', 6, 6), ss_r('subss', 6, 4), ps_r('movaps', 4, 6),
    ('L', 'notchar'),
    ss_k('movss', 5, SW), ss_k('mulss', 5, HALF), ss_r('addss', 3, 5),     # cx = 480 + px
    ss_k('movss', 5, SH), ss_k('mulss', 5, HALF), ss_r('addss', 4, 5),     # cy = 272 + py
    ss_m('movss', 1, SPR, 0x108), ss_k('mulss', 1, HALF), ps_r('movaps', 5, 3), ss_r('subss', 5, 1), ss_st(SPR, 0xb8, 5),
    ss_m('movss', 2, SPR, 0x10c), ss_k('mulss', 2, HALF), ps_r('movaps', 5, 4), ss_r('subss', 5, 2), ss_st(SPR, 0xbc, 5),
    ('mov eax, dword ptr [edx + 0xda8]', _('8b82a80d0000')),
    ('mov dword ptr [ecx + 0xc0], eax', _('8981c0000000')), ('mov dword ptr [ecx + 0xe0], eax', _('8981e0000000')),
    ('mov eax, dword ptr [edx + 0xdac]', _('8b82ac0d0000')),
    ('mov dword ptr [ecx + 0xc4], eax', _('8981c4000000')), ('mov dword ptr [ecx + 0xe4], eax', _('8981e4000000')),
    ss_st(SPR, 0xd8, 3), ss_st(SPR, 0xdc, 4),                              # zoom pivot = picture center
    ss_st(SPR, 0x114, 0), ss_st(SPR, 0x118, 0),                            # scale
    ('mov byte ptr [ecx + 0x11e], 1', _('c6811e01000001')),
    ('or byte ptr [ecx + 0x120], 0x41', _('808920010000' + '41')),
    ('mov esp, ebp', _('8be5')), ('pop ebp', _('5d')), ('ret', _('c3')),
]


def assemble(va=VA):
    """Returns (code bytes, [(va, expected_text)]). Short jumps resolved in two passes."""
    labels, pos = {}, 0
    for it in PROG:
        if it[0] == 'L': labels[it[1]] = pos
        else: pos += 2 if it[0] == 'J' else len(it[1])
    out, listing = bytearray(), []
    for it in PROG:
        if it[0] == 'L': continue
        if it[0] == 'J':
            rel = labels[it[2]] - (len(out) + 2)
            assert -128 <= rel <= 127
            listing.append((va + len(out), f'{it[3]} {hex(va + labels[it[2]])}'))
            out += bytes([it[1]]) + struct.pack('<b', rel)
        else:
            listing.append((va + len(out), it[0])); out += it[1]
    assert len(out) <= SIZE, len(out)
    return bytes(out) + b'\xcc' * (SIZE - len(out)), listing
