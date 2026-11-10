# Liberator+ 1.0.0

Fixes and options for **Valkyrie Drive -Bhikkhuni-** on PC (Steam): higher frame rates, sharper textures, rendering bug fixes, 4K output and quality-of-life tweaks. Optional packs add HD CGs, mipmapped stage textures and a 4K opening movie.

Author: DarkSpartan

## Requirements

- Valkyrie Drive -Bhikkhuni- on Steam, public branch (v1.05) or beta branch (v1.06).
- Windows 10 or 11.

## Install

1. Copy `dinput8.dll`, `vdmod.ini` and `VDPatch.exe` into the game's `DeploymentRoot` folder, next to `VD_BHIKKHUNI.exe`.
2. Optional packs: copy each pack's `DeploymentRoot` folder over the game's.
3. Start the game from Steam. On the first start, the mod offers to set the 4 GB memory flag in the game exe; choose Yes and the game restarts by itself.

Always start the game from Steam. Starting `VD_BHIKKHUNI.exe` directly crashes a few seconds in, with or without the mod.

## What it does

All fixes are switched in `vdmod.ini`: close the game, edit, start the game again. `0` turns a fix off and gives the original behaviour. Each option is explained in the file itself. After every start, `vdmod.log` lists each fix as `on`, `off` or `SKIPPED`.

| Area | Options |
| --- | --- |
| Frame rate | `FrameRate` (60 to 240), `PreciseLimiter`, `ForceVSyncOff`, `PhysicsRate` (hair and bust physics behave as at 30 fps) |
| Graphics | `MipFix` (no distant shimmer), `Anisotropy`, `MSAAFix` (no white flashes on thin edges), `BlackWallFix` (no black patches on walls), `ShadowResolution`, `MaxResolution` (fullscreen up to 4K with DSR/VSR) |
| Gallery | `GalleryHDFit` (HD CGs at screen size), `GalleryZoom` (fit to screen, zoom to 1:1, full panning) |
| Boot and menus | `SkipIntro`, `FastDlcCheck`, `SkipRoomRanking` (no "Server Connect" box after the Dressing Room) |
| Memory | `LargeAddressAware` (keeps the 4 GB flag set after Steam updates) |
| Always on | Crash guards: Screen Size menu after a resolution change, and a rare crash in the game's texture loading |

The game exe on disk is never changed, except for the 4 GB memory flag. Every fix checks the game code before patching it; on an unknown game version that fix is skipped and the rest still work.

## Optional packs

| Pack | Contents |
| --- | --- |
| `CGPack` | Gallery and story CGs at 4x, title menu at 2x, Koharu's Vault > Voice portrait fixed. Needs `GalleryHDFit=1`. |
| `MipFixPack` | Stage and background textures with mipmaps. Used only with `MipFix=1`. |
| `OPVideo4K` | Opening movie at 3840x2160 with the original audio. |

## Uninstall

Delete `dinput8.dll`, `vdmod.ini`, `VDPatch.exe` and `vdmod.log` from `DeploymentRoot`, then run **Verify integrity of game files** in Steam. That also puts back the original textures, CGs and movie, and clears the 4 GB flag.

## License

Copyright (c) 2026 DarkSpartan

Liberator+ is free. You may use, copy, modify and share it, in whole or in part, including in other mods, as long as this notice stays with it. It may not be sold or offered only behind a paywall.

THE MOD IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, INCLUDING LOSS OF SAVE DATA, ARISING FROM OR IN CONNECTION WITH THE MOD OR ITS USE. Back up your saves; use at your own risk.

Liberator+ is an unofficial fan project. It is not affiliated with, endorsed or supported by Meteorise, Marvelous, or any other developer or publisher of Valkyrie Drive -Bhikkhuni-. Do not contact them for support with the mod.

Valkyrie Drive -Bhikkhuni-, its characters, artwork, movies and all other game content belong to their respective owners. The optional packs contain modified game data and are meant only for use with a legally owned copy of the game.
