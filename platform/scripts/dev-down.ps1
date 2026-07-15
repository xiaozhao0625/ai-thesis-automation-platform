[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$PlatformRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$ComposeFile = Join-Path $PlatformRoot 'deploy\docker-compose.yml'
$EnvFile = Join-Path $PlatformRoot '.env'

docker compose --env-file $EnvFile -f $ComposeFile down
if ($LASTEXITCODE -ne 0) { throw 'docker compose down failed' }
Write-Host 'Services stopped. PostgreSQL volume and Artifact Store were preserved.'
