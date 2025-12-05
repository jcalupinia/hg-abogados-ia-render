# ---- Imagen base ----
FROM python:3.11-slim

# ---- Variables de entorno ----
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV PLAYWRIGHT_BROWSERS_PATH=/usr/local/share/playwright-browsers
ENV PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=0

# ---- Instalar dependencias mínimas del sistema ----
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget curl gnupg ca-certificates \
    libnss3 libatk1.0-0 libatk-bridge2.0-0 \
    libx11-6 libxcomposite1 libxdamage1 libxfixes3 \
    libpangocairo-1.0-0 libpango-1.0-0 libcairo2 \
    libxrandr2 libxkbcommon0 libasound2 libatspi2.0-0 \
    libxshmfence1 libgbm1 fonts-liberation \
    libcups2 tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

# ---- Directorio de trabajo ----
WORKDIR /app
COPY . /app

# ---- Evitar uso de proxy durante el build (pip) ----
ENV HTTP_PROXY="" \
    HTTPS_PROXY=""

# ---- Instalar dependencias Python ----
# Limpia proxies en el paso de build para que pip use la red directa
RUN unset HTTP_PROXY HTTPS_PROXY http_proxy https_proxy && \
    pip install --no-cache-dir -r requirements.txt

# ---- Instalar Playwright sin dependencias del sistema ----
RUN python -m playwright install chromium || true

# ---- Evitar que Playwright intente reinstalar navegadores en Render ----
ENV PLAYWRIGHT_SKIP_VALIDATE_HOST_REQUIREMENTS=true

# ---- Puerto de Render ----
EXPOSE 10000

# ---- Comando de ejecución ----
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-10000}"]
