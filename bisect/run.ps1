# Launch each exe variant through Steam; report whether it survives $wait seconds.
param([string[]]$Variants, [int]$Wait = 25)
$game = 'D:\SteamLibrary\steamapps\common\Valkyrie Drive\DeploymentRoot\VD_BHIKKHUNI.exe'
foreach ($v in $Variants) {
    Get-Process VD_BHIKKHUNI -ErrorAction SilentlyContinue | Stop-Process -Force
    Start-Sleep 3
    Copy-Item "$PSScriptRoot\$v.exe" $game -Force
    $t0 = Get-Date
    Start-Process 'steam://rungameid/550080'
    $alive = $false
    for ($i = 0; $i -lt $Wait; $i++) {
        Start-Sleep 1
        if (Get-Process VD_BHIKKHUNI -ErrorAction SilentlyContinue) { $alive = $true }
    }
    $still = [bool](Get-Process VD_BHIKKHUNI -ErrorAction SilentlyContinue)
    $crash = Get-WinEvent -FilterHashtable @{LogName='Application'; Id=1000; StartTime=$t0} -ErrorAction SilentlyContinue |
        ForEach-Object { if ($_.Message -match 'Deslocamento da falha: (0x[0-9a-f]+)|Fault offset: (0x[0-9a-f]+)') { $Matches[1] + $Matches[2] } }
    "{0,-16} started={1} running_after_{2}s={3} crash_offsets={4}" -f $v, $alive, $Wait, $still, ($crash -join ',')
}
Get-Process VD_BHIKKHUNI -ErrorAction SilentlyContinue | Stop-Process -Force
