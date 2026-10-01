"""TTS：edge-tts 神经语音；联网失败时用 ffmpeg 等长静音兜底，保证流水线不断。"""
from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path

from . import config


def _estimate_seconds(text: str) -> float:
    # 中文按字符数估算（标点不计），220 字/分钟
    chars = sum(1 for ch in text if ch.strip() and ch not in "，。！？；：、“”‘’《》——…·.,!?;:\"'()（）")
    return max(3.0, chars * 60.0 / config.FALLBACK_RATE_CPM)


async def _edge_tts(text: str, out_path: Path) -> None:
    import edge_tts  # 延迟导入：离线/未安装时仍可走静音兜底

    communicate = edge_tts.Communicate(text, config.TTS_VOICE, rate=config.TTS_RATE)
    await communicate.save(str(out_path))


def _silence(text: str, out_path: Path) -> None:
    seconds = _estimate_seconds(text)
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
         "-t", f"{seconds:.2f}", "-q:a", "9", "-acodec", "libmp3lame", str(out_path)],
        check=True, capture_output=True,
    )


def synth_one(text: str, out_path: Path) -> bool:
    """返回 True=神经语音，False=静音兜底。"""
    try:
        asyncio.run(_edge_tts(text, out_path))
        if out_path.exists() and out_path.stat().st_size > 1024:
            return True
    except Exception as exc:  # 网络故障/服务不可用/未安装
        print(f"[tts] edge-tts 不可用，本段改静音兜底: {exc}")
    _silence(text, out_path)
    return False


def synth_all(shots, audio_dir: Path) -> dict[int, Path]:
    result: dict[int, Path] = {}
    neural = 0
    for shot in shots:
        out = audio_dir / f"shot_{shot.no:02d}.mp3"
        if out.exists() and out.stat().st_size > 1024:
            neural += 1
            result[shot.no] = out
            continue
        if synth_one(shot.narration, out):
            neural += 1
        result[shot.no] = out
    print(f"[tts] 完成 {len(shots)} 段（神经语音 {neural}/{len(shots)}，静音兜底 {len(shots) - neural}）")
    return result
