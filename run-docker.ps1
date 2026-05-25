# Docker launcher (Windows). Auto-detects NVIDIA GPU and picks the right image.
#
# Usage:
#   .\run-docker.ps1                       # auto-find a video in the current folder
#   .\run-docker.ps1 path\to\video.mkv
#   .\run-docker.ps1 path\to\video.mkv --model large-v3
#
# First run will build the image (~few minutes) and pull the Whisper model
# (~1.5 GB). Both are cached afterwards.
$ErrorActionPreference = 'Stop'

# Detect GPU
$useGpu = $false
try {
    & nvidia-smi -L 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) { $useGpu = $true }
} catch { }

if ($useGpu) {
    $image = 'subtitle-translator:cuda'
    $dockerfile = 'docker/cuda.Dockerfile'
    $gpuArgs = @('--gpus', 'all')
    Write-Host "GPU detected — using $image" -ForegroundColor Green
} else {
    $image = 'subtitle-translator:cpu'
    $dockerfile = 'docker/cpu.Dockerfile'
    $gpuArgs = @()
    Write-Host "No NVIDIA GPU detected — using $image (CPU-only, slow)" -ForegroundColor Yellow
}

# Build image if missing
$exists = (& docker image inspect $image 2>$null | Out-String).Trim()
if (-not $exists) {
    Write-Host "Building $image (one-time, a few minutes)..." -ForegroundColor Cyan
    & docker build -f $dockerfile -t $image .
    if ($LASTEXITCODE -ne 0) { throw "docker build failed" }
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
