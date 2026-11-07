@echo off
rem Uninstall the mod: put back the original game files saved in VDMod\backup and remove the DLL.
rem The exe itself is not touched (the DLL patches it only in memory); a Steam "Verify integrity"
rem afterwards also clears the 4 GB (Large Address Aware) flag and re-checks every game file.
set G=%~dp0..
copy /y "%~dp0backup\UI\advstill\*.mib" "%G%\DeploymentRoot\Resource\UI\advstill\" >nul
copy /y "%~dp0backup\UI_Eng_Dt\advstill\*.mib" "%G%\DeploymentRoot\Resource\UI_Eng_Dt\advstill\" >nul
if exist "%~dp0backup\Resource" xcopy /e /y /q "%~dp0backup\Resource" "%G%\DeploymentRoot\Resource\" >nul
for %%F in (MeShaderQueCache_WIN.bin MeShaderCache_WIN.bin MeShaderPack_WIN.bin MeigeUtilWinShaderPack.bin) do if exist "%~dp0backup\%%F" copy /y "%~dp0backup\%%F" "%G%\DeploymentRoot\" >nul
if exist "%~dp0backup\MeigeAppWin.cfg" copy /y "%~dp0backup\MeigeAppWin.cfg" "%G%\DeploymentRoot\" >nul
copy /y "%~dp0backup\Database\*.bin" "%G%\DeploymentRoot\Resource\Database\" >nul
for %%F in (dinput8.dll VDPatch.exe vdmod.ini vdmod.log) do if exist "%G%\DeploymentRoot\%%F" del "%G%\DeploymentRoot\%%F"
echo Mod removed: original textures, CGs, shader caches and settings restored, DLL deleted.
echo Run "Verify integrity of game files" in Steam to clear the 4 GB flag as well.
pause
