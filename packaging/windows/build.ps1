param([Parameter(Mandatory=$true)][string]$PythonRoot, [string]$ForecastWorkbook)
$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
Set-Location -LiteralPath $root
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
$env:PATH = "$env:USERPROFILE/.cargo/bin;$root/.venv/Scripts;$env:PATH"
function Run-Native([string]$Program, [string[]]$Arguments) {
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Command failed ($LASTEXITCODE): $Program" }
}
$arguments = @('packaging/windows/prepare_payload.py', '--python-root', $PythonRoot)
if ($ForecastWorkbook) { $arguments += @('--forecast-workbook', $ForecastWorkbook) }
Run-Native "$root/.venv/Scripts/python.exe" @('-m', 'pip', 'install', 'uv')
Run-Native "$root/.venv/Scripts/python.exe" $arguments
Run-Native 'npm.cmd' @('--prefix', 'desktop', 'ci')
Push-Location -LiteralPath (Join-Path $root 'desktop')
try { Run-Native 'npm.cmd' @('run', 'build', '--', '--bundles', 'nsis') }
finally { Pop-Location }
$output = Join-Path $root 'dist/windows'
New-Item -ItemType Directory -Force $output | Out-Null
$targetRoot = if ($env:CARGO_TARGET_DIR) { [IO.Path]::GetFullPath($env:CARGO_TARGET_DIR) } else { "$root/desktop/src-tauri/target" }
$installers = @(Get-ChildItem -LiteralPath "$targetRoot/release/bundle/nsis" -Filter '*.exe')
if ($installers.Count -eq 0) { throw 'NSIS build produced no installer.' }
$installers | ForEach-Object {
    $destination = Join-Path $output $_.Name
    Copy-Item -LiteralPath $_.FullName -Destination $destination
    $digest = (Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash.ToLowerInvariant()
    [IO.File]::WriteAllText("$destination.sha256", "$digest  $($_.Name)`n")
}
Write-Host "Windows installer and SHA256: $output"
