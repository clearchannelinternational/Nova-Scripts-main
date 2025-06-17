$taskName = "LEDMonitoring"
$taskPath = "\"
$LoggedOnUser = (query user | Select-Object  -Last 1 ).ToString().Split(' ')[0].Remove(0,1)
$User = $env:COMPUTERNAME + "\" + $LoggedOnUser
$time = (Get-Date).AddMinutes(15)
$trigger = New-ScheduledTaskTrigger -At $time -Once
$action = New-ScheduledTaskAction -Execute "python.exe" -Argument "C:\LEDMonitoring\main_monitor.py"
$principal = New-ScheduledTaskPrincipal -UserId "$User" -LogonType Interactive -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable

Register-ScheduledTask -TaskName $taskName -TaskPath $taskPath -Trigger $trigger -Action $action -Principal $principal -Settings $settings -Force
