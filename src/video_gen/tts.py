"""TTS：edge-tts 神经语音；联网失败时用 ffmpeg 等长静音兜底，保证流水线不断。"""
from __future__ import annotations

import asyncio
import hashlib
import json
import re
import subprocess
import time

from pathlib import Path

from . import config

# 低于该平均响度（dB）视为静音兜底/坏文件，不允许当作神经语音复用
_AUDIBLE_THRESHOLD_DB = -60.0
# edge-tts 偶发 "No audio was received"（限流/网络抖动），按次退避重试
_MAX_ATTEMPTS = 4
_RETRY_BACKOFF_S = (3, 8, 15)


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


def _mean_volume_db(path: Path) -> float:
    """用 ffmpeg volumedetect 读平均响度；解析不到按 -∞（静音）处理。"""
    proc = subprocess.run(
        ["ffmpeg", "-i", str(path), "-af", "volumedetect", "-f", "null", "-"],
        check=True, capture_output=True, text=True,
    )
    m = re.search(r"mean_volume:\s*(-?[\d.]+)\s*dB", proc.stderr)
    return float(m.group(1)) if m else -910.0


def _cache_key(text: str) -> str:
    raw = f"{config.TTS_VOICE}|{config.TTS_RATE}|{text}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def synth_one(text: str, out_path: Path) -> bool:
    """合成单段并做响度校验（含退避重试）。返回 True=神经语音，False=静音兜底。"""
    meta_path = out_path.with_suffix(".meta")
    last_exc: Exception | None = None
    for attempt in range(_MAX_ATTEMPTS):
        try:
            asyncio.run(_edge_tts(text, out_path))
            if out_path.exists() and out_path.stat().st_size > 1024:
                mean_db = _mean_volume_db(out_path)
                if mean_db > _AUDIBLE_THRESHOLD_DB:
                    meta_path.write_text(json.dumps(
                        {"key": _cache_key(text), "meanVolumeDb": mean_db},
                        ensure_ascii=False), encoding="utf-8")
                    return True
                last_exc = RuntimeError(f"合成结果疑似静音（{mean_db:.1f}dB）")
                print(f"[tts] {last_exc}")
        except Exception as exc:  # 网络故障/服务不可用/未安装
            last_exc = exc
            print(f"[tts] edge-tts 第 {attempt + 1} 次尝试失败: {exc}")
        if attempt < _MAX_ATTEMPTS - 1:
            time.sleep(_RETRY_BACKOFF_S[min(attempt, len(_RETRY_BACKOFF_S) - 1)])
    print(f"[tts] {_MAX_ATTEMPTS} 次均失败，本段改静音兜底: {last_exc}")
    _silence(text, out_path)
    meta_path.unlink(missing_ok=True)
    return False


def synth_all(shots, audio_dir: Path) -> dict[int, Path]:
    result: dict[int, Path] = {}
    neural = 0
    for shot in shots:
        out = audio_dir / f"shot_{shot.no:02d}.mp3"
        meta_path = out.with_suffix(".meta")
        reusable = False
        # 仅当语音参数+文案指纹与 .meta 一致才复用，杜绝把历史静音兜底当真人声
        if out.exists() and meta_path.exists():
            try:
                reusable = json.loads(meta_path.read_text("utf-8")).get("key") == _cache_key(shot.narration)
            except (ValueError, OSError):
                reusable = False
        if reusable:
            neural += 1
        elif synth_one(shot.narration, out):
            neural += 1
        result[shot.no] = out
    print(f"[tts] 完成 {len(shots)} 段（神经语音 {neural}/{len(shots)}，静音兜底 {len(shots) - neural}）")
    if neural < len(shots):
        raise RuntimeError(
            f"{len(shots) - neural} 段语音合成失败（已重试 {_MAX_ATTEMPTS} 次），"
            "已保留成功段缓存，网络恢复后重跑即可续合")
    return result
