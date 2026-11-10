@echo off
rem Builds dinput8.dll and VDPatch.exe (32-bit) with the MSVC Build Tools and copies them to DeploymentRoot.
rem zoom.h comes from gen_zoom.py (re-run it only after changing ../gallery_zoom.py).
call "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars32.bat" >nul || exit /b 1
cd /d "%~dp0"
rc /nologo /fo dinput8.res version.rc || exit /b 1
rc /nologo /d PATCHER /fo VDPatch.res version.rc || exit /b 1
cl /nologo /O2 /W3 /GS- /LD /MT vdmod.c dinput8.res /link /DEF:vdmod.def /OUT:dinput8.dll kernel32.lib user32.lib || exit /b 1
rem the embedded asInvoker manifest matters: without it Windows' installer detection ("Patch" in the name)
rem demands admin rights and dinput8.dll's CreateProcess fails with error 740
cl /nologo /O2 /W3 /MT VDPatch.c VDPatch.res /link /SUBSYSTEM:WINDOWS /MANIFEST:EMBED /MANIFESTUAC:"level='asInvoker' uiAccess='false'" kernel32.lib user32.lib shell32.lib || exit /b 1
del *.obj *.res vdmod.lib vdmod.exp dinput8.lib dinput8.exp 2>nul
copy /y dinput8.dll "%~dp0..\..\DeploymentRoot\" >nul && copy /y VDPatch.exe "%~dp0..\..\DeploymentRoot\" >nul && echo Copied to DeploymentRoot.
