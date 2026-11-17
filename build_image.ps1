param([string]$BaseImage = 'python:3.12-slim')

$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot

function Invoke-Docker {
    & docker @args
    if ($LASTEXITCODE -ne 0) {
        throw "Docker failed: $($args[0]) (exit $LASTEXITCODE)"
    }
}

Get-Command docker -ErrorAction Stop | Out-Null
Invoke-Docker version --format '{{.Server.Version}}'
$tag = 'zhixun-harness:public-v1'
Invoke-Docker build --platform linux/amd64 --build-arg "BASE_IMAGE=$BaseImage" --tag $tag .
$platform = Invoke-Docker image inspect --format '{{.Os}}/{{.Architecture}}' $tag
if ($platform -ne 'linux/amd64') { throw "Unexpected image platform: $platform" }

# Use a new output directory so a previous run cannot satisfy this check.
$testDir = New-Item -ItemType Directory -Path (Join-Path $PSScriptRoot ("container-test-" + [guid]::NewGuid().ToString('N')))
Invoke-Docker run --rm --network none --cpus 4 --memory 8g --platform linux/amd64 --mount "type=bind,source=$($testDir.FullName),target=/results" $tag --simulate --output /results --rounds 10
$summary = Get-Content -LiteralPath (Join-Path $testDir.FullName 'summary.json') -Raw -Encoding UTF8 | ConvertFrom-Json
foreach ($name in 'A','B','C') {
    $task = $summary.tasks.$name
    if ($task.rounds -ne 10 -or !(Test-Path -LiteralPath (Join-Path $testDir.FullName $task.checkpoint) -PathType Leaf)) {
        throw "Incomplete container run for task $name"
    }
}

$target = Join-Path $PSScriptRoot 'zhixun-harness-linux-amd64.tar'
$staging = "$target.$([guid]::NewGuid().ToString('N')).tmp"
try {
    Invoke-Docker save --output $staging $tag
    if ((Get-Item -LiteralPath $staging).Length -gt 2000000000) { throw 'Archive exceeds 2 GB' }
    $manifest = & tar -xOf $staging manifest.json
    if ($LASTEXITCODE -ne 0) { throw 'Could not read Docker archive manifest' }
    $entries = @((($manifest -join "`n") | ConvertFrom-Json))
    if ($entries.Count -ne 1 -or $entries[0].RepoTags -notcontains $tag) { throw 'Unexpected archive contents' }
    Move-Item -LiteralPath $staging -Destination $target -Force
    Get-Item -LiteralPath $target | Select-Object FullName,Length
    Get-FileHash -Algorithm SHA256 -LiteralPath $target
} finally {
    if (Test-Path -LiteralPath $staging) { Remove-Item -LiteralPath $staging }
}
