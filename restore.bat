@echo off
rem Put back the original CGs and re-enable 3dmigoto.
set G=%~dp0..
copy /y "%~dp0backup\UI\advstill\*.mib" "%G%\DeploymentRoot\Resource\UI\advstill\" >nul
copy /y "%~dp0backup\UI_Eng_Dt\advstill\*.mib" "%G%\DeploymentRoot\Resource\UI_Eng_Dt\advstill\" >nul
if exist "%~dp0backup\Resource" xcopy /e /y /q "%~dp0backup\Resource" "%G%\DeploymentRoot\Resource\" >nul
for %%F in (MeShaderQueCache_WIN.bin MeShaderCache_WIN.bin MeShaderPack_WIN.bin MeigeUtilWinShaderPack.bin) do if exist "%~dp0backup\%%F" copy /y "%~dp0backup\%%F" "%G%\DeploymentRoot\" >nul
if exist "%~dp0backup\MeigeAppWin.cfg" copy /y "%~dp0backup\MeigeAppWin.cfg" "%G%\DeploymentRoot\" >nul
copy /y "%~dp0backup\VD_BHIKKHUNI.exe" "%G%\DeploymentRoot\" >nul
copy /y "%~dp0backup\Database\*.bin" "%G%\DeploymentRoot\Resource\Database\" >nul
for %%F in (dinput8.dll VDPatch.exe vdmod.log) do if exist "%G%\DeploymentRoot\%%F" del "%G%\DeploymentRoot\%%F"
move /y "%~dp0_3dmigoto_off\*" "%G%\DeploymentRoot\" >nul
echo Restored original CGs and 3dmigoto.
pause
