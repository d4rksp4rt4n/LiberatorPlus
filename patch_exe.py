"""LEGACY: all of these fixes now run in memory from DeploymentRoot/dinput8.dll (VDMod/physfix,
options in DeploymentRoot/vdmod.ini); the exe stays original except the LAA flag (VDPatch.exe).
Kept as the reference the DLL was checked against (bisect/dllcheck.py).

Gallery fixes for VD_BHIKKHUNI.exe (Steam main branch, 32-bit).

1) size: HD CGs shown at screen size (below).
2) zoom: gallery opens pictures fit-to-screen, zooms to 1:1, pans the whole
   picture (gallery_zoom.py; self-check: python -I VDMod/test_patch.py).

The gallery (CCollection_Pic) sizes the picture sprite from the texture size, so
upscaled CGs show zoomed in. Patch: if texture height is k*544 (k>1), divide the
sprite width/height by k. Solo images (heights 1346..3124) are never multiples
of 544, so they are untouched. Works for 2x/3x/4x CGs.

  python patch_exe.py check   path/to/VD_BHIKKHUNI.exe   # verify only
  python patch_exe.py apply   path/to/VD_BHIKKHUNI.exe   # writes .orig backup first
"""
import struct, sys, os, shutil
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

SITE_W, SITE_H = 0x5c3aef, 0x5c3b19          # movzx eax,[edx+10h/12h]; mov ecx,[ebx+0D80h]
ORIG_W = bytes.fromhex('0fb742108b8b800d0000')
ORIG_H = bytes.fromhex('0fb742128b8b800d0000')
CAVE = 0x8ccef0                               # unused tail of .text (vsize 0x4cbee6, raw 0x4cc000)
H544 = 544


def rel(src_next, dst):
    return struct.pack('<i', dst - src_next)


def build_cave():
    c = bytearray()
    scale = CAVE + 32
    for off in (0x10, 0x12):                  # cave_w @CAVE, cave_h @CAVE+16
        here = CAVE + len(c)
        c += bytes([0x0f, 0xb7, 0x42, off])   # movzx eax, word [edx+off]
        c += b'\xe8' + rel(here + 9, scale)   # call scale
        c += bytes.fromhex('8b8b800d0000')    # mov ecx, [ebx+0xd80]
        c += b'\xc3'                          # ret
    assert len(c) == 32
    s = bytes.fromhex(
        '51 52 50'                # push ecx; push edx; push eax
        '0fb74212'                # movzx eax, word [edx+0x12]   (height)
        '3d20020000'              # cmp eax, 544
        '7617'                    # jbe .no
        '31d2'                    # xor edx, edx
        'b920020000'              # mov ecx, 544
        'f7f1'                    # div ecx        eax=k, edx=h%544
        '85d2'                    # test edx, edx
        '750a'                    # jnz .no
        '89c1'                    # mov ecx, eax   (k)
        '58'                      # pop eax        (value)
        '31d2'                    # xor edx, edx
        'f7f1'                    # div ecx        value/k
        '5a 59 c3'                # pop edx; pop ecx; ret
        '58 5a 59 c3')            # .no: pop eax; pop edx; pop ecx; ret
    return bytes(c + s)


def call_site(site, target):
    return b'\xe8' + rel(site + 5, target) + b'\x90' * 5


def layout(d):
    pe = struct.unpack_from('<I', d, 0x3c)[0]
    so = pe + 24 + struct.unpack_from('<H', d, pe + 20)[0]
    base = struct.unpack_from('<I', d, pe + 0x34)[0]
    nm, vs, va, rs, ra = struct.unpack_from('<8sIIII', d, so)
    assert nm.rstrip(b'\0') == b'.text'
    return so, base + va, vs, ra, rs


