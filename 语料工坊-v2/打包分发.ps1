$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectName = Split-Path -Leaf $Root
$ReleaseRoot = Join-Path (Split-Path -Parent $Root) "release"
$ReleaseDir = Join-Path $ReleaseRoot "$ProjectName-release"
$ZipPath = Join-Path $ReleaseRoot "$ProjectName-release.zip"

$ExcludedDirs = @(
    ".git",
    "backend\.venv",
    "backend\data",
    "backend\__pycache__",
    "backend\app\__pycache__",
    "frontend\node_modules",
    "frontend\dist"
)

$ExcludedFiles = @(
    "*.pyc",
    "*.log",
    ".env"
)

Write-Host "Creating release directory..." -ForegroundColor Cyan

if (Test-Path $ReleaseDir) {
    Remove-Item -LiteralPath $ReleaseDir -Recurse -Force
}
New-Item -ItemType Directory -Path $ReleaseDir -Force | Out-Null

$xd = @()
foreach ($dir in $ExcludedDirs) {
    $xd += "/XD"
    $xd += (Join-Path $Root $dir)
}

$xf = @()
foreach ($file in $ExcludedFiles) {
    $xf += "/XF"
    $xf += $file
}

$robocopyArgs = @(
    $Root,
    $ReleaseDir,
    "/E",
    "/NFL",
    "/NDL",
    "/NJH",
    "/NJS",
    "/NP"
) + $xd + $xf

& robocopy @robocopyArgs | Out-Null
$robocopyExit = $LASTEXITCODE
if ($robocopyExit -ge 8) {
    throw "Failed to copy release files. robocopy exit code: $robocopyExit"
}

if (Test-Path $ZipPath) {
    Remove-Item -LiteralPath $ZipPath -Force
}

Write-Host "Creating release zip..." -ForegroundColor Cyan
Compress-Archive -Path (Join-Path $ReleaseDir "*") -DestinationPath $ZipPath -Force

Write-Host "Release directory: $ReleaseDir" -ForegroundColor Green
Write-Host "Release zip: $ZipPath" -ForegroundColor Green
Write-Host "The release package excludes personal data, media files, database, virtualenv, node_modules, build output, and logs." -ForegroundColor Yellow
