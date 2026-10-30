param(
    [string]$TaskName = 'IMAX Daily Refresh',
    [string]$Distro = 'Ubuntu',
    [string]$LinuxUser = 'mmm',
    [string]$ProjectPath = '/home/mmm/code/IMAX'
)
$ErrorActionPreference = 'Stop'
$identity = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$action = New-ScheduledTaskAction -Execute "$env:SystemRoot\System32\wsl.exe" -Argument "--distribution $Distro --user $LinuxUser --exec /bin/bash $ProjectPath/scripts/run_imax_scheduled.sh --if-due"
$daily = New-ScheduledTaskTrigger -Daily -At '03:15'
$logon = New-ScheduledTaskTrigger -AtLogOn -User $identity
$logon.Delay = 'PT1M'
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -WakeToRun -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -RunOnlyIfNetworkAvailable -MultipleInstances IgnoreNew -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 15) -ExecutionTimeLimit (New-TimeSpan -Hours 1)
$principal = New-ScheduledTaskPrincipal -UserId $identity -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger @($daily, $logon) -Settings $settings -Principal $principal -Description 'Publish IMAX daily at 03:15 local time. Recover missed runs at sign-in; retry failures every 15 minutes, up to 3 times. Requires the owning Windows user to be signed in.' -Force | Out-Null
Get-ScheduledTask -TaskName $TaskName | Select-Object TaskName, State, @{Name='User';Expression={$_.Principal.UserId}}, @{Name='LogonType';Expression={$_.Principal.LogonType}}
Get-ScheduledTaskInfo -TaskName $TaskName | Select-Object NextRunTime, LastRunTime, LastTaskResult
