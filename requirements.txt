FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV PLAYWRIGHT_BROWSERS_PATH=/usr/local/share/playwright-browsers

RUN apt-get update && apt-get install -y \
    wget curl gnupg \
    libnss3 libatk1.0-0 libatk-bridge2.0-0 \
    libx11-6 libxcomposite1 libxdamage1 libxfixes3 \
    libpangocairo-1.0-0 libpango-1.0-0 libcairo2 \
    libxrandr2 libxkbcommon0 libasound2 libatspi2.0-0 \
    libxshmfence1 libgbm1 fonts-liberation \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . /app

RUN pip install --no-cache-dir -r requirements.txt
RUN playwright install chromium

EXPOSE 10000

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-10000}"]
