FROM python:3.8.10-slim
RUN apt-get update && apt-get install -y \
    build-essential \
    libboost-python-dev \
    libboost-system-dev \
    pkg-config \
    libtorrent-rasterbar-dev \
    python3-libtorrent \
    redis-tools \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

WORKDIR /app

COPY requirements.txt .
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

COPY . .

RUN mkdir -p /app/media /app/downloads /app/staticfiles
RUN python manage.py collectstatic --noinput
EXPOSE 8000
CMD ["daphne", "-b", "0.0.0.0", "-p", "8000", "torrent_downloader.asgi:application"]