def relocs_in(d, lo, hi):
    """File offsets of active base-relocation entries whose target VA is in [lo, hi)."""
    pe = struct.unpack_from('<I', d, 0x3c)[0]
    base = struct.unpack_from('<I', d, pe + 0x34)[0]
    rva, size = struct.unpack_from('<II', d, pe + 0x78 + 8 * 5)
    so = pe + 24 + struct.unpack_from('<H', d, pe + 20)[0]
    for i in range(struct.unpack_from('<H', d, pe + 6)[0]):
        _, vs, va, rs, ra = struct.unpack_from('<8sIIII', d, so + 40 * i)
        if va <= rva < va + rs: o = ra + rva - va; break
    end, out = o + size, []
    while o < end:
        page, bs = struct.unpack_from('<II', d, o)
        for k in range((bs - 8) // 2):
            e = struct.unpack_from('<H', d, o + 8 + 2 * k)[0]
            if e >> 12 and lo <= base + page + (e & 0xfff) < hi: out.append(o + 8 + 2 * k)
        o += bs
    return out


ZOOM_ORIG_SHA = '0d29e2bc33a617c9ed012103bfa40bedf715457c27ecc535d749113d6e2a249d'
ZOOM_V1_SHA = '71ba336253a17282e065e1cf1636d11116267ff2efebb18882647ac31e108e4b'   # first version, upgradable


def patch_zoom(d):
    """Gallery zoom/pan rewrite (see gallery_zoom.py). Returns status string; edits d in place."""
    import hashlib, gallery_zoom as G
    so, tva, vs, ra, rs = layout(d)
    o = ra + G.VA - tva
    code, _ = G.assemble()
    if d[o:o + G.SIZE] == code:
        return 'zoom: already patched'
    assert hashlib.sha256(d[o:o + G.SIZE]).hexdigest() in (ZOOM_ORIG_SHA, ZOOM_V1_SHA), 'zoom fn: unexpected bytes'
    d[o:o + G.SIZE] = code
    for r in relocs_in(d, G.VA, G.VA + G.SIZE):   # old absolute-address fixups would corrupt the new code
        struct.pack_into('<H', d, r, 0)           # IMAGE_REL_BASED_ABSOLUTE = skip
    assert not relocs_in(d, G.VA, G.VA + G.SIZE)
    return 'zoom: patched'


def patch_laa(d):
    """Large Address Aware: 32-bit game may use 4 GB instead of 2 GB."""
    o = struct.unpack_from('<I', d, 0x3c)[0] + 22
    ch = struct.unpack_from('<H', d, o)[0]
    if ch & 0x20: return 'laa: already patched'
    struct.pack_into('<H', d, o, ch | 0x20)
    return 'laa: patched'


MIP_EDITS = [  # material sampler creation (0x863030): MaxLOD was 0 unless the material's mip mode == 1
    (0x86307c, '7517', '9090'),                          # jne skip  -> nop: every mode reaches MaxLOD=FLT_MAX
    (0x863087, 'c745f400000000', 'c745f4ffff7f7f'),      # mode 0: MaxLOD = 0 -> FLT_MAX
]


def patch_mip(d):
    """Let material samplers use mip levels (fixes distant texture shimmer).
    Material 'mip mode': 0 -> MaxLOD 0, 1 -> mips, 2+ -> MaxLOD 0 (vanilla). Some effect textures ship
    with garbage low mips (black box in transformation flash), so this can be limited per mode:
    MipFix 0 = vanilla, 1 = all modes, 2 = only modes 2+, 3 = only mode 0."""
    mode = option('MipFix', 1)
    assert mode in (0, 1, 2, 3), 'MipFix must be 0..3'
    (jne_va, jne_o, jne_n), (imm_va, imm_o, imm_n) = MIP_EDITS
    want = {jne_va: jne_n if mode in (1, 2) else jne_o, imm_va: imm_n if mode in (1, 3) else imm_o}
    assert not relocs_in(d, 0x86307c, 0x86308e)
    before = bytes(d)
    for va, o, n in MIP_EDITS:
        p = off_text(d, va); ln = len(bytes.fromhex(o))
        assert d[p:p + ln].hex() in (o, n), f'mip: unexpected bytes at {va:#x}'
        d[p:p + ln] = bytes.fromhex(want[va])
    return f'mip(mode {mode}): ' + ('patched' if bytes(d) != before else 'already patched')


ANISO = 16                                  # anisotropy level for material samplers (1..16)
ANISO_SITE, ANISO_CAVE = 0x86304c, 0x8ccf40  # site: mov dword ptr [ebp-0x30], 1 (AddressW = WRAP)
ANISO_ORIG = bytes.fromhex('c745d001000000')


def build_aniso():
    assert 1 <= ANISO <= 16
    return bytes.fromhex(
        'c745d001000000'          # mov dword ptr [ebp-0x30], 1     (replaced instruction)
        '817dc415000000'          # cmp dword ptr [ebp-0x3c], 0x15  (filter == MIN_MAG_MIP_LINEAR?)
        '750e'                    # jne ret
        'c745c455000000'          # mov dword ptr [ebp-0x3c], 0x55  (ANISOTROPIC)
        'c745d8') + struct.pack('<I', ANISO) + b'\xc3'   # mov [ebp-0x28], ANISO (MaxAnisotropy); ret


def patch_aniso(d):
    """Material samplers: trilinear -> anisotropic (point-filtered ones untouched)."""
    so, tva, vs, ra, rs = layout(d)
    off = lambda v: ra + v - tva
    cave, site = build_aniso(), b'\xe8' + rel(ANISO_SITE + 5, ANISO_CAVE) + b'\x90\x90'
    if d[off(ANISO_SITE):off(ANISO_SITE) + 7] == site and d[off(ANISO_CAVE):off(ANISO_CAVE) + len(cave)] == cave:
        return 'aniso: already patched'
    assert d[off(ANISO_SITE):off(ANISO_SITE) + 7] == ANISO_ORIG, 'aniso: unexpected bytes at site'
    assert vs == rs, 'aniso: needs the size patch first (extends .text VirtualSize)'
    assert d[off(ANISO_CAVE):off(ANISO_CAVE) + len(cave)] == bytes(len(cave)), 'aniso: cave not empty'
    assert ANISO_CAVE >= CAVE + len(build_cave()) and ANISO_CAVE + len(cave) <= tva + rs
    assert not relocs_in(d, ANISO_SITE, ANISO_SITE + 7)
    d[off(ANISO_CAVE):off(ANISO_CAVE) + len(cave)] = cave
    d[off(ANISO_SITE):off(ANISO_SITE) + 7] = site
    return 'aniso: patched'


OPTIONS_INI = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'DeploymentRoot', 'vdmod.ini')


