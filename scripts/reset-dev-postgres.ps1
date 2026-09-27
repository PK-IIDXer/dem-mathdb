param(
    [string]$DatabaseUrl = "postgresql+psycopg://dem_dev@localhost:5432/dem_dev",
    [switch]$Yes
)

$ErrorActionPreference = "Stop"
$parsed = [System.Uri]$DatabaseUrl
$databaseName = $parsed.AbsolutePath.Trim("/")
if ($parsed.Host -notin @("localhost", "127.0.0.1")) {
    throw "Refusing to reset a non-local PostgreSQL host: $($parsed.Host)"
}
if ($databaseName -ne "dem_dev") {
    throw "Refusing to reset a database other than dem_dev: $databaseName"
}
if (-not $Yes) {
    throw "No changes made. Pass -Yes to drop and recreate the dem_dev database."
}

$repository = Split-Path -Parent $PSScriptRoot
$python = Join-Path $repository ".venv\Scripts\python.exe"
$psql = "C:\Program Files\PostgreSQL\18\bin\psql.exe"
if (-not (Test-Path -LiteralPath $python)) {
    throw "Repository virtual-environment Python was not found: $python"
}
if (-not (Test-Path -LiteralPath $psql)) {
    throw "PostgreSQL psql was not found: $psql"
}

$user = $parsed.UserInfo.Split(":", 2)[0]
$previousDatabaseUrl = $env:DEM_DATABASE_URL
$previousLocation = Get-Location
$stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
try {
    Set-Location -LiteralPath $repository
    & $psql -X -w -v ON_ERROR_STOP=1 -U $user -h $parsed.Host -p $parsed.Port -d postgres -c 'DROP DATABASE IF EXISTS "dem_dev" WITH (FORCE);'
    if ($LASTEXITCODE -ne 0) {
        throw "DROP DATABASE failed with exit code $LASTEXITCODE"
    }
    & $psql -X -w -v ON_ERROR_STOP=1 -U $user -h $parsed.Host -p $parsed.Port -d postgres -c 'CREATE DATABASE "dem_dev";'
    if ($LASTEXITCODE -ne 0) {
        throw "CREATE DATABASE failed with exit code $LASTEXITCODE"
    }

    $env:DEM_DATABASE_URL = $DatabaseUrl
    & $python -m alembic upgrade head
    if ($LASTEXITCODE -ne 0) {
        throw "alembic upgrade head failed with exit code $LASTEXITCODE"
    }
    & $python -m dem.db.seeds
    if ($LASTEXITCODE -ne 0) {
        throw "seed_all failed with exit code $LASTEXITCODE"
    }
}
finally {
    $stopwatch.Stop()
    if ($null -eq $previousDatabaseUrl) {
        Remove-Item Env:DEM_DATABASE_URL -ErrorAction SilentlyContinue
    }
    else {
        $env:DEM_DATABASE_URL = $previousDatabaseUrl
    }
    Set-Location -LiteralPath $previousLocation
}

Write-Output ("TOTAL_SECONDS={0:F3}" -f $stopwatch.Elapsed.TotalSeconds)
