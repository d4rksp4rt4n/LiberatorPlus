"""Function-level diff of two builds of VD_BHIKKHUNI.exe.
  python -I exediff.py public.exe beta.exe
Functions = .text chunks separated by int3 padding; call/jmp rel32 and relocated dwords are masked so
moved code still matches. Prints the changed/added/removed functions with the strings they use."""
import sys, re, difflib, hashlib, pefile, capstone

md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)


def load(path):
    pe = pefile.PE(path); img = bytearray(pe.get_memory_mapped_image()); B = pe.OPTIONAL_HEADER.ImageBase
    t = pe.sections[0]; lo, hi = t.VirtualAddress, t.VirtualAddress + t.Misc_VirtualSize
    rel = set()
    for blk in pe.DIRECTORY_ENTRY_BASERELOC:
        for r in blk.entries:
            if r.type: rel.add(r.rva)
    norm = bytearray(img)
    for r in rel: norm[r:r + 4] = b'\0\0\0\0'                     # absolute addresses
    funcs = []
    for m in re.finditer(rb'(?:[^\xcc]|\xcc(?!\xcc))+', bytes(img[lo:hi])):
        if m.end() - m.start() < 4: continue
        a, b = lo + m.start(), lo + m.end()
        n = bytearray(norm[a:b])
        for i in md.disasm(bytes(img[a:b]), 0):                 # relative call/jmp targets
            if i.bytes[0] in (0xe8, 0xe9) and i.size == 5: n[i.address + 1:i.address + 5] = b'\0\0\0\0'
        funcs.append((B + a, b - a, hashlib.md5(n).hexdigest()))
    return pe, img, B, rel, funcs


def strings_used(pe, img, B, rel, va, size):
    out = []
    for r in sorted(x for x in rel if va - B <= x < va - B + size):
        p = int.from_bytes(img[r:r + 4], 'little') - B
        if 0 <= p < len(img):
            m = re.match(rb'[\x20-\x7e]{4,}', bytes(img[p:p + 80]))
            if m: out.append(m.group().decode())
    return out


A, Bx = load(sys.argv[1]), load(sys.argv[2])
sm = difflib.SequenceMatcher(None, [f[2] for f in A[4]], [f[2] for f in Bx[4]], autojunk=False)
same = sum(b.size for b in sm.get_matching_blocks())
print(f'functions: public {len(A[4])}, beta {len(Bx[4])}, identical {same}')
for tag, i1, i2, j1, j2 in sm.get_opcodes():
    if tag == 'equal': continue
    print(f'\n[{tag}] public {i2 - i1} fn, beta {j2 - j1} fn')
    for side, (pe, img, B, rel, funcs), lo, hi in (('public', A, i1, i2), ('beta  ', Bx, j1, j2)):
        for va, size, _ in funcs[lo:hi]:
            s = strings_used(pe, img, B, rel, va, size)
            print(f'  {side} {va:#x} {size:5} bytes  {"; ".join(dict.fromkeys(s))[:150]}')
