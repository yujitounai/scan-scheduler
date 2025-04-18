# ベースイメージ
FROM python:3.10-slim

# 環境変数
ENV PYTHONUNBUFFERED=1

# 作業ディレクトリを作成
WORKDIR /app

# 依存関係のインストール
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# アプリケーションコードをコピー
COPY . .

# ポートを公開
EXPOSE 3333

# アプリケーション起動
CMD ["python", "app.py"]
