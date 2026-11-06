"""Check that the physfix dinput8.dll hook is live in the running game."""
import struct, sys, os
sys.argv = sys.argv[:1]
src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'adread.py')).read()
exec(src.split('h = find_pid()')[0])
h = find_pid()
if not h: sys.exit('game not running')
base = module_base(h)
j = raw(h, base + (0x8914bb - 0x400000), 5)
tgt = base + (0x8914c0 - 0x400000) + struct.unpack('<i', j[1:])[0]
print('jmp', j.hex(), 'target', hex(tgt), '->', 'hooked (DLL)' if not base <= tgt < base + 9052160 else 'NOT hooked')
