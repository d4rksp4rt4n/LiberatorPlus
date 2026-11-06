@echo off
rem Drag folders of texture PNGs (named as in VDMod\extract) onto this file to put them into the game.
python -I "%~dp0repack.py" %*
pause
