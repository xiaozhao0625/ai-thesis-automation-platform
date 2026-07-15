[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$BundleDirectory
)

$ErrorActionPreference = 'Stop'
$Bundle = (Resolve-Path $BundleDirectory).Path
$ManifestPath = Join-Path $Bundle 'backup-manifest.json'
if (-not (Test-Path $ManifestPath)) { throw 'backup-manifest.json is missing' }
$Manifest = Get-Content -LiteralPath $ManifestPath -Raw | ConvertFrom-Json
if ($Manifest.format_version -ne 'p1-1-handoff-v1') { throw 'Unsupported handoff format_version' }
if (-not $Manifest.alembic_revision) { throw 'alembic_revision is missing' }
if ($null -eq $Manifest.table_counts) { throw 'table_counts is missing' }
if ($null -eq $Manifest.artifact_store -or $null -eq $Manifest.artifact_store.file_count -or $null -eq $Manifest.artifact_store.size_bytes) { throw 'artifact_store counts are missing' }
foreach ($Required in @('database.dump','artifact-store.zip','RESTORE.md')) {
    if ($null -eq $Manifest.files.PSObject.Properties[$Required]) { throw "Required handoff file is not declared: $Required" }
}
foreach ($File in $Manifest.files.PSObject.Properties) {
    $Path = Join-Path $Bundle $File.Name
    if (-not (Test-Path $Path)) { throw "Missing handoff file: $($File.Name)" }
    $Actual = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($Actual -ne [string]$File.Value) { throw "Hash mismatch: $($File.Name)" }
}
Write-Host "Handoff bundle verified: $Bundle"
