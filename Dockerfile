# Используем официальный Python образ
FROM python:3.11-slim

# Устанавливаем рабочую директорию
WORKDIR /app

# Копируем зависимости и устанавливаем их
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем весь код в контейнер
COPY . .

# Экспонируем порт (тот, что Render использует)
ENV PORT=10000
EXPOSE 10000

# Команда запуска сервера
CMD ["gunicorn", "app:app", "-w", "1", "-b", "0.0.0.0:10000"]
