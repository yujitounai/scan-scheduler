FROM projectdiscovery/nuclei:latest

# Python3 + venv を使う準備
RUN apk add --no-cache python3 py3-pip

# アプリ配置
WORKDIR /app
COPY app.py /app/

# 仮想環境の作成とパッケージのインストール
RUN python3 -m venv venv && \
    ./venv/bin/pip install --upgrade pip && \
    ./venv/bin/pip install flask flask_cors

# nuclei-templates をマウントして使いたい場合は run 時に -v で指定する

EXPOSE 5557

# アプリを仮想環境の Python で起動
CMD ["./venv/bin/python", "app.py"]
