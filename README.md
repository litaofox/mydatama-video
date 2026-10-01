# mydatama-video — 讲解视频全自动生成器

一条命令把 **mydatama 数据中台** 的项目讲解视频（约 18 分钟，1080p，中文配音 + 中文字幕 + 代码高亮 + 实机功能演示）自动渲染成 MP4，**全程无需人工操作**。

> 这是一个**完全独立的项目**：独立 Git 仓库、独立依赖与配置、独立容器镜像与发布节奏。
> 它是 mydatama 平台的黑盒客户端，**只通过 `http://平台地址` 访问系统，不包含、不引用、不共享 mydatama 的任何源码、数据库或基础设施**。

---

## 1. 项目边界（重要）

| 维度 | 本项目 | 说明 |
|---|---|---|
| 代码库 | 独立 Git 仓库，无 submodule / 软链引用 | mydatama 仅作为外部被测系统 |
| 数据 | 不连 PostgreSQL；自带固定种子 fixtures | 生成器副本独立维护，与 mydatama/samples 无文件级共享 |
| 运行时 | 独立 venv 或独立 Docker 镜像 | 不加入 mydatama compose 网络，不挂载其数据卷 |
| 配置 | 自己的 `.env` | 唯一输入是 `BASE_URL` 与演示账号 |
| 版本 | 独立 semver（v0.1.0） | 见下方兼容矩阵 |

**唯一耦合点**：平台公开 HTTP 契约（`/api/auth/login`、`/api/processing/*`、`/api/dataset/*`、`/api/product/*`、`/api/governance/*`）与前端页面路由。DOM 选择器相关逻辑集中在 [browser.py](src/video_gen/browser.py)，页面改版只需改这一处。

### 兼容矩阵

| 生成器版本 | 验证通过的平台版本 |
|---|---|
| 0.1.x | mydatama **v0.1.0** |

---

## 2. 它是怎么做到"无人值守"的

```
分镜旁白稿 (assets/narration/分镜脚本与旁白.md)
   │  edge-tts 神经语音（断网自动等长静音兜底）
   ├─► 每镜一段 MP3（ffprobe 自动测时长 → 音画天然同步）
slides.html（26 页章节卡/架构图/代码高亮）
   │  Playwright 无头 Chromium 按 #页码 截图
   ├─► 幻灯片镜 1~23、31~32 的 PNG
平台 15 步动线（src/video_gen/scenario.py）
   │  公开 API 自动：登录→上传 5 万行→轮询五阶段→修复→多模态→
   │  资产/血缘→数据集 v1/v2→产品生成→合规四绿→密级倒挂反面→登记挂牌→审计
   ├─► 实机镜 24~30 的真实页面截图
ffmpeg：逐镜图+音合成 → 拼接 → 烧录自动生成的 SRT → H.264/AAC MP4
```

输出：`output/mydatama-v0.1-讲解视频-1080p.mp4` 与 `output/work/subtitles.srt`。

---

## 3. 方式 A：本地运行（约 10 分钟准备）

前置：Python 3.11+、ffmpeg（`winget install Gyan.FFmpeg`）、Windows 可访问外网（edge-tts）。

```powershell
cd mydatama-video
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m playwright install chromium

copy .env.example .env          # 按需改 BASE_URL

# 先确保 mydatama 平台已在运行（建议指向独立的 8091 测试实例）
python -m video_gen --dry-run   # ① 校验素材与剧本（不联网）
python -m video_gen             # ② 全自动出片
```

平台建议用独立测试实例，避免演示数据污染开发库（在 mydatama 目录执行一次）：

```powershell
$env:COMPOSE_PROJECT_NAME="mydatama-stage"; $env:PORTAL_PORT="8091"
docker compose up -d            # 然后把本项目 .env 的 BASE_URL 改为 http://localhost:8091
```

其他开关：

```powershell
python -m video_gen --slides-only   # 不连平台：只渲染章节/架构/代码幻灯片（第五章用转场卡）
python -m video_gen --no-burn       # 不烧硬字幕，只外挂生成 SRT
```

## 4. 方式 B：Docker 一条命令（本机零安装）

```bash
docker compose --profile video run --rm builder
# 成片在 ./output/ ；容器通过 host.docker.internal 访问宿主上的平台
```

镜像内已含 Chromium、ffmpeg、Noto Sans CJK 中文字体，并在构建期生成 fixtures。

---

## 5. 目录结构

```
mydatama-video/
├── src/video_gen/         # 生成器
│   ├── platform_api.py    # 唯一耦合点：平台公开 HTTP 契约
│   ├── scenario.py        # 15 步演示动线（自动造数）
│   ├── browser.py         # Playwright 仅负责按路由截图
│   ├── tts.py             # edge-tts + 静音兜底
│   ├── ffmpeg_utils.py    # 逐镜合成/拼接/烧字幕
│   ├── subtitles.py       # 按实际音频时长自动切 SRT
│   └── pipeline.py        # 总编排
├── assets/
│   ├── slides.html        # 章节卡/架构图/代码高亮（本地化 hljs，可离线）
│   ├── narration/         # 分镜旁白稿（字幕与配音的唯一文案源）+ 手工版 SRT 参考
│   └── fixtures/generator/# 独立复制的固定种子演示数据生成器
├── Dockerfile / docker-compose.yml
└── output/                # gitignore；成片与中间产物
```

## 6. 修改视频内容

- 改旁白/字幕/时长：只改 `assets/narration/分镜脚本与旁白.md`（编号 `镜 N` 与引用块），重新运行即可——字幕按实际音频重新切分；
- 改章节卡/架构图/代码片段：改 `assets/slides.html`（每页对应分镜编号）；
- 改演示动作或适应平台新版：改 `scenario.py`（造数）与 `browser.py`（页面路由）。

## 7. 常见问题

| 现象 | 处理 |
|---|---|
| edge-tts 报错 | 自动静音兜底，仍出片（无真人声）；联网后重跑即可恢复配音 |
| 某镜实机截图失败 | 自动用第五章转场卡兜底，流水线不中断；日志会打印失败路由 |
| 平台连不上 | 确认 `BASE_URL`、容器内用 `host.docker.internal:8090`、平台容器 healthy |
| 字幕方块字 | 本地缺中文字体；Docker 镜像已内置 Noto CJK，本地安装任意中文字体即可 |
| 反面演示为什么主要亮 R1 | v0.1.0 平台 MASK 阶段处置过的敏感列必带脱敏策略（R2 恒绿），故以"密级倒挂"稳定触发 R1 拦阻 |
