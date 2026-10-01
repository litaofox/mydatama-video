# Changelog

## 0.1.0 — 2026-10-01

首个独立版本。

- 32 镜 / 18 分钟讲解视频一键生成：edge-tts 神经配音 → Playwright 自动截图（幻灯片 + 平台实机 15 步动线）→ ffmpeg 逐镜合成/拼接/烧录中文字幕，产出 1080p MP4
- 平台驱动仅依赖公开 HTTP 契约（登录 + /api/**）与浏览器页面，不依赖 mydatama 源码、数据库与基础设施
- 内置固定种子演示数据生成器（独立副本），离线可生成
- TTS 断网自动等长静音兜底；实机截图失败自动以章节转场卡兜底
- 提供 Docker 镜像（Chromium + ffmpeg + Noto CJK）与独立 compose 工程
- 兼容平台版本：mydatama v0.1.0
