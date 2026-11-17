param([string]$BaseTar = (Join-Path $PSScriptRoot 'smart-training-harness-competition-v3-linux-amd64.tar'))
$ErrorActionPreference = 'Stop'
function Invoke-Docker {
    & docker @args
    if ($LASTEXITCODE -ne 0) { throw "docker $($args[0]) failed" }
}
$tag = 'smart-training-harness:sdk-1.0.2-b-v2'
Invoke-Docker load -i $BaseTar
Invoke-Docker build --platform linux/amd64 --network none -t $tag $PSScriptRoot
$description = (Invoke-Docker run --rm --network none --read-only $tag describe) | ConvertFrom-Json
if ($description.protocol -ne 'contest.harness.workspace.v2') { throw 'Unexpected SDK protocol' }
$out = Join-Path $PSScriptRoot 'image6-sdk-b-v2-linux-amd64.tar'
$tmp = "$out.$([guid]::NewGuid()).tmp"
try {
    Invoke-Docker save -o $tmp $tag
    Move-Item -Force -LiteralPath $tmp -Destination $out
    Get-FileHash -LiteralPath $out -Algorithm SHA256
} finally {
    if (Test-Path -LiteralPath $tmp) { Remove-Item -LiteralPath $tmp }
}
