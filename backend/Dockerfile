FROM kalilinux/kali-rolling

RUN apt-get update && \
    apt-get install -y amass python3 python3-pip golang recon-ng nmap subfinder && \
    apt-get clean

WORKDIR /app
COPY . /app
RUN pip3 install --break-system-packages --no-cache-dir -r requirements.txt
RUN subfinder --version
CMD ["python3", "app.py"]

