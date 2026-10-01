# mydatama-video 生成器镜像：Chromium（Playwright）+ ffmpeg + 中文字体
# 构建：docker build -t mydatama-video:0.1.0 .
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# 国内 Debian 源 + ffmpeg + 中文字体 + Chromium 运行依赖
RUN sed -i 's|deb.debian.org|mirrors.aliyun.com|g; s|security.debian.org|mirrors.aliyun.com|g' \
        /etc/apt/sources.list.d/debian.sources 2>/dev/null || true \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        ffmpeg fonts-noto-cjk fonts-noto-cjk-extra ca-certificates curl \
        libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \
        libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 \
        libgbm1 libpango-1.0-0 libcairo2 libasound2 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt \
    && PLAYWRIGHT_DOWNLOAD_HOST=https://cdn.npmmirror.com/binaries/playwright \
       python -m playwright install chromium

# 代码与素材
COPY src /app/src
COPY assets /app/assets

# 构建期生成演示 fixtures（固定种子、纯标准库、幂等），运行时无需 mydatama 仓库
RUN python /app/assets/fixtures/generator/generate_all.py || true

ENV PYTHONPATH=/app/src \
    OUTPUT_DIR=/app/output

VOLUME ["/app/output"]

# 通过 host.docker.internal 访问宿主机上的 mydatama 平台（compose 已配 host-gateway）
ENTRYPOINT ["python", "-m", "video_gen"]
CMD []
