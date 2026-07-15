[CmdletBinding()]
param(
    [switch]$WithRedis,
    [switch]$Docker,
    [switch]$E2E
)

$ErrorActionPreference = 'Stop'
$RepositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$Backend = Join-Path $RepositoryRoot 'platform\backend'
$Frontend = Join-Path $RepositoryRoot 'platform\frontend'
$Python = Join-Path $Backend '.venv\Scripts\python.exe'

if ($Docker) {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw 'Docker Desktop / docker CLI is required.' }
    $PlatformRoot = Join-Path $RepositoryRoot 'platform'
    $ComposeFile = Join-Path $PlatformRoot 'deploy\docker-compose.yml'
    $TestComposeFile = Join-Path $PlatformRoot 'deploy\docker-compose.test.yml'
    $EnvFile = Join-Path $PlatformRoot '.env'
    if (-not (Test-Path $EnvFile)) { throw 'platform/.env is required; run bootstrap-new-machine.ps1 first.' }
    $Env = @{}
    Get-Content -LiteralPath $EnvFile | Where-Object { $_ -match '^[^#][^=]*=' } | ForEach-Object { $Key,$Value = $_ -split '=',2; $Env[$Key]=$Value }
    $User = $Env['POSTGRES_USER']; $Password = $Env['POSTGRES_PASSWORD']
    if (-not $User -or -not $Password) { throw 'POSTGRES_USER and POSTGRES_PASSWORD are required in platform/.env' }
    $TestDatabase = 'thesis_platform_test'
    docker compose --env-file $EnvFile -f $ComposeFile up -d postgres redis
    if ($LASTEXITCODE -ne 0) { throw 'Docker test infrastructure startup failed' }
    $Exists = docker compose --env-file $EnvFile -f $ComposeFile exec -T postgres psql -U $User -d postgres -Atc "select 1 from pg_database where datname='$TestDatabase'"
    if (([string]$Exists).Trim() -ne '1') {
        docker compose --env-file $EnvFile -f $ComposeFile exec -T postgres createdb -U $User $TestDatabase
        if ($LASTEXITCODE -ne 0) { throw 'Creating isolated test database failed' }
    }
    $EncodedUser = [System.Uri]::EscapeDataString($User)
    $EncodedPassword = [System.Uri]::EscapeDataString($Password)
    $env:TEST_DATABASE_URL = "postgresql+psycopg://$EncodedUser`:$EncodedPassword@postgres:5432/$TestDatabase"
    try {
        docker compose --env-file $EnvFile -f $ComposeFile -f $TestComposeFile build backend-tests frontend-tests
        if ($LASTEXITCODE -ne 0) { throw 'Building Docker test images failed' }
        docker compose --env-file $EnvFile -f $ComposeFile -f $TestComposeFile run --rm backend-tests sh -c "cd /app/ingest-cli && python -m pytest -q"
        if ($LASTEXITCODE -ne 0) { throw 'Docker Ingest CLI tests failed' }
        docker compose --env-file $EnvFile -f $ComposeFile -f $TestComposeFile run --rm backend-tests
        if ($LASTEXITCODE -ne 0) { throw 'Docker backend tests failed' }
        docker compose --env-file $EnvFile -f $ComposeFile -f $TestComposeFile run --rm frontend-tests
        if ($LASTEXITCODE -ne 0) { throw 'Docker frontend tests failed' }
        if ($E2E) {
            docker compose --env-file $EnvFile -f $ComposeFile up -d --build api publisher worker frontend
            if ($LASTEXITCODE -ne 0) { throw 'Starting application services for E2E failed' }
            docker compose --env-file $EnvFile -f $ComposeFile -f $TestComposeFile build e2e
            if ($LASTEXITCODE -ne 0) { throw 'Building Playwright test image failed' }
            docker compose --env-file $EnvFile -f $ComposeFile -f $TestComposeFile run --rm e2e
            if ($LASTEXITCODE -ne 0) { throw 'Docker Playwright E2E failed' }
        }
    } finally {
        Remove-Item Env:TEST_DATABASE_URL -ErrorAction SilentlyContinue
    }
    Write-Host 'Docker acceptance tests passed.'
    exit 0
}

if (-not (Test-Path $Python)) { throw 'Local backend virtual environment is missing; use -Docker on a Docker-only computer.' }

Push-Location (Join-Path $RepositoryRoot 'ingest-cli')
try { & $Python -m pytest -q; if ($LASTEXITCODE -ne 0) { throw 'CLI tests failed' } } finally { Pop-Location }

Push-Location $Backend
try {
    if ($WithRedis) { $env:RUN_REDIS_TESTS = '1' }
    & $Python -m pytest -q
    if ($LASTEXITCODE -ne 0) { throw 'Backend tests failed' }
} finally { Pop-Location }

Push-Location $Frontend
try {
    npm test
    if ($LASTEXITCODE -ne 0) { throw 'Frontend tests failed' }
    npm run typecheck
    if ($LASTEXITCODE -ne 0) { throw 'Frontend typecheck failed' }
    npm run build
    if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed' }
} finally { Pop-Location }
