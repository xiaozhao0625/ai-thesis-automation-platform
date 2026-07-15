[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$BundleDirectory,
    [string]$TargetDatabase = 'thesis_platform_restored'
)

$ErrorActionPreference = 'Stop'
$PlatformRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$ComposeFile = Join-Path $PlatformRoot 'deploy\docker-compose.yml'
$EnvFile = Join-Path $PlatformRoot '.env'
$Bundle = (Resolve-Path $BundleDirectory).Path
& (Join-Path $PSScriptRoot 'verify-handoff.ps1') -BundleDirectory $Bundle
if ($TargetDatabase -notmatch '^[A-Za-z_][A-Za-z0-9_]*$') { throw 'TargetDatabase must be a safe PostgreSQL identifier.' }

$Env = @{}
Get-Content -LiteralPath $EnvFile | Where-Object { $_ -match '^[^#][^=]*=' } | ForEach-Object { $Key,$Value = $_ -split '=',2; $Env[$Key]=$Value }
$User = $Env['POSTGRES_USER']; $Password = $Env['POSTGRES_PASSWORD']
if (-not $User -or -not $Password) { throw 'POSTGRES_USER and POSTGRES_PASSWORD are required in platform/.env' }
$Manifest = Get-Content -LiteralPath (Join-Path $Bundle 'backup-manifest.json') -Raw | ConvertFrom-Json
docker compose --env-file $EnvFile -f $ComposeFile up -d postgres redis
$Exists = docker compose --env-file $EnvFile -f $ComposeFile exec -T postgres psql -U $User -d postgres -Atc "select 1 from pg_database where datname='$TargetDatabase'"
if (([string]$Exists).Trim() -eq '1') { throw "Target database already exists; refusing to overwrite: $TargetDatabase" }

$ArtifactRoot = Join-Path $PlatformRoot 'artifact_store'
if ((Test-Path $ArtifactRoot) -and (Get-ChildItem -LiteralPath $ArtifactRoot -Force | Select-Object -First 1)) { throw 'Artifact target is not empty; refusing to overwrite it.' }
docker compose --env-file $EnvFile -f $ComposeFile exec -T postgres createdb -U $User $TargetDatabase
docker compose --env-file $EnvFile -f $ComposeFile cp (Join-Path $Bundle 'database.dump') postgres:/tmp/p1-1-restore.dump
docker compose --env-file $EnvFile -f $ComposeFile exec -T postgres pg_restore -U $User -d $TargetDatabase --no-owner --no-acl --exit-on-error /tmp/p1-1-restore.dump
if ($LASTEXITCODE -ne 0) { throw 'pg_restore failed' }

$EncodedUser = [System.Uri]::EscapeDataString($User)
$EncodedPassword = [System.Uri]::EscapeDataString($Password)
$RestoredUrl = "postgresql+psycopg://$EncodedUser`:$EncodedPassword@postgres:5432/$TargetDatabase"
docker compose --env-file $EnvFile -f $ComposeFile run --rm -e "DATABASE_URL=$RestoredUrl" api python -m alembic upgrade head
if ($LASTEXITCODE -ne 0) { throw 'Alembic upgrade of restored database failed' }
New-Item -ItemType Directory -Force -Path $ArtifactRoot | Out-Null
Expand-Archive -LiteralPath (Join-Path $Bundle 'artifact-store.zip') -DestinationPath $ArtifactRoot
$SnapshotJson = docker compose --env-file $EnvFile -f $ComposeFile run --rm --no-deps -e "DATABASE_URL=$RestoredUrl" api python -m app.maintenance.snapshot --database-url $RestoredUrl --artifact-root /app/platform/artifact_store
if ($LASTEXITCODE -ne 0) { throw 'Collecting restored snapshot failed' }
$Snapshot = ([string]::Join("`n", $SnapshotJson) | ConvertFrom-Json)
foreach ($Property in $Manifest.table_counts.PSObject.Properties) {
    $ActualCount = $Snapshot.table_counts.($Property.Name)
    if ([int64]$ActualCount -ne [int64]$Property.Value) { throw "Restored row count mismatch: $($Property.Name)" }
}
if ([int64]$Snapshot.artifact_store.file_count -ne [int64]$Manifest.artifact_store.file_count) { throw 'Restored Artifact Store file count mismatch' }
if ([int64]$Snapshot.artifact_store.size_bytes -ne [int64]$Manifest.artifact_store.size_bytes) { throw 'Restored Artifact Store size mismatch' }
docker compose --env-file $EnvFile -f $ComposeFile run --rm --no-deps -e "DATABASE_URL=$RestoredUrl" worker python -m app.maintenance.verify_artifacts --database-url $RestoredUrl --artifact-root /app/platform/artifact_store
if ($LASTEXITCODE -ne 0) { throw 'ArtifactVersion-to-file verification failed' }
docker compose --env-file $EnvFile -f $ComposeFile run --rm -e "DATABASE_URL=$RestoredUrl" worker python -m app.worker.recover --expire-active
if ($LASTEXITCODE -ne 0) { throw 'Restored workflow reconciliation failed' }
Write-Host 'Restore verification succeeded. No existing database was replaced.'
Write-Host "Set DATABASE_URL to the restored database only after review: $TargetDatabase"
