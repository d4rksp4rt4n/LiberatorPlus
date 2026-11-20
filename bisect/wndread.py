"""Dump the game's window object ([exe+0xc3fe84], same in both builds) and the mouse fields of the
   input object, while the game runs.   python -I wndread.py"""
import os, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import importlib.util
spec = importlib.util.spec_from_file_location('fr', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fpsread.py'))
src = open(spec.origin).read().split('secs = float')[0]          # helpers only
g = {}; exec(src, g)
pid, h = g['find_pid']()
if not h: sys.exit('game not running')
base = g['module_base'](h)
wnd = g['read'](h, base + (0xc3fe84 - 0x400000), '<I')
print(f'base {base:#x} wnd {wnd:#x}')
for off in range(0, 0x40, 4):
    v = g['read'](h, wnd + off, '<i')
    print(f'  wnd+{off:#04x} = {v} ({v & 0xffffffff:#x})')
