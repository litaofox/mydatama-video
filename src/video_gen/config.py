"""全局配置：全部来自环境变量（可选 .env 文件），不与任何项目共享配置。"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]          # mydatama-video/
ASSETS = ROOT / "assets"
NARRATION_MD = ASSETS / "narration" / "分镜脚本与旁白.md"
SLIDES_HTML = ASSETS / "slides.html"
FIXTURES_DIR = ASSETS / "fixtures"
FIXTURES_GEN = FIXTURES_DIR / "generator" / "generate_all.py"
OUTPUT_DIR = ROOT / "output"


def _load_dotenv() -> None:
    """极简 .env 解析（不引入 python-dotenv 依赖）。"""
    env_file = ROOT / ".env"
    if not env_file.exists():
        return
    for raw in env_file.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv()

# ---- 目标平台（唯一耦合点：HTTP 地址 + 演示账号） ----
BASE_URL = os.environ.get("BASE_URL", "http://localhost:8090").rstrip("/")
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "Admin@123")

# ---- TTS ----
TTS_VOICE = os.environ.get("TTS_VOICE", "zh-CN-YunxiNeural")
TTS_RATE = os.environ.get("TTS_RATE", "-5%")
# TTS 不可用时的兜底语速（字/分钟），用于生成等长静音
FALLBACK_RATE_CPM = int(os.environ.get("FALLBACK_RATE_CPM", "220"))
TAIL_SECONDS = float(os.environ.get("TAIL_SECONDS", "0.8"))

# ---- 视频规格 ----
WIDTH = int(os.environ.get("VIDEO_WIDTH", "1920"))
HEIGHT = int(os.environ.get("VIDEO_HEIGHT", "1080"))
FPS = int(os.environ.get("VIDEO_FPS", "30"))
FINAL_NAME = os.environ.get("FINAL_NAME", "mydatama-v0.1-讲解视频-1080p.mp4")

# ---- 轮询 ----
LIVE_TIMEOUT = int(os.environ.get("LIVE_TIMEOUT", "300"))
POLL_INTERVAL = float(os.environ.get("POLL_INTERVAL", "3"))
HEADLESS = os.environ.get("HEADLESS", "true").lower() not in ("0", "false", "no")

# ---- 演示造数（默认关闭）----
# 平台 configure 阶段会硬性拦阻密级倒挂（错误码 600008），因此走公开 HTTP 无法让产品带着
# 倒挂密级进入 GENERATED。为在视频中如实复现合规引擎 R1 红屏，可显式提供演示库 DSN，
# 生成器会在反面产品 GENERATED 后直接把其密级 UPDATE 为 1 再触发合规校验。
# 仅限一次性演示库，切勿指向生产。例如：
# DEMO_TWEAK_DSN=host=postgres port=5432 dbname=mydatama user=mydatama password=***
DEMO_TWEAK_DSN = os.environ.get("DEMO_TWEAK_DSN", "").strip()

# 兼容矩阵：本生成器验证过的平台版本
COMPAT_PLATFORM = "v0.1.0"


def work_dirs() -> dict[str, Path]:
    dirs = {
        "root": OUTPUT_DIR,
        "audio": OUTPUT_DIR / "work" / "audio",
        "img": OUTPUT_DIR / "work" / "img",
        "clip": OUTPUT_DIR / "work" / "clip",
    }
    for p in dirs.values():
        p.mkdir(parents=True, exist_ok=True)
    return dirs
