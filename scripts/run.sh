#!/usr/bin/env bash
# 一键运行（Linux / macOS）
# 前置：python3.11+、ffmpeg、可访问外网（edge-tts）
set -euo pipefail
cd "$(dirname "$0")/.."

if [ ! -d .venv ]; then
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -q -r requirements.txt
python -m playwright install chromium

exec python -m video_gen "$@"
