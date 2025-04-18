FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    curl git unzip build-essential libpcap-dev \
    && rm -rf /var/lib/apt/lists/*

# Go install
ENV GO_VERSION=1.21.5
RUN curl -LO https://go.dev/dl/go${GO_VERSION}.linux-amd64.tar.gz && \
    tar -C /usr/local -xzf go${GO_VERSION}.linux-amd64.tar.gz && \
    ln -s /usr/local/go/bin/go /usr/bin/go

ENV PATH="/usr/local/go/bin:/root/go/bin:$PATH"
ENV GOPROXY=direct

# ProjectDiscoveryツールのインストール
RUN go install github.com/projectdiscovery/subfinder/v2/cmd/subfinder@latest && \
    go install github.com/projectdiscovery/httpx/cmd/httpx@latest && \
    go install github.com/projectdiscovery/dnsx/cmd/dnsx@latest && \
    go install github.com/projectdiscovery/naabu/v2/cmd/naabu@latest && \
    go install github.com/projectdiscovery/cdncheck/cmd/cdncheck@latest && \
    go install github.com/projectdiscovery/tlsx/cmd/tlsx@latest

# Install Flask
COPY requirements.txt /tmp/
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Copy app
WORKDIR /app
COPY app.py .

CMD ["python", "app.py"]
