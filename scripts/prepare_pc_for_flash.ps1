$ErrorActionPreference = "Stop"

$pythonExe = "C:\Python312\python.exe"
$ruleName = "HH72VM-OpenWrt-Python-UDP"

Write-Host "[1/2] Configuring Windows Firewall inbound UDP rule for $pythonExe..."
netsh advfirewall firewall delete rule name="$ruleName" | Out-Null
netsh advfirewall firewall add rule name="$ruleName" dir=in action=allow program="$pythonExe" protocol=UDP profile=any enable=yes

Write-Host "[2/2] Adding secondary IPv4 192.168.1.50/24 to Ethernet adapter 'Gigabit'..."
$existing = Get-NetIPAddress -InterfaceAlias "Gigabit" -IPAddress "192.168.1.50" -ErrorAction SilentlyContinue
if (-not $existing) {
    netsh interface ipv4 add address name="Gigabit" addr=192.168.1.50 mask=255.255.255.0
} else {
    Write-Host "192.168.1.50/24 is already configured on 'Gigabit'."
}

Write-Host "DONE. PC is ready to flash OpenWrt onto HH72VM (bootloader 192.168.1.6)."
