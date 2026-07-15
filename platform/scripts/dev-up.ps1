[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$PlatformRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$ComposeFile = Join-Path $PlatformRoot 'deploy\docker-compose.yml'
$EnvFile = Join-Path $PlatformRoot '.env'

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw 'Docker Desktop / docker CLI is required.'
}
if (-not (Test-Path $EnvFile)) {
    Copy-Item -LiteralPath (Join-Path $PlatformRoot '.env.example') -Destination $EnvFile
    Write-Warning 'Created platform/.env from .env.example. Review POSTGRES_PASSWORD before shared use.'
}

docker compose --env-file $EnvFile -f $ComposeFile up -d --build
if ($LASTEXITCODE -ne 0) { throw 'docker compose up failed' }
docker compose --env-file $EnvFile -f $ComposeFile ps
Write-Host 'Frontend: http://127.0.0.1:5173'
Write-Host 'API:      http://127.0.0.1:8000'
Write-Host 'Health:   http://127.0.0.1:8000/api/system/health'
