"""ffmpeg 封装：探测时长、逐镜合成（图+音）、拼接、烧录字幕。"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from . import config


class FfmpegMissing(RuntimeError):
    pass


def ensure_ffmpeg() -> None:
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise FfmpegMissing(
            "未找到 ffmpeg/ffprobe。本地运行请先安装：Windows 用 winget install Gyan.FFmpeg；"
            "或直接使用项目提供的 Docker 镜像。")


def probe_duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "json", str(path)],
        check=True, capture_output=True, text=True)
    return float(json.loads(out.stdout)["format"]["duration"])


def render_shot(image: Path, audio: Path, out: Path, tail: float | None = None) -> float:
    """图片 + 音频 → 单镜 mp4。返回片段总时长（秒）。"""
    tail = config.TAIL_SECONDS if tail is None else tail
    total = probe_duration(audio) + tail
    vf = (f"scale={config.WIDTH}:{config.HEIGHT}:force_original_aspect_ratio=decrease,"
          f"pad={config.WIDTH}:{config.HEIGHT}:(ow-iw)/2:(oh-ih)/2:white")
    subprocess.run([
        "ffmpeg", "-y",
        "-loop", "1", "-framerate", str(config.FPS), "-i", str(image),
        "-i", str(audio),
        "-filter_complex", f"[0:v]{vf}[v];[1:a]apad=pad_dur={tail:.2f}[a]",
        "-map", "[v]", "-map", "[a]",
        "-t", f"{total:.3f}",
        "-c:v", "libx264", "-tune", "stillimage", "-preset", "medium", "-crf", "20",
        "-pix_fmt", "yuv420p", "-r", str(config.FPS),
        "-c:a", "aac", "-b:a", "192k",
        str(out),
    ], check=True, capture_output=True)
    return total


def concat(clips: list[Path], out: Path) -> None:
    """concat demuxer 拼接（所有片段编码参数一致）。"""
    list_file = out.with_suffix(".txt")
    list_file.write_text("".join(f"file '{c.resolve().as_posix()}'\n" for c in clips),
                         encoding="utf-8")
    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_file),
         "-c", "copy", str(out)],
        check=True, capture_output=True, cwd=str(out.parent))


def burn_subtitles(video: Path, srt: Path, out: Path) -> None:
    """烧录中文字幕。srt 用相对路径（cwd 设为其目录），规避 Windows 转义问题。"""
    style = ("FontName=Noto Sans CJK SC,FontSize=20,PrimaryColour=&H00FFFFFF,"
             "OutlineColour=&H66000000,BorderStyle=1,Outline=1.5,Shadow=0,MarginV=34")
    subprocess.run([
        "ffmpeg", "-y", "-i", str(video),
        "-vf", f"subtitles={srt.name}:force_style='{style}'",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-c:a", "copy", str(out),
    ], check=True, capture_output=True, cwd=str(srt.parent))
