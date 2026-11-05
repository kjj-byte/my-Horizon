# Start the daily Horizon run at 06:00 instead of 07:00.
# Registered by admin as: task name Horizon-Daily-Trigger, daily at 06:00, run as
# the current user, command:
#   gh workflow run daily-summary.yml -R kjj-byte/my-Horizon --ref main
# Runs minimised: nothing is shown and the window closes when gh exits.
$ErrorActionPreference = 'Stop'
try {
    $task = Get-ScheduledTask -TaskName 'Horizon-Daily-Trigger'
    $trigger = @($task.Triggers)[0]
    $trigger.StartBoundary = '2026-11-05T06:00:00+08:00'
    Set-ScheduledTask -TaskName 'Horizon-Daily-Trigger' -Trigger $trigger | Out-Null
    Get-ScheduledTask -TaskName 'Horizon-Daily-Trigger' |
        Select-Object TaskName, State, @{n = 'Start'; e = { $_.Triggers[0].StartBoundary } } |
        Format-List
} catch {
    $_ | Out-String | Add-Content -Path "$PSScriptRoot\set-task-0600-error.log"
}