@echo off
rem Liberator+: sets the Large Address Aware flag in VD_BHIKKHUNI.exe next to this file, so the 32-bit
rem game can use 4 GB of memory instead of 2 GB (needed with the HD textures). It changes one bit in the
rem exe header and nothing else. Steam updates and "Verify integrity" remove it: run this again after them.
rem Close the game first.
powershell -NoProfile -ExecutionPolicy Bypass -Command "$p = Join-Path '%~dp0' 'VD_BHIKKHUNI.exe'; try { $s = [IO.File]::Open($p, 'Open', 'ReadWrite', 'None') } catch { Write-Host ('Cannot open ' + $p + ' - close the game and run this again.'); exit 1 }; $b = New-Object byte[] 1024; [void]$s.Read($b, 0, 1024); $pe = [BitConverter]::ToInt32($b, 60); if ($pe -lt 0 -or $pe -gt 1000 -or $b[$pe] -ne 0x50 -or $b[$pe + 1] -ne 0x45 -or [BitConverter]::ToUInt16($b, $pe + 4) -ne 0x14c) { $s.Close(); Write-Host 'VD_BHIKKHUNI.exe is not the 32-bit game exe - nothing changed.'; exit 1 }; $c = $pe + 22; if ($b[$c] -band 0x20) { Write-Host 'The 4 GB flag was already set in VD_BHIKKHUNI.exe.' } else { $s.Position = $c; $s.WriteByte([byte]($b[$c] -bor 0x20)); Write-Host 'Done: the 4 GB flag is now set in VD_BHIKKHUNI.exe.' }; $s.Close()"
pause
