<#
.SYNOPSIS
    Dev convenience: wipe the local DEM database and reseed everything from scratch.

.DESCRIPTION
    Thin wrapper around `python -m dem.db.reset_db`. Prefers the project's
    .venv if present, otherwise falls back to whatever `python` is on PATH.
    Respects $env:DEM_DATABASE_URL the same way the seed scripts do (defaults
    to the sqlite dev DB, ./dem_dev.db).

.PARAMETER Yes
    Skip the confirmation prompt.

.PARAMETER ForceNonSqlite
    Allow drop_all/create_all against a non-sqlite DEM_DATABASE_URL (see
    dem/db/reset_db.py's docstring for why this is guarded).

.EXAMPLE
    ./scripts/reset-db.ps1
    ./scripts/reset-db.ps1 -Yes
#>
param(
    [switch]$Yes,
    [switch]$ForceNonSqlite
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $repoRoot ".venv\Scripts\python.exe"
$python = if (Test-Path $venvPython) { $venvPython } else { "python" }

$scriptArgs = @()
if ($Yes) { $scriptArgs += "--yes" }
if ($ForceNonSqlite) { $scriptArgs += "--force-non-sqlite" }

Push-Location $repoRoot
try {
    & $python -m dem.db.reset_db @scriptArgs
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}
finally {
    Pop-Location
}
