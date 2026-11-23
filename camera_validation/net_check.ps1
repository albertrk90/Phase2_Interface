<#
Read-only network preflight for the isolated OAK PoE test network.
Changes no adapter, firewall or routing settings.

    powershell -ExecutionPolicy Bypass -File .\net_check.ps1
    powershell -ExecutionPolicy Bypass -File .\net_check.ps1 -CameraIp 169.254.1.222,169.254.1.223
#>
param(
    [string[]]$CameraIp = @("169.254.1.222"),
    [string]$Adapter = "Ethernet 4"
)

$results = Join-Path $PSScriptRoot "results"
New-Item -ItemType Directory -Force $results | Out-Null
$log = Join-Path $results ("net_check_{0:yyyyMMdd_HHmmss}.txt" -f (Get-Date))
Start-Transcript -Path $log | Out-Null

try {
    "== Adapters that are Up =="
    Get-NetAdapter | Where-Object Status -eq "Up" |
        Format-Table Name, InterfaceDescription, LinkSpeed, MacAddress -AutoSize | Out-String

    "== Test adapter: $Adapter =="
    Get-NetAdapter -Name $Adapter -ErrorAction SilentlyContinue |
        Format-Table Name, Status, LinkSpeed, MediaConnectionState -AutoSize | Out-String
    Get-NetIPAddress -InterfaceAlias $Adapter -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Format-Table IPAddress, PrefixLength, PrefixOrigin -AutoSize | Out-String

    "== Non-link-local IPv4 addresses (should be empty on the isolated network) =="
    $other = Get-NetIPAddress -AddressFamily IPv4 |
        Where-Object { $_.IPAddress -notlike "169.254.*" -and $_.IPAddress -notlike "127.*" }
    if ($other) { $other | Format-Table InterfaceAlias, IPAddress -AutoSize | Out-String }
    else { "none" }

    foreach ($ip in $CameraIp) {
        "== Camera $ip =="
        $ping = Test-Connection -ComputerName $ip -Count 4 -ErrorAction SilentlyContinue
        if ($ping) {
            $ms = ($ping | Measure-Object ResponseTime -Average -Maximum)
            "ping: {0}/4 replies, avg {1:N1} ms, max {2} ms" -f $ping.Count, $ms.Average, $ms.Maximum
        } else { "ping: no replies" }
        # 11490/TCP is the DepthAI XLink port on RVC2 PoE devices.
        $tcp = Test-NetConnection -ComputerName $ip -Port 11490 -WarningAction SilentlyContinue
        "tcp 11490: {0}" -f $(if ($tcp.TcpTestSucceeded) { "open" } else { "no connection" })
    }
} finally {
    Stop-Transcript | Out-Null
    "Saved: $log"
}
