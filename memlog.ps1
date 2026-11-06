# Logs Valkyrie Drive memory every 5 s while it runs (waits for the game to start).
#   powershell -ExecutionPolicy Bypass -File VDMod\memlog.ps1
# virtual_mb = 32-bit address space in use (crashes are likely near 4096 with LAA).
param([string]$Out = "$PSScriptRoot\memlog.csv", [int]$WaitMinutes = 240)
$deadline = (Get-Date).AddMinutes($WaitMinutes)
while (-not ($p = Get-Process VD_BHIKKHUNI -ErrorAction SilentlyContinue | Select-Object -First 1)) {
    if ((Get-Date) -gt $deadline) { return }; Start-Sleep 2
}
"time,virtual_mb,private_mb,workingset_mb,gpu_dedicated_mb,gpu_shared_mb" | Set-Content $Out
while (-not $p.HasExited) {
    $p.Refresh()
    $gd = $gs = ''
    try {
        $c = (Get-Counter "\GPU Process Memory(pid_$($p.Id)*)\Dedicated Usage", "\GPU Process Memory(pid_$($p.Id)*)\Shared Usage" -ErrorAction Stop).CounterSamples
        $gd = [math]::Round((($c | Where-Object Path -match 'dedicated' | Measure-Object CookedValue -Sum).Sum) / 1MB)
        $gs = [math]::Round((($c | Where-Object Path -match 'shared' | Measure-Object CookedValue -Sum).Sum) / 1MB)
    } catch {}
    '{0:HH:mm:ss},{1},{2},{3},{4},{5}' -f (Get-Date), [math]::Round($p.VirtualMemorySize64 / 1MB),
        [math]::Round($p.PrivateMemorySize64 / 1MB), [math]::Round($p.WorkingSet64 / 1MB), $gd, $gs | Add-Content $Out
    Start-Sleep 5
}
"exited,{0:HH:mm:ss},exitcode={1}" -f (Get-Date), $p.ExitCode | Add-Content $Out
