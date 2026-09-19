param([int]$Port = 8503)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
& "$PSScriptRoot/.venv/Scripts/python.exe" -m scripts.run_fsc_preview --port $Port
exit $LASTEXITCODE