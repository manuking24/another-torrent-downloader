FROM python:3.8.10-slim

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

WORKDIR /app

COPY requirements.txt .
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

COPY . .

RUN mkdir -p /app/media /app/downloads /app/staticfiles
RUN chmod -R 755 /app
RUN python manage.py collectstatic --noinput
EXPOSE 8000
CMD ["daphne", "-b", "0.0.0.0", "-p", "8000", "torrent_downloader.asgi:application"]