def option(name, default):
    if os.path.exists(OPTIONS_INI):
        for line in open(OPTIONS_INI):
            line = line.split(';')[0].strip()
            if '=' in line and line.split('=')[0].strip() == name:
                return type(default)(line.split('=', 1)[1].strip())
    return default


# Intro: logo list = [intro video, HPG, Meteorise, CRIWARE]; CLogoManager (state at +0x1bc)
INTRO_CALLS = (0x705e1b, 0x705e38)   # state 1: call SetState(6) = start playback
SET_STATE, NEXT_ENTRY = 0x7059b0, 0x706570
INTRO_JL = 0x706587                  # NextEntry: 'jl more_entries' (7c 29)
INTRO_STUB = 0x8ccf60                # set index past the end, call NextEntry -> normal end path (title)


def patch_intro(d):
    mode = option('SkipIntro', 0)
    assert mode in (0, 1, 2), 'SkipIntro must be 0, 1 or 2'
    so, tva, vs, ra, rs = layout(d)
    off = lambda v: ra + v - tva
    stub = bytes.fromhex('c781c8010000ff7f0000') + b'\xe8' + rel(INTRO_STUB + 15, NEXT_ENTRY) + bytes.fromhex('c20400')
    s0 = off(INTRO_STUB)
    assert d[s0:s0 + len(stub)] in (stub, bytes(len(stub))), 'intro: cave in use'
    assert d[off(INTRO_JL):off(INTRO_JL) + 2] in (b'\x7c\x29', b'\x90\x90'), 'intro: unexpected bytes'
    want_target = INTRO_STUB if mode == 2 else SET_STATE
    before = bytes(d)
    for site in INTRO_CALLS:
        o = off(site)
        assert d[o] == 0xe8 and struct.unpack_from('<i', d, o + 1)[0] + site + 5 in (SET_STATE, INTRO_STUB)
        d[o + 1:o + 5] = rel(site + 5, want_target)
    d[s0:s0 + len(stub)] = stub if mode == 2 else bytes(len(stub))
    d[off(INTRO_JL):off(INTRO_JL) + 2] = b'\x90\x90' if mode == 1 else b'\x7c\x29'
    return f'intro(mode {mode}): ' + ('patched' if bytes(d) != before else 'already patched')


