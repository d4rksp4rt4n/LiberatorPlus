@echo off
rem Builds dinput8.dll (32-bit) with the MSVC Build Tools and copies it and Set4GB.bat to DeploymentRoot.
rem zoom.h comes from gen_zoom.py (re-run it only after changing ../gallery_zoom.py).
call "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars32.bat" >nul || exit /b 1
cd /d "%~dp0"
rc /nologo /fo dinput8.res version.rc || exit /b 1
cl /nologo /O2 /W3 /GS- /LD /MT vdmod.c dinput8.res /link /DEF:vdmod.def /OUT:dinput8.dll kernel32.lib user32.lib || exit /b 1
del *.obj *.res vdmod.lib vdmod.exp dinput8.lib dinput8.exp 2>nul
copy /y dinput8.dll "%~dp0..\..\DeploymentRoot\" >nul && copy /y Set4GB.bat "%~dp0..\..\DeploymentRoot\" >nul && echo Copied to DeploymentRoot.
