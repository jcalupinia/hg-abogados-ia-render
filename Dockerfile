# ---- Imagen base ligera ----
FROM python:3.11-slim

# ---- Variables de entorno ----
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV PLAYWRIGHT_BROWSERS_PATH=/usr/local/share/playwright-browsers

# ---- Dependencias del sistema necesarias para Chromium/Playwright ----
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl wget gnupg apt-transport-https lsb-release \
    fonts-liberation \
    libasound2 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdbus-1-3 libdrm2 \
    libgbm1 libgtk-3-0 libnspr4 libnss3 \
    libx11-6 libx11-xcb1 libxcb1 libxcomposite1 libxcursor1 libxdamage1 \
    libxext6 libxfixes3 libxi6 libxrandr2 libxss1 libxtst6 \
    && rm -rf /var/lib/apt/lists/*

# ---- Directorio de trabajo ----
WORKDIR /app

# Copiar solo requirements para aprovechar la cache de Docker
COPY requirements.txt /app/

# ---- Instalación de dependencias Python ----
RUN python -m pip install --upgrade pip setuptools wheel \
    && pip install --no-cache-dir -r requirements.txt

# Copiar el resto del código
COPY . /app

# ---- Instalar navegadores de Playwright (usa el módulo Python instalado) ----
RUN python -m playwright install chromium

# ---- Puerto de Render ----
EXPOSE 10000

# ---- Comando de ejecución ----
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-10000}"]
