param([int]$Port = 8502)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$env:PYTHONUTF8 = '1'
if (-not $env:LAW_API_KEY) {
    $lawOc = [Environment]::GetEnvironmentVariable('LAW_OC', 'User')
    if ($lawOc) { $env:LAW_API_KEY = $lawOc }
}
& "$PSScriptRoot/.venv/Scripts/python.exe" -m streamlit run app.py --server.address 127.0.0.1 --server.port $Port --browser.gatherUsageStats false --server.headless true
exit $LASTEXITCODE
