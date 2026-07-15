[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$PlatformRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$ComposeFile = Join-Path $PlatformRoot 'deploy\docker-compose.yml'
$EnvFile = Join-Path $PlatformRoot '.env'

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw 'Install and start Docker Desktop first.' }
docker version | Out-Null
if (-not (Test-Path $EnvFile)) {
    Copy-Item -LiteralPath (Join-Path $PlatformRoot '.env.example') -Destination $EnvFile
    throw 'platform/.env was created. Set a local POSTGRES_PASSWORD, then run this script again.'
}

docker compose --env-file $EnvFile -f $ComposeFile up -d postgres redis
if ($LASTEXITCODE -ne 0) { throw 'Infrastructure startup failed' }
docker compose --env-file $EnvFile -f $ComposeFile run --rm api python -m alembic upgrade head
if ($LASTEXITCODE -ne 0) { throw 'Alembic migration failed' }
docker compose --env-file $EnvFile -f $ComposeFile up -d --build api publisher worker frontend
if ($LASTEXITCODE -ne 0) { throw 'Application startup failed' }

$Deadline = (Get-Date).AddMinutes(3)
do {
    try { $Health = Invoke-RestMethod 'http://127.0.0.1:8000/api/system/health'; break } catch { Start-Sleep -Seconds 2 }
} while ((Get-Date) -lt $Deadline)
if (-not $Health -or $Health.database -ne 'ok' -or $Health.redis -ne 'ok') { throw 'Health verification failed' }
Write-Host 'New-machine bootstrap complete.'
Write-Host 'Open http://127.0.0.1:5173'
