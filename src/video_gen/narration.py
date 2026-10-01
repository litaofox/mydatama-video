"""解析分镜脚本 Markdown：抽取每镜编号与旁白逐字稿。"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

_SHOT_RE = re.compile(r"^###\s*镜\s*(\d+)｜")


@dataclass
class Shot:
    no: int
    narration: str

    @property
    def is_live(self) -> bool:
        """24~30 镜为实机录屏章，其余为幻灯片。"""
        return 24 <= self.no <= 30

    @property
    def slide_page(self) -> int | None:
        """分镜号 → slides.html 页码（第 24 页为第五章转场卡）。"""
        if self.is_live:
            return 24
        if self.no <= 23:
            return self.no
        if self.no == 31:
            return 25
        if self.no == 32:
            return 26
        return None


def load_shots(md_path: Path) -> list[Shot]:
    lines = md_path.read_text(encoding="utf-8").splitlines()
    shots: list[Shot] = []
    current_no: int | None = None
    buf: list[str] = []
    in_narration = False

    def flush() -> None:
        nonlocal buf
        if current_no is not None:
            text = "".join(buf).strip()
            if text:
                shots.append(Shot(no=current_no, narration=text))
        buf = []

    for line in lines:
        m = _SHOT_RE.match(line)
        if m:
            flush()
            current_no = int(m.group(1))
            in_narration = False
            continue
        if current_no is None:
            continue
        stripped = line.strip()
        if stripped.startswith("**旁白**"):
            in_narration = True
            continue
        if in_narration:
            if stripped.startswith(">"):
                buf.append(stripped.lstrip(">").strip())
            elif stripped.startswith("**画面**") or stripped.startswith("###"):
                in_narration = False
            elif stripped == "" and buf:
                # 旁白块结束于空行
                pass
    flush()

    shots.sort(key=lambda s: s.no)
    nos = [s.no for s in shots]
    if nos != list(range(1, len(nos) + 1)):
        raise ValueError(f"分镜编号不连续: {nos}")
    return shots