def voff(d, va):
    """File offset of a VA in any section."""
    pe = struct.unpack_from('<I', d, 0x3c)[0]
    base = struct.unpack_from('<I', d, pe + 0x34)[0]
    so = pe + 24 + struct.unpack_from('<H', d, pe + 20)[0]
    for i in range(struct.unpack_from('<H', d, pe + 6)[0]):
        _, vs, sva, rs, ra = struct.unpack_from('<8sIIII', d, so + 40 * i)
        if base + sva <= va < base + sva + max(vs, rs): return ra + va - base - sva
    raise ValueError(hex(va))


# Frame rate: limiter waits (index+1)/fps with fps hard-coded 60; game logic steps 480/fps ticks per frame
FPS_IMM = 0x85af9a          # mov dword ptr [ebp-4], 60   (c7 45 fc imm32)
FPS_WORDS = 0x8eac90        # fps per index (60,30,20,15), dword stride -> 480/fps tick step
FPS_TIMES = 0x8eac80        # frame time per index (1/60, 1/30, 1/20, 1/15)


def patch_fps(d):
    f = option('FrameRate', 60)
    assert f in (60, 80, 96, 120, 160, 240), 'FrameRate must divide 480 (game logic): 60, 80, 96, 120, 160 or 240'
    o = off_text(d, FPS_IMM)
    assert d[o:o + 3] == b'\xc7\x45\xfc', 'fps: unexpected bytes'
    before = bytes(d)
    d[o + 3:o + 7] = struct.pack('<I', f)
    for i in range(4):
        rate = f // (i + 1)
        struct.pack_into('<H', d, voff(d, FPS_WORDS + 4 * i), rate)
        struct.pack_into('<f', d, voff(d, FPS_TIMES + 4 * i), (i + 1) / f)
    return f'fps({f}): ' + ('patched' if bytes(d) != before else 'already patched')


# DLC check: while the DLC worker is busy, set the renderer's 'unlimited fps' flag (+0x1c6) so the
# frame-paced check runs at full speed; it is cleared again as soon as the worker is idle.
DLC_SITE, DLC_STUB = 0x6d886c, 0x8ccf80     # site: mov ecx, [eax+0x2d0]  (eax = render manager)
DLC_ORIG = bytes.fromhex('8b88d0020000')


def build_dlc_stub():
    return bytes.fromhex(
        '8b88d0020000'      # mov ecx, [eax+0x2d0]       (replaced instruction: DLC worker)
        '52'                # push edx
        '31d2'              # xor edx, edx
        '833903'            # cmp dword ptr [ecx], 3
        '0f94c2'            # sete dl
        '0a5108'            # or dl, byte ptr [ecx+8]      busy = (state == 3) | flag
        '8890c6010000'      # mov byte ptr [eax+0x1c6], dl unlimited fps while busy
        '5a'                # pop edx
        'c3')               # ret


def patch_dlc(d):
    on = option('FastDlcCheck', 0)
    o, s = off_text(d, DLC_SITE), off_text(d, DLC_STUB)
    stub, call = build_dlc_stub(), b'\xe8' + rel(DLC_SITE + 5, DLC_STUB) + b'\x90'
    assert d[o:o + 6] in (DLC_ORIG, call) and d[s:s + len(stub)] in (stub, bytes(len(stub))), 'dlc: unexpected bytes'
    assert not relocs_in(d, DLC_SITE, DLC_SITE + 6)
    before = bytes(d)
    d[o:o + 6] = call if on else DLC_ORIG
    d[s:s + len(stub)] = stub if on else bytes(len(stub))
    return f'dlc(fast={on}): ' + ('patched' if bytes(d) != before else 'already patched')


