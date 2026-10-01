"""命令行入口：python -m video_gen [--slides-only] [--no-burn] [--dry-run]"""
from __future__ import annotations

import argparse

from .pipeline import run


def main() -> None:
    parser = argparse.ArgumentParser(
        description="mydatama 讲解视频全自动生成器（TTS + 浏览器自动化 + ffmpeg）")
    parser.add_argument("--slides-only", action="store_true",
                        help="只渲染幻灯片部分（不连接平台、不执行 15 步动线），第五章用转场卡")
    parser.add_argument("--no-burn", action="store_true",
                        help="不烧录硬字幕（仍输出 subtitles.srt，可在剪辑软件中外挂）")
    parser.add_argument("--dry-run", action="store_true",
                        help="只校验素材与剧本，不联网、不生成音视频")
    args = parser.parse_args()
    run(live=not args.slides_only, burn=not args.no_burn, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
