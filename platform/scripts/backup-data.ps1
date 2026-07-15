[CmdletBinding()]
param(
    [string]$OutputDirectory
)

$ErrorActionPreference = 'Stop'
$PlatformRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$RepositoryRoot = (Resolve-Path (Join-Path $PlatformRoot '..')).Path
$ComposeFile = Join-Path $PlatformRoot 'deploy\docker-compose.yml'
$EnvFile = Join-Path $PlatformRoot '.env'
if (-not $OutputDirectory) { $OutputDirectory = Join-Path $PlatformRoot ("handoff-bundles\" + (Get-Date -Format 'yyyyMMdd-HHmmss')) }
$Bundle = [System.IO.Path]::GetFullPath($OutputDirectory)
New-Item -ItemType Directory -Force -Path $Bundle | Out-Null
if (-not (Test-Path $EnvFile)) { throw 'platform/.env is required; copy .env.example and configure it first.' }

$Env = @{}
Get-Content -LiteralPath $EnvFile | Where-Object { $_ -match '^[^#][^=]*=' } | ForEach-Object { $Key,$Value = $_ -split '=',2; $Env[$Key]=$Value }
$Db = $Env['POSTGRES_DB']; $User = $Env['POSTGRES_USER']; $DatabaseUrl = $Env['DATABASE_URL']; $ArtifactContainerRoot = $Env['ARTIFACT_STORE_ROOT']
if (-not $Db -or -not $User -or -not $DatabaseUrl -or -not $ArtifactContainerRoot) { throw 'POSTGRES_DB, POSTGRES_USER, DATABASE_URL and ARTIFACT_STORE_ROOT are required in platform/.env' }

docker compose --env-file $EnvFile -f $ComposeFile stop api publisher worker frontend | Out-Null
try {
    $SnapshotJson = docker compose --env-file $EnvFile -f $ComposeFile run --rm --no-deps api python -m app.maintenance.snapshot --database-url $DatabaseUrl --artifact-root $ArtifactContainerRoot
    if ($LASTEXITCODE -ne 0) { throw 'collecting handoff snapshot failed' }
    $Snapshot = ([string]::Join("`n", $SnapshotJson) | ConvertFrom-Json)
    docker compose --env-file $EnvFile -f $ComposeFile exec -T postgres pg_dump -U $User -d $Db -Fc --no-owner --no-acl -f /tmp/p1-1-database.dump
    if ($LASTEXITCODE -ne 0) { throw 'pg_dump failed' }
    docker compose --env-file $EnvFile -f $ComposeFile cp postgres:/tmp/p1-1-database.dump (Join-Path $Bundle 'database.dump')
    if ($LASTEXITCODE -ne 0) { throw 'copying database dump failed' }
    $ArtifactRoot = Join-Path $PlatformRoot 'artifact_store'
    if (-not (Test-Path $ArtifactRoot)) { New-Item -ItemType Directory -Path $ArtifactRoot | Out-Null }
    $ArtifactArchive = Join-Path $Bundle 'artifact-store.zip'
    if (Test-Path $ArtifactArchive) { Remove-Item -LiteralPath $ArtifactArchive -Force }
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    [System.IO.Compression.ZipFile]::CreateFromDirectory($ArtifactRoot, $ArtifactArchive, [System.IO.Compression.CompressionLevel]::Optimal, $false)
    Copy-Item -LiteralPath (Join-Path $PlatformRoot 'docs\P1-1_DATA_PORTABILITY.md') -Destination (Join-Path $Bundle 'RESTORE.md')
    $Files = @{}
    foreach ($Name in @('database.dump','artifact-store.zip','RESTORE.md')) { $Files[$Name]=(Get-FileHash -LiteralPath (Join-Path $Bundle $Name) -Algorithm SHA256).Hash.ToLowerInvariant() }
    $Manifest = [ordered]@{ format_version='p1-1-handoff-v1'; created_at=(Get-Date).ToUniversalTime().ToString('o'); git_commit=([string](git -C $RepositoryRoot rev-parse HEAD)).Trim(); alembic_revision=$Snapshot.alembic_revision; postgres_image='postgres:17.10-alpine'; redis_image='redis:7.4.9-alpine'; database=$Db; table_counts=$Snapshot.table_counts; artifact_store=$Snapshot.artifact_store; files=$Files }
    $Manifest | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $Bundle 'backup-manifest.json') -Encoding utf8
} finally {
    docker compose --env-file $EnvFile -f $ComposeFile start api publisher worker frontend | Out-Null
}
& (Join-Path $PSScriptRoot 'verify-handoff.ps1') -BundleDirectory $Bundle
Write-Host "Backup bundle: $Bundle"
