"""Put edited/upscaled texture PNGs back into the game. Drag folders (or PNGs) onto repack.bat, or:
  python -I VDMod/repack.py <folder or png> [...]

PNGs are found by their names from textool.py extract (VDMod/extract/manifest.csv): <file>.mib/<NN>_<name>.png.
Keep the extract folder tree, or at least the <file>.mib folder, when a name is used by more than one .mib.
Each PNG goes into every texture that uses it (UI and UI_Eng_Dt alike), at any size, format kept.
The game file is edited in place (other entries kept); the first time, the original is saved to
VDMod/backup/Resource (restore.bat puts it back).
"""
import csv, os, shutil, sys
from collections import defaultdict
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from PIL import Image
from textool import inject

GAME = os.path.join(HERE, '..', 'DeploymentRoot', 'Resource')
BACKUP = os.path.join(HERE, 'backup', 'Resource')


def match(path, by_name):
    """Manifest PNG with the same file name whose folders agree with this file's folders the furthest back."""
    parts = os.path.abspath(path).replace('\\', '/').lower().split('/')
    best, depth = [], 0
    for key in by_name.get(parts[-1], []):
        k = key.lower().split('/'); d = 0
        while d < len(k) and k[-1 - d] == parts[-1 - d]: d += 1
        if d > depth: best, depth = [key], d
        elif d == depth: best.append(key)
    return best


def main(args):
    uses, modes = defaultdict(list), {}
    for r in csv.DictReader(open(os.path.join(HERE, 'extract', 'manifest.csv'), encoding='utf-8')):
        uses[r['png']].append((r['mib'], int(r['entry']))); modes[r['png']] = r['mode']
    by_name = defaultdict(list)
    for key in uses: by_name[key.rsplit('/', 1)[-1].lower()].append(key)

    pngs = []
    for a in args:
        if os.path.isdir(a):
            pngs += [os.path.join(dp, f) for dp, _, fs in os.walk(a) for f in fs if f.lower().endswith('.png')]
        elif a.lower().endswith('.png'): pngs.append(a)
    per_mib, bad = defaultdict(list), 0
    for p in sorted(pngs):
        m = match(p, by_name)
        if len(m) != 1:
            bad += 1
            print(f'SKIPPED {p}: ' + ('no texture has this name' if not m else
                  f'name used by {len(m)} textures, keep the folders it was in ({", ".join(x.rsplit("/", 1)[0] for x in m[:3])})'))
            continue
        if modes[m[0]] == 'RGBA' and 'A' not in Image.open(p).getbands():
            print(f'WARNING {p}: original has transparency, this PNG has none (upscaler dropped alpha?)')
        for mib, i in uses[m[0]]: per_mib[mib].append(f'{i}={p}')

    done = 0
    for mib, pairs in sorted(per_mib.items()):
        game, bak = os.path.join(GAME, mib), os.path.join(BACKUP, mib)
        if not os.path.exists(game): print(f'SKIPPED {mib}: not in the game folder'); bad += 1; continue
        print(mib)
        try:
            inject(game, game + '.new', *pairs)
        except Exception as e:
            print(f'  FAILED, game file not changed: {e}'); bad += 1
            if os.path.exists(game + '.new'): os.remove(game + '.new')
            continue
        if not os.path.exists(bak) and not os.path.exists(os.path.join(HERE, 'backup', mib)):  # old CG backups
            os.makedirs(os.path.dirname(bak), exist_ok=True); shutil.copy2(game, bak)
        os.replace(game + '.new', game); done += 1
    print(f'\n{len(pngs)} PNGs, {done} game files updated, {bad} problems' if pngs else
          'No PNGs given. Drag a folder of PNGs (named as in VDMod/extract) onto repack.bat.')


if __name__ == '__main__':
    main(sys.argv[1:])
