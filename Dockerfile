FROM python:3.11-slim

# ffmpeg обязателен для смешивания
RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

# создадим папку для результатов
RUN mkdir -p static/out

# Render пробрасывает HTTP-трафик в контейнер на порт $PORT; подхватим его в запуске
EXPOSE 8000
ENV PYTHONUNBUFFERED=1

# если $PORT есть (Render), используем его; иначе по умолчанию 8000 (локально)
CMD ["sh","-c","uvicorn app:app --host 0.0.0.0 --port ${PORT:-8000}"]
