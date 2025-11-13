# ---- Imagen base ligera ----
FROM python:3.11-slim

# ---- Variables de entorno ----
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV PLAYWRIGHT_BROWSERS_PATH=/usr/local/share/playwright-browsers

# ---- Dependencias mínimas para Chromium ----
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget curl gnupg \
    libnss3 libatk1.0-0 libatk-bridge2.0-0 \
    libx11-6 libxcomposite1 libxdamage1 libxfixes3 \
    libpangocairo-1.0-0 libpango-1.0-0 libcairo2 \
    libxrandr2 libxkbcommon0 libasound2 libatspi2.0-0 \
    libxshmfence1 libgbm1 fonts-liberation \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# ---- Directorio de trabajo ----
WORKDIR /app
COPY . /app

# ---- Instalación de dependencias Python ----
RUN pip install --no-cache-dir -r requirements.txt

# ---- Instalar Playwright sin dependencias del sistema ----
RUN playwright install chromium

# ---- Puerto de Render ----
EXPOSE 10000

# ---- Comando de ejecución ----
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-10000}"]
