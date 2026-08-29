# Run the offline test suites on Windows.
#
# Why this exists: the project venv is macOS-built (.venv/bin/python, darwin
# .so files), so it cannot run here even though the repo syncs to this machine
# via OneDrive. The offline suites need no third-party packages at all —
# call_quality and speech_dynamics are stdlib-only at import time — so a bare
# interpreter is enough and no Windows venv is required.
#
# Two Windows-specific traps this handles:
#   1. `python` on PATH is usually the Microsoft Store stub, which exits without
#      running anything. Real installs live under %LOCALAPPDATA%\Programs\Python.
#   2. The console defaults to cp1252 and the scripts print emoji, so output
#      dies on UnicodeEncodeError. PYTHONUTF8=1 fixes it.
#
# Usage:  powershell -ExecutionPolicy Bypass -File scripts\run_tests.ps1

$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot

function Find-Python {
    # Explicit installs first — these are never the Store stub.
    $candidates = @()
    $candidates += Get-ChildItem "$env:LOCALAPPDATA\Programs\Python\Python*\python.exe" -ErrorAction SilentlyContinue
    $candidates += Get-ChildItem "C:\Python*\python.exe" -ErrorAction SilentlyContinue
    $candidates += Get-ChildItem "$env:ProgramFiles\Python*\python.exe" -ErrorAction SilentlyContinue
    foreach ($c in $candidates) {
        if (Test-Path $c.FullName) { return $c.FullName }
    }
    # The py launcher, if it is installed.
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) { return $py.Source }
    # Whatever is on PATH, unless it is the Store stub.
    $p = Get-Command python -ErrorAction SilentlyContinue
    if ($p -and $p.Source -notmatch 'WindowsApps') { return $p.Source }
    return $null
}

$python = Find-Python
if (-not $python) {
    Write-Output "No usable Python found."
    Write-Output "  'python' on PATH is the Microsoft Store stub, which runs nothing."
    Write-Output "  Install Python 3 from python.org, then re-run this script."
    exit 1
}

$env:PYTHONUTF8 = '1'   # scripts print emoji; the console is cp1252 by default
Write-Output "Using $python"
& $python --version
Write-Output ''

$suites = @('scripts\test_call_quality.py', 'scripts\test_speech_dynamics.py')
$failed = @()
foreach ($suite in $suites) {
    Write-Output "=== $suite ==="
    & $python (Join-Path $repo $suite)
    if ($LASTEXITCODE -ne 0) { $failed += $suite }
    Write-Output ''
}

if ($failed.Count -gt 0) {
    Write-Output "FAILED: $($failed -join ', ')"
    exit 1
}
Write-Output "All offline suites passed."
