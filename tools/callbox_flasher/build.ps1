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

Write-Host "Running test suite in build environment..."
$env:PYTHONPATH = $RepoRoot
& $Python -m unittest discover -s (Join-Path $ToolRoot 'tests') -v

Write-Host "Packaging executable with PyInstaller..."
$WorkDir = Join-Path $ToolRoot 'build'
if (Test-Path -LiteralPath $WorkDir) {
    Remove-Item -LiteralPath $WorkDir -Recurse -Force -ErrorAction SilentlyContinue
}
$DistDir = Join-Path $ToolRoot 'dist'
if (Test-Path -LiteralPath $DistDir) {
    Remove-Item -LiteralPath $DistDir -Recurse -Force -ErrorAction SilentlyContinue
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
