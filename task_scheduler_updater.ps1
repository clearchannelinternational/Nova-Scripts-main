$taskName = "LEDMonitoring"
$taskPath = "\"
$time = (Get-Date).AddMinutes(15)
$trigger = New-ScheduledTaskTrigger -At $time -Once
$action = New-ScheduledTaskAction -Execute "python.exe" -Argument "C:\LEDMonitoring\main_monitor.py"
$principal = New-ScheduledTaskPrincipal -UserId "Borough-Control-PC" -LogonType Interactive -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable

Register-ScheduledTask -TaskName $taskName -TaskPath $taskPath -Trigger $trigger -Action $action -Principal $principal -Settings $settings -Force
