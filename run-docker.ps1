# Docker launcher (Windows). Auto-detects NVIDIA GPU and picks the right image.
#
# Usage:
#   .\run-docker.ps1                       # auto-find a video in the current folder
#   .\run-docker.ps1 path\to\video.mkv
#   .\run-docker.ps1 path\to\video.mkv --model large-v3
#
# By default pulls a pre-built image from GHCR. Set $env:TRANSLATOR_BUILD_LOCAL=1
# to force a local build instead.
$ErrorActionPreference = 'Stop'

$registry = 'ghcr.io/shytech1/multilingual-subtitle-translator'

# Detect GPU
$useGpu = $false
try {
    & nvidia-smi -L 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) { $useGpu = $true }
} catch { }

if ($useGpu) {
    $variant = 'cuda'
    $dockerfile = 'docker/cuda.Dockerfile'
    $gpuArgs = @('--gpus', 'all')
    Write-Host "GPU detected — using $variant image" -ForegroundColor Green
} else {
    $variant = 'cpu'
    $dockerfile = 'docker/cpu.Dockerfile'
    $gpuArgs = @()
    Write-Host "No NVIDIA GPU detected — using $variant image (CPU-only, slow)" -ForegroundColor Yellow
}

$image = "${registry}:${variant}"

# Resolve image: pull from GHCR by default, fall back to local build on failure.
$forceLocal = $env:TRANSLATOR_BUILD_LOCAL -eq '1'
$haveImage  = (& docker image inspect $image 2>$null | Out-String).Trim()

if (-not $haveImage) {
    if (-not $forceLocal) {
        Write-Host "Pulling $image ..." -ForegroundColor Cyan
        & docker pull $image
        if ($LASTEXITCODE -ne 0) {
            Write-Host "Pull failed — falling back to local build." -ForegroundColor Yellow
            $forceLocal = $true
        }
    }
    if ($forceLocal) {
        Write-Host "Building $image locally (one-time, a few minutes)..." -ForegroundColor Cyan
        & docker build -f $dockerfile -t $image .
        if ($LASTEXITCODE -ne 0) { throw "docker build failed" }
    }
}

# Decide what to mount as /data and how to invoke
if ($args.Count -gt 0 -and (Test-Path -LiteralPath $args[0])) {
    $videoPath = (Resolve-Path -LiteralPath $args[0]).Path
    $mountDir  = Split-Path -Parent $videoPath
    $videoName = Split-Path -Leaf $videoPath
    $extra     = @($args | Select-Object -Skip 1)
    $cmdArgs   = @($videoName) + $extra
} else {
    $mountDir = (Get-Location).Path
    $cmdArgs  = $args
}

# Share the Hugging Face model cache with the native install
$hfCache = if ($env:HF_HOME) { $env:HF_HOME } else { Join-Path $env:USERPROFILE '.cache\huggingface' }
New-Item -ItemType Directory -Force -Path $hfCache | Out-Null

$dockerArgs = @(
    'run', '--rm', '-it'
) + $gpuArgs + @(
    '-v', ("{0}:/data" -f $mountDir),
    '-v', ("{0}:/cache/huggingface" -f $hfCache),
    $image
) + $cmdArgs

Write-Host ">> docker $($dockerArgs -join ' ')" -ForegroundColor DarkGray
& docker @dockerArgs
