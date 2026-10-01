"""Playwright 截图：幻灯片页（file://）与平台真实页面（http，注入登录态）。

浏览器只负责"按路由截图"，造数据全部由 platform_api 完成。
"""
from __future__ import annotations

import json
from pathlib import Path

from . import config
# playwright 在 capture() 内延迟导入：--dry-run 与 --slides-only 的环境校验无需安装浏览器。


def capture_route(route: str, auth_state: dict | None, out_path: Path) -> Path:
    """单页截图（动线前置镜头，如镜 24 的出厂空态大屏）。失败抛异常由调用方兜底。"""
    from playwright.sync_api import sync_playwright  # 延迟导入

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=config.HEADLESS, args=[
            "--force-device-scale-factor=1",
            "--hide-scrollbars",
        ])
        context = browser.new_context(
            viewport={"width": config.WIDTH, "height": config.HEIGHT},
            device_scale_factor=1,
        )
        if auth_state:
            context.add_init_script(
                f"localStorage.setItem('mydatama_auth', {json.dumps(json.dumps(auth_state, ensure_ascii=False))});"
            )
        page = context.new_page()
        try:
            page.goto(f"{config.BASE_URL}{route}", wait_until="domcontentloaded")
            try:
                page.wait_for_load_state("networkidle", timeout=8000)
            except Exception:
                pass
            page.wait_for_timeout(1800)
            page.screenshot(path=str(out_path))
        finally:
            page.close()
            browser.close()
    return out_path


def capture(slide_targets: dict[int, tuple[int, Path]], live_targets: dict[int, Path],
            live_routes: dict[int, str], auth_state: dict | None) -> dict[int, Path]:
    """slide_targets: {分镜号: (幻灯片页码, 输出路径)}；live_targets: {分镜号: 输出路径}。

    返回 {分镜号: 实际截图路径}。单个页面截图失败不影响其他镜头（调用方可用转场卡兜底）。
    """
    images: dict[int, Path] = {}
    slides_url = config.SLIDES_HTML.resolve().as_uri()

    from playwright.sync_api import sync_playwright  # 延迟导入

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=config.HEADLESS, args=[
            "--force-device-scale-factor=1",
            "--hide-scrollbars",
        ])
        context = browser.new_context(
            viewport={"width": config.WIDTH, "height": config.HEIGHT},
            device_scale_factor=1,
        )
        if auth_state:
            # 与前端 store/auth.ts 的 STORAGE_KEY 保持一致
            context.add_init_script(
                f"localStorage.setItem('mydatama_auth', {json.dumps(json.dumps(auth_state, ensure_ascii=False))});"
            )

        # 1) 幻灯片：file:///.../slides.html#页码
        if slide_targets:
            page = context.new_page()
            for no, (page_no, out) in sorted(slide_targets.items()):
                page.goto(f"{slides_url}#{page_no}", wait_until="load")
                # 隐藏翻页提示条与光标，保证画面干净
                page.evaluate(
                    "document.querySelectorAll('.hint').forEach(e => e.style.display='none');"
                    "document.body.style.cursor='none';")
                page.wait_for_timeout(1200)   # 等动画/高亮渲染
                page.screenshot(path=str(out))
                images[no] = out
            page.close()

        # 2) 真实平台页面（单页失败容错：跳过该镜，由调用方兜底）
        if live_targets and auth_state:
            page = context.new_page()
            for no, out in sorted(live_targets.items()):
                route = live_routes.get(no)
                if not route:
                    continue
                try:
                    page.goto(f"{config.BASE_URL}{route}", wait_until="domcontentloaded")
                    try:
                        page.wait_for_load_state("networkidle", timeout=8000)
                    except Exception:
                        pass
                    page.wait_for_timeout(1800)
                    page.screenshot(path=str(out))
                    images[no] = out
                except Exception as exc:
                    print(f"[browser] 镜 {no} 截图失败（将用转场卡兜底）: {exc}")
            page.close()

        browser.close()
    return images
