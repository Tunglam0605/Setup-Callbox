$ErrorActionPreference = 'Stop'
$ToolRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = (Resolve-Path (Join-Path $ToolRoot '..\..')).Path
$Venv = Join-Path $ToolRoot '.venv-build'
$Python = Join-Path $Venv 'Scripts\python.exe'

if (Test-Path -LiteralPath $Venv) {
    $ResolvedVenv = (Resolve-Path -LiteralPath $Venv).Path
    $ExpectedPrefix = $ToolRoot + [System.IO.Path]::DirectorySeparatorChar
    if (-not $ResolvedVenv.StartsWith($ExpectedPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Venv path '$ResolvedVenv' is outside ToolRoot '$ToolRoot'"
    }
    Remove-Item -LiteralPath $Venv -Recurse -Force
}

Write-Host "Creating virtual environment at $Venv..."
python -m venv $Venv

Write-Host "Installing dependencies..."
& $Python -m pip install --disable-pip-version-check -r (Join-Path $ToolRoot 'requirements-build.txt')

Write-Host "Syncing embedded firmware package from build_flash..."
& $Python (Join-Path $ToolRoot "sync_firmware_assets.py")
if ($LASTEXITCODE -ne 0) { throw "Firmware asset sync failed" }

Write-Host "Running test suite in build environment..."
$env:PYTHONPATH = $RepoRoot
& $Python -m unittest discover -s (Join-Path $ToolRoot 'tests') -v
if ($LASTEXITCODE -ne 0) { throw "Tool test suite failed with exit code $LASTEXITCODE" }

Write-Host "Packaging executable with PyInstaller..."
$WorkDir = Join-Path $ToolRoot 'build'
if (Test-Path -LiteralPath $WorkDir) {
    Remove-Item -LiteralPath $WorkDir -Recurse -Force -ErrorAction SilentlyContinue
}
$DistDir = Join-Path $ToolRoot 'dist'
$FactoryProfile = Join-Path $DistDir 'Setup-CallBox.factory.json'
$FactoryProfileBytes = if (Test-Path -LiteralPath $FactoryProfile) {
    [System.IO.File]::ReadAllBytes($FactoryProfile)
} else {
    $null
}
if (Test-Path -LiteralPath $DistDir) {
    Remove-Item -LiteralPath $DistDir -Recurse -Force -ErrorAction SilentlyContinue
}
New-Item -ItemType Directory -Path $DistDir -Force | Out-Null
if ($null -ne $FactoryProfileBytes) {
    [System.IO.File]::WriteAllBytes($FactoryProfile, $FactoryProfileBytes)
}

& $Python -m PyInstaller --clean --noconfirm `
    --distpath (Join-Path $ToolRoot 'dist') `
    --workpath (Join-Path $ToolRoot 'build') `
    (Join-Path $ToolRoot 'Setup-CallBox.spec')
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller build failed with exit code $LASTEXITCODE"
}

$Exe = Join-Path $ToolRoot 'dist\Setup-CallBox.exe'
if (-not (Test-Path -LiteralPath $Exe)) {
    throw "Packaged EXE not found at '$Exe'"
}

Write-Host "Running EXE self-test..."
& $Exe --self-test
if ($LASTEXITCODE -ne 0) {
    throw "Packaged EXE self-test failed with exit code $LASTEXITCODE"
}

Write-Host "Executable generated successfully."
Get-FileHash -LiteralPath $Exe -Algorithm SHA256

Write-Host "Generating source-free public release bundle..."
& $Python (Join-Path $ToolRoot 'publish_release_bundle.py')
if ($LASTEXITCODE -ne 0) { throw "Public release bundle generation failed" }