def toggle(d, va, orig_hex, new_hex, on, name):
    o = off_text(d, va); orig, new = bytes.fromhex(orig_hex), bytes.fromhex(new_hex)
    assert d[o:o + len(orig)] in (orig, new), f'{name}: unexpected bytes'
    assert not relocs_in(d, va, va + len(orig))
    before = bytes(d[o:o + len(orig)])
    d[o:o + len(orig)] = new if on else orig
    return f'{name}({int(bool(on))}): ' + ('patched' if bytes(d[o:o + len(orig)]) != before else 'already patched')


def patch_limiter(d):
    # frame limiter: 'setae al' picks Sleep(1) when >= 3 ms remain; without timeBeginPeriod that sleeps
    # ~15.6 ms and breaks any lock above 60 fps -> always Sleep(0) (yield) = exact pacing, one busy core
    return toggle(d, 0x855d9c, '0f93c0', '0f1f00', option('PreciseLimiter', 0), 'limiter')


def patch_vsync(d):
    # Present: 'setne bl' = sync interval from the vsync setting; the game's fullscreen mode is 60 Hz,
    # so vsync caps at 60. Force sync interval 0 (the frame limiter does the pacing).
    return toggle(d, 0x85afaf, '0f95c3', '31db90', option('ForceVSyncOff', 0), 'vsyncoff')


# Physics (PhysicsRate) is done at runtime by VDMod/physfix (dinput8.dll proxy), not in the exe.


def off_text(d, va):
    so, tva, vs, ra, rs = layout(d)
    return ra + va - tva


def patch(d):
    d = bytearray(d)
    msgs = [patch_size(d), patch_zoom(d), patch_laa(d), patch_mip(d), patch_aniso(d), patch_intro(d),
            patch_fps(d), patch_dlc(d), patch_limiter(d), patch_vsync(d)]
    return (bytes(d) if any(m.endswith(': patched') for m in msgs) else None), ', '.join(msgs)


def patch_size(d):
    so, tva, vs, ra, rs = layout(d)
    off = lambda v: ra + v - tva
    cave = build_cave()
    patched = (d[off(SITE_W):off(SITE_W) + 10] == call_site(SITE_W, CAVE) and
               d[off(SITE_H):off(SITE_H) + 10] == call_site(SITE_H, CAVE + 16) and
               d[off(CAVE):off(CAVE) + len(cave)] == cave)
    if patched:
        return 'size: already patched'
    assert d[off(SITE_W):off(SITE_W) + 10] == ORIG_W, 'unexpected bytes at width site (different exe version?)'
    assert d[off(SITE_H):off(SITE_H) + 10] == ORIG_H, 'unexpected bytes at height site'
    assert vs == 0x4cbee6 and rs == 0x4cc000, 'unexpected .text layout'
    assert d[off(CAVE):off(CAVE) + len(cave)] == bytes(len(cave)), 'cave not empty'
    assert CAVE + len(cave) <= tva + rs
    d[off(CAVE):off(CAVE) + len(cave)] = cave
    d[off(SITE_W):off(SITE_W) + 10] = call_site(SITE_W, CAVE)
    d[off(SITE_H):off(SITE_H) + 10] = call_site(SITE_H, CAVE + 16)
    struct.pack_into('<I', d, so + 8, rs)    # VirtualSize covers the cave
    return 'size: patched'


def rule(value, h):                           # reference of the asm, for the self-check
    return value // (h // H544) if h > H544 and h % H544 == 0 else value


if __name__ == '__main__':
    for (w, h), want in {(960, 544): (960, 544), (1920, 1088): (960, 544), (2880, 1088): (1440, 544),
                         (3840, 2176): (960, 544), (2136, 3124): (2136, 3124), (1190, 1346): (1190, 1346)}.items():
        assert (rule(w, h), rule(h, h)) == want, (w, h)
    cmd, exe = sys.argv[1:3]
    new, msg = patch(open(exe, 'rb').read())
    if cmd == 'apply' and new:
        if not os.path.exists(exe + '.orig'):
            shutil.copy2(exe, exe + '.orig')
        open(exe, 'wb').write(new)
    print(msg if cmd == 'apply' else 'check: ' + msg.replace('patched', 'would patch').replace('already would patch', 'already patched'))
