# SPDX-License-Identifier: GPL-3.0-or-later
# Runs every check of this repository: format, lints, build and tests.
#
#   tools\check.ps1                      the quick checks
#   tools\check.ps1 -Full                also the ones that need 3ds Max, the network or a long time
#   tools\check.ps1 -Skip "ruff check"   leaves out the check named, and says so; several names are
#                                        separated by commas. A name that no check has is an error.
#
# Where Windows does not let scripts run:  powershell -ExecutionPolicy Bypass -File tools\check.ps1
#
# The checks are listed in tools\repo.toml and run by tools\repo.py. This script only finds a Python
# from 3.11 on, starts it and passes its exit code on. It is the same in every OPEN3D repository.
param([switch]$Full, [string[]]$Skip = @())

$ErrorActionPreference = 'Continue'
$tool = Join-Path $PSScriptRoot 'repo.py'
$isNewEnough = 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)'

# True when the command (a program and its first arguments) starts a Python from 3.11 on.
function Test-Python([string[]]$Command) {
    $program = $Command[0]
    $first = @($Command | Select-Object -Skip 1)
    try {
        & $program @first -c $isNewEnough 2>$null | Out-Null
        return ($LASTEXITCODE -eq 0)
    } catch {
        return $false
    }
}

# The py launcher, then python on PATH, then the folders where the installer of python.org puts them
# when PATH does not have them.
$candidates = @()
if (Get-Command py -ErrorAction SilentlyContinue) { $candidates += , @('py', '-3') }
if (Get-Command python -ErrorAction SilentlyContinue) { $candidates += , @('python') }
$places = @()
if ($env:LOCALAPPDATA) {
    $candidates += , @((Join-Path $env:LOCALAPPDATA 'Programs\Python\Launcher\py.exe'), '-3')
    $places += Join-Path $env:LOCALAPPDATA 'Programs\Python\Python3*\python.exe'
}
if ($env:ProgramFiles) { $places += Join-Path $env:ProgramFiles 'Python3*\python.exe' }
foreach ($place in $places) {
    $installed = @(Get-Item -Path $place -ErrorAction SilentlyContinue | Sort-Object -Property FullName -Descending)
    foreach ($found in $installed) { $candidates += , @($found.FullName) }
}

$python = $null
foreach ($candidate in $candidates) {
    if (Test-Python $candidate) {
        $python = $candidate
        break
    }
}
if (-not $python) {
    Write-Host 'check.ps1: no Python 3.11 or newer was found.'
    Write-Host 'Install Python from https://www.python.org/downloads/ (the default options are fine),'
    Write-Host 'open a new terminal and run tools\check.ps1 again.'
    exit 2
}

$program = $python[0]
$first = @($python | Select-Object -Skip 1)
$arguments = @('check')
if ($Full) { $arguments += '--full' }
foreach ($name in @($Skip | ForEach-Object { $_ -split ',' })) {
    if ($name.Trim()) { $arguments += @('--skip', $name.Trim()) }
}
& $program @first -I $tool @arguments
exit $LASTEXITCODE
