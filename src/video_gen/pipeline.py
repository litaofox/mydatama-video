"""编排：分镜 → 造数(可选) → 截图 → TTS → 逐镜合成 → 拼接 → 烧字幕 → MP4。"""
from __future__ import annotations

import shutil
from pathlib import Path

from . import browser, config, ffmpeg_utils, subtitles, tts
from .narration import load_shots


def run(*, live: bool = True, burn: bool = True, dry_run: bool = False) -> Path:
    shots = load_shots(config.NARRATION_MD)
    print(f"[plan] 共 {len(shots)} 镜；目标平台 {config.BASE_URL}；"
          f"实机镜 {[s.no for s in shots if s.is_live]}")

    # 资源完整性
    for required in (config.SLIDES_HTML, config.NARRATION_MD,
                     config.ASSETS / "vendor" / "highlight.min.js",
                     config.FIXTURES_GEN):
        if not required.exists():
            raise FileNotFoundError(f"缺少素材: {required}")

    if dry_run:
        print("[dry-run] 素材齐全，剧本解析成功，未联网、未渲染。")
        return Path()

    ffmpeg_utils.ensure_ffmpeg()
    dirs = config.work_dirs()
    audio_dir, img_dir, clip_dir = dirs["audio"], dirs["img"], dirs["clip"]

    # ---------- 1) 画面 ----------
    slide_targets: dict[int, tuple[int, Path]] = {}
    live_targets: dict[int, Path] = {}
    for shot in shots:
        out = img_dir / f"shot_{shot.no:02d}.png"
        if shot.is_live:
            live_targets[shot.no] = out
        else:
            slide_targets[shot.no] = (shot.slide_page, out)

    # 第五章转场卡：实机截图缺失时兜底
    chapter5 = img_dir / "chapter5.png"
    slide_targets[-1] = (24, chapter5)

    auth_state = None
    live_routes: dict[int, str] = {}
    pre_images: dict[int, Path] = {}
    if live:
        print("[live] 连接平台并执行 15 步自动化动线（约 3~5 分钟）...")
        from . import scenario  # 延迟导入：仅实机模式需要 requests
        from .platform_api import PlatformClient

        client = PlatformClient(config.BASE_URL)
        client.wait_healthy()
        client.login(config.ADMIN_USERNAME, config.ADMIN_PASSWORD)
        auth_state = client.auth_state()
        # 镜 24 旁白为"出厂空态大屏"：必须在造数动线之前截图
        if 24 in live_targets:
            try:
                browser.capture_route("/screen", auth_state, live_targets[24])
                pre_images[24] = live_targets[24]
                live_targets.pop(24)
                print("[live] 镜 24 空态大屏已提前截取")
            except Exception as exc:
                print(f"[browser] 镜 24 空态截图失败，改为动线后补拍: {exc}")
        live_routes = scenario.run(client, scratch=img_dir / "scratch")
    else:
        print("[live] --slides-only：跳过实机演示，第五章使用转场卡。")

    images = browser.capture(slide_targets, live_targets, live_routes, auth_state)
    images.update(pre_images)
    for shot in shots:
        if shot.no not in images:
            print(f"[render] 镜 {shot.no} 无实机截图，使用第五章转场卡兜底")
            images[shot.no] = chapter5

    # ---------- 2) 配音 ----------
    audios = tts.synth_all(shots, audio_dir)

    # ---------- 3) 逐镜合成 ----------
    clips: list[Path] = []
    durations: dict[int, float] = {}
    for shot in shots:
        clip = clip_dir / f"shot_{shot.no:02d}.mp4"
        durations[shot.no] = ffmpeg_utils.render_shot(images[shot.no], audios[shot.no], clip)
        clips.append(clip)
        print(f"[render] 镜 {shot.no:02d} 合成完成 {durations[shot.no]:.1f}s")

    # ---------- 4) 字幕（按实际音频时长重切，天然对齐） ----------
    srt_path = dirs["root"] / "work" / "subtitles.srt"
    subtitles.build_srt(durations, {s.no: s.narration for s in shots}, srt_path)

    # ---------- 5) 拼接 + 烧字幕 ----------
    merged = dirs["root"] / "work" / "merged.mp4"
    ffmpeg_utils.concat(clips, merged)
    final = dirs["root"] / config.FINAL_NAME
    if burn and shutil.which("ffmpeg"):
        ffmpeg_utils.burn_subtitles(merged, srt_path, final)
    else:
        shutil.copyfile(merged, final)

    total = sum(durations.values())
    print(f"[done] 成片：{final}（{total / 60:.1f} 分钟，{config.WIDTH}x{config.HEIGHT}）")
    print(f"[done] 字幕文件：{srt_path}")
    return final
