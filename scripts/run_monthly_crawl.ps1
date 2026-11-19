[CmdletBinding()]
param(
    [string]$ConfigPath = "config.yaml",
    [string]$PythonPath = ""
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $ProjectRoot

$ConfigFile = (Resolve-Path $ConfigPath -ErrorAction Stop).Path
$SessionFile = Join-Path $ProjectRoot ".session\session.json"
if ([string]::IsNullOrWhiteSpace($env:MYSQL_PASSWORD)) {
    Write-Error "MYSQL_PASSWORD is not available for the scheduled task user."
    exit 2
}
if (-not (Test-Path -LiteralPath $SessionFile)) {
    Write-Error "Saved Pugongying session is missing: $SessionFile"
    exit 2
}

if ([string]::IsNullOrWhiteSpace($PythonPath)) {
    $VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
    if (Test-Path -LiteralPath $VenvPython) {
        $PythonPath = $VenvPython
    } else {
        $PythonCommand = Get-Command python.exe -ErrorAction Stop
        $PythonPath = $PythonCommand.Source
    }
}

$env:PYTHONPATH = Join-Path $ProjectRoot "src"
$MainPath = Join-Path $ProjectRoot "src\main.py"

function Invoke-Crawler {
    param([string[]]$CrawlerArgs)

    & $PythonPath $MainPath "--config" $ConfigFile @CrawlerArgs
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}

Invoke-Crawler @()
Invoke-Crawler @("--report")
exit 0
