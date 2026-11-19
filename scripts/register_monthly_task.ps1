[CmdletBinding()]
param(
    [ValidateRange(1, 31)]
    [int]$Day = 25,
    [ValidatePattern('^([01][0-9]|2[0-3]):[0-5][0-9]$')]
    [string]$Time = '02:00',
    [string]$TaskName = 'Blogger Crawler Monthly',
    [switch]$Preview
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$LauncherPath = Join-Path $PSScriptRoot "run_monthly_crawl.ps1"
$TimeValue = [datetime]::ParseExact(
    $Time,
    "HH:mm",
    [Globalization.CultureInfo]::InvariantCulture
)
$UserId = "$env:USERDOMAIN\$env:USERNAME"
$ActionArgs = "-NoProfile -ExecutionPolicy Bypass -File `"$LauncherPath`""
$DayMask = [uint32]1 -shl ($Day - 1)
$Now = Get-Date
$SearchMonth = Get-Date -Year $Now.Year -Month $Now.Month -Day 1 `
    -Hour $TimeValue.Hour -Minute $TimeValue.Minute -Second 0
while ($true) {
    $DaysInMonth = [DateTime]::DaysInMonth($SearchMonth.Year, $SearchMonth.Month)
    if ($Day -le $DaysInMonth) {
        $Candidate = Get-Date -Year $SearchMonth.Year -Month $SearchMonth.Month -Day $Day `
            -Hour $TimeValue.Hour -Minute $TimeValue.Minute -Second 0
        if ($Candidate -gt $Now) {
            $StartBoundary = $Candidate
            break
        }
    }
    $SearchMonth = $SearchMonth.AddMonths(1)
}

if ($Preview) {
    Write-Output "TaskName: $TaskName"
    Write-Output "User: $UserId"
    Write-Output "ProjectRoot: $ProjectRoot"
    Write-Output "Launcher: $LauncherPath"
    Write-Output "Action: PowerShell.exe $ActionArgs"
    Write-Output "Schedule: day $Day at $Time"
    Write-Output "Day mask: $DayMask"
    Write-Output "Next run boundary: $($StartBoundary.ToString('s'))"
    Write-Output "Preview only; no task was registered."
    exit 0
}

$ScheduleService = New-Object -ComObject "Schedule.Service"
$ScheduleService.Connect()
$TaskFolder = $ScheduleService.GetFolder("\")
$TaskDefinition = $ScheduleService.NewTask(0)
$TaskDefinition.RegistrationInfo.Description = "Monthly Pugongying blogger crawl and report"
$TaskDefinition.Principal.UserId = $UserId
$TaskDefinition.Principal.LogonType = 3
$TaskDefinition.Principal.RunLevel = 0

$Trigger = $TaskDefinition.Triggers.Create(4)
$Trigger.DaysOfMonth = $DayMask
$Trigger.MonthsOfYear = 4095
$Trigger.StartBoundary = $StartBoundary.ToString("s")

$Action = $TaskDefinition.Actions.Create(0)
$Action.Path = "PowerShell.exe"
$Action.Arguments = $ActionArgs
$Action.WorkingDirectory = $ProjectRoot
$TaskDefinition.Settings.StartWhenAvailable = $true
$TaskDefinition.Settings.ExecutionTimeLimit = "PT6H"

$TaskFolder.RegisterTaskDefinition(
    $TaskName,
    $TaskDefinition,
    6,
    $UserId,
    $null,
    3,
    $null
) | Out-Null

Write-Output "Registered scheduled task '$TaskName' for day $Day at $Time."
