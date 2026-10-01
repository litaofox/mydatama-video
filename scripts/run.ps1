# 一键运行（Windows / PowerShell）
# 前置：python 3.11+、ffmpeg、可访问外网（edge-tts）
param(
    [switch]$SlidesOnly,
    [switch]$NoBurn,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..

if (-not (Test-Path .venv)) {
    python -m venv .venv
}
. .\.venv\Scripts\Activate.ps1
python -m pip install -q -r requirements.txt
python -m playwright install chromium

$args = @("-m", "video_gen")
if ($SlidesOnly) { $args += "--slides-only" }
if ($NoBurn)     { $args += "--no-burn" }
if ($DryRun)     { $args += "--dry-run" }
python @args
