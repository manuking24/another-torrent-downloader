FROM python:3.8.10-slim

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

WORKDIR /app

COPY requirements.txt .
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

COPY . .
RUN mkdir -p /app/media /app/downloads /app/staticfiles
RUN python manage.py collectstatic --noinput

CMD ["celery", "-A", "torrent_downloader", "worker", "--loglevel=info"]
