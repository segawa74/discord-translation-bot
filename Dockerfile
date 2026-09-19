# 軽量なPythonイメージを使用
FROM python:3.11-slim

# ビルドツールおよび音声・暗号化に必要なライブラリをインストール
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    build-essential \
    python3-dev \
    ffmpeg \
    libopus0 \
    libsodium-dev && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ライブラリインストール
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ソースコードをコピー
COPY . .

# print出力を即時反映させるオプション付きで実行
CMD ["python", "-u", "main.py"]
