"""按每镜实际音频时长自动切分并生成 SRT 字幕（与成片严格对齐）。"""
from __future__ import annotations

import re
from pathlib import Path

_SENT_SPLIT = re.compile(r"(?<=[。！？；!?;;])")
_CLAUSE_SPLIT = re.compile(r"[，,、：:]")
_MAX_LINE = 22          # 单行最大字数
_MIN_CUE = 1.4         # 单条字幕最短秒数


def _phrases(text: str) -> list[str]:
    """句号切大句，逗号切小句，超长再硬切。"""
    phrases: list[str] = []
    for sent in _SENT_SPLIT.split(text):
        sent = sent.strip()
        if not sent:
            continue
        buf = ""
        for clause in _CLAUSE_SPLIT.split(sent):
            clause = clause.strip()
            if not clause:
                continue
            if len(buf) + len(clause) <= _MAX_LINE:
                buf = (buf + "，" + clause).strip("，")
            else:
                if buf:
                    phrases.append(buf)
                while len(clause) > _MAX_LINE:
                    phrases.append(clause[:_MAX_LINE])
                    clause = clause[_MAX_LINE:]
                buf = clause
        if buf:
            phrases.append(buf)
    return phrases


def _ts(seconds: float) -> str:
    if seconds < 0:
        seconds = 0
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}".replace(".", ",")


def build_srt(shot_durations: dict[int, float], narrations: dict[int, str],
              out_path: Path) -> None:
    """shot_durations/narrations: {镜号: ...}。按字数比例把镜头时长分配给短语。"""
    blocks: list[str] = []
    cue_no = 1
    cursor = 0.0

    for shot_no in sorted(shot_durations):
        duration = shot_durations[shot_no]
        phrases = _phrases(narrations[shot_no])
        if not phrases:
            cursor += duration
            continue
        weights = [max(len(p), 4) for p in phrases]
        total_w = sum(weights)
        start = cursor
        for i, phrase in enumerate(phrases):
            raw_dur = duration * weights[i] / total_w
            end = start + raw_dur if i < len(phrases) - 1 else cursor + duration
            # 保证除最后一条外不短于 _MIN_CUE
            if i < len(phrases) - 1 and end - start < _MIN_CUE:
                end = min(cursor + duration, start + _MIN_CUE)
            blocks.append(f"{cue_no}\n{_ts(start)} --> {_ts(end)}\n{phrase}\n")
            cue_no += 1
            start = end
        cursor += duration

    out_path.write_text("\n".join(blocks), encoding="utf-8")
