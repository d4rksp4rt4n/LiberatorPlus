# Launch the game through Steam with a given exe, wait, report Log.txt markers + crashes, close the game.
#   powershell -ExecutionPolicy Bypass -File VDMod\bisect\trial.ps1 -Exe <path> [-Wait 30]
param([string]$Exe, [int]$Wait = 30, [switch]$PressKeys, [int]$PressAfter = 8, [int]$SampleFps = 0)
$root = 'D:\SteamLibrary\steamapps\common\Valkyrie Drive\DeploymentRoot'
$game = "$root\VD_BHIKKHUNI.exe"
Get-Process VD_BHIKKHUNI -ErrorAction SilentlyContinue | Stop-Process -Force; Start-Sleep 2
$keep = "$env:TEMP\vd_exe_keep.exe"
Copy-Item $game $keep -Force
Copy-Item $Exe $game -Force
$t0 = Get-Date
Start-Process 'steam://rungameid/550080'
if ($PressKeys) {
    Add-Type -Namespace W -Name K -MemberDefinition @'
[DllImport("user32.dll")] public static extern void keybd_event(byte vk, byte scan, uint flags, System.UIntPtr extra);
[DllImport("user32.dll")] public static extern bool SetForegroundWindow(System.IntPtr h);
'@
    for ($s = 0; $s -lt $Wait; $s++) {
        Start-Sleep 1
        $gp = Get-Process VD_BHIKKHUNI -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($gp -and $s -ge $PressAfter -and $s % 2 -eq 0) {
            [void][W.K]::SetForegroundWindow($gp.MainWindowHandle)
            foreach ($vk in 0x0D, 0x5A) {      # Enter, Z (scan codes for DirectInput)
                $sc = @{0x0D = 0x1C; 0x5A = 0x2C}[$vk]
                [W.K]::keybd_event($vk, $sc, 0x8, [UIntPtr]::Zero); Start-Sleep -Milliseconds 80
                [W.K]::keybd_event($vk, $sc, 0xA, [UIntPtr]::Zero)
            }
        }
    }
} elseif ($SampleFps) {
    Start-Sleep $SampleFps
    python -I "$PSScriptRoot\fpsread.py" 6
    Start-Sleep ([math]::Max(1, $Wait - $SampleFps - 6))
} else { Start-Sleep $Wait }
$p = Get-Process VD_BHIKKHUNI -ErrorAction SilentlyContinue | Select-Object -First 1
$alive = [bool]$p
if ($p) {                       # close the window normally so the game flushes Log.txt
    [void]$p.CloseMainWindow()
    for ($i = 0; $i -lt 15 -and -not $p.HasExited; $i++) { Start-Sleep 1 }
    if (-not $p.HasExited) { 'window close ignored -> killing'; $p | Stop-Process -Force }
}
Start-Sleep 2
Copy-Item $keep $game -Force
"alive after $Wait s: $alive"
Get-WinEvent -FilterHashtable @{LogName='Application'; Id=1000; StartTime=$t0} -ErrorAction SilentlyContinue |
    ForEach-Object { if ($_.Message -match 'dulo com falha: ([^,]+),.*?Deslocamento da falha: (0x[0-9a-f]+)') { "CRASH in $($Matches[1]) at $($Matches[2])" } }
if ((Get-Item "$root\Log.txt").LastWriteTime -gt $t0) {
    Select-String -Path "$root\Log.txt" -Pattern 'LG_CHECK|TL_CHECK|DLC|Screen Change' | ForEach-Object { $_.Line }
} else { 'Log.txt not written' }
