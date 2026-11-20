# Liberator+ 1.0.1

Fixes and options for **Valkyrie Drive -Bhikkhuni-** on PC (Steam): higher frame rates, sharper textures, rendering bug fixes, 4K output and quality-of-life tweaks. Optional packs add HD CGs, mipmapped stage textures and a 4K opening movie.

Author: DarkSpartan

## Requirements

- Valkyrie Drive -Bhikkhuni- on Steam, public branch (v1.05) or beta branch (v1.06).
- Windows 10 or 11.

## Install

1. Copy `dinput8.dll`, `vdmod.ini` and `Set4GB.bat` into the game's `DeploymentRoot` folder, next to `VD_BHIKKHUNI.exe`.
2. Optional packs: copy each pack's `DeploymentRoot` folder over the game's.
3. Double-click `Set4GB.bat`. It sets the 4 GB memory flag in `VD_BHIKKHUNI.exe`, so the 32-bit game can use 4 GB instead of 2 GB (needed with the HD packs). It changes one bit in the exe header, and you can open the file to read exactly what it does. Run it again after any Steam update or "Verify integrity"; the mod reminds you at game start when the flag is missing.
4. Start the game from Steam.

Always start the game from Steam. Starting `VD_BHIKKHUNI.exe` directly crashes a few seconds in, with or without the mod.

### Steam Deck and Linux (Proton)

Not tested yet; reports welcome. Proton only loads `dinput8.dll` when told to, and `Set4GB.bat` does not run there, so instead:

1. Copy `dinput8.dll` and `vdmod.ini` into `DeploymentRoot` as above (skip `Set4GB.bat`).
2. In Steam, right-click the game > **Properties** > **Launch Options**, and enter:
   `WINEDLLOVERRIDES="dinput8=n,b" PROTON_FORCE_LARGE_ADDRESS_AWARE=1 %command%`
   The first part loads the mod, the second gives the game 4 GB of memory.
3. In `vdmod.ini`, set `LargeAddressAware=0`, so the mod doesn't show the 4 GB reminder at every start.

## What it does

All fixes are switched in `vdmod.ini`: close the game, edit, start the game again. `0` turns a fix off and gives the original behaviour. Each option is explained in the file itself. After every start, `vdmod.log` lists each fix as `on`, `off` or `SKIPPED`.

| Area | Options |
| --- | --- |
| Frame rate | `FrameRate` (60 to 240), `PreciseLimiter`, `ForceVSyncOff`, `PhysicsRate` (hair and bust physics behave as at 30 fps) |
| Graphics | `MipFix` (no distant shimmer), `Anisotropy`, `MSAAFix` (no white flashes on thin edges), `BlackWallFix` (no black patches on walls), `ShadowResolution`, `MaxResolution` (fullscreen up to 4K with DSR/VSR; never more than the display supports) |
| Gallery | `GalleryHDFit` (HD CGs at screen size), `GalleryZoom` (fit to screen, zoom to 1:1, full panning) |
| Boot and menus | `SkipIntro`, `FastDlcCheck`, `SkipRoomRanking` (no "Server Connect" box after the Dressing Room) |
| Memory | `LargeAddressAware` (warns at game start when the 4 GB flag is missing, for example after a Steam update) |
| Always on | Crash guards: Screen Size menu after a resolution change, and a rare crash in the game's texture loading |

The game exe on disk is never changed, except for the 4 GB memory flag. Every fix checks the game code before patching it; on an unknown game version that fix is skipped and the rest still work.

## Optional packs

| Pack | Contents |
| --- | --- |
| `CGPack` | Gallery and story CGs at 4x, title menu at 2x, Koharu's Vault > Voice portrait fixed. Needs `GalleryHDFit=1`. |
| `MipFixPack` | Stage and background textures with mipmaps. Used only with `MipFix=1`. |
| `OPVideo4K` | Opening movie at 3840x2160 with the original audio. |

## Uninstall

Delete `dinput8.dll`, `vdmod.ini`, `Set4GB.bat` and `vdmod.log` from `DeploymentRoot`, then run **Verify integrity of game files** in Steam. That also puts back the original textures, CGs and movie, and clears the 4 GB flag.

## AI use

This mod was made with help from an AI coding assistant (Claude Code).

