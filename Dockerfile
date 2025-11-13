# ========================================================
# 🧠 H&G Abogados IA - Dockerfile de despliegue en Render
# Compatible con FastAPI + Playwright + Chromium
# Última revisión: Noviembre 2025
# ========================================================

# ---- Imagen base ----
FROM python:3.11-slim

# ---- Variables de entorno globales ----
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV PYTHONIOENCODING=utf-8
ENV PLAYWRIGHT_BROWSERS_PATH=/usr/local/share/playwright-browsers
ENV PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=0

# ---- Instalación de dependencias del sistema ----
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget curl gnupg ca-certificates \
    libnss3 libatk1.0-0 libatk-bridge2.0-0 \
    libx11-6 libxcomposite1 libxdamage1 libxfixes3 \
    libpangocairo-1.0-0 libpango-1.0-0 libcairo2 \
    libxrandr2 libxkbcommon0 libasound2 libatspi2.0-0 \
    libxshmfence1 libgbm1 fonts-liberation \
    libcups2 libdrm2 libxext6 \
    && rm -rf /var/lib/apt/lists/*

# ---- Directorio de trabajo ----
WORKDIR /app
COPY . .

# ---- Instalación de dependencias Python ----
RUN pip install --no-cache-dir --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# ---- Instalación de Playwright con dependencias ----
RUN python -m playwright install --with-deps chromium

# ---- Evitar reinstalación de navegadores en cada arranque ----
ENV PLAYWRIGHT_SKIP_VALIDATE_HOST_REQUIREMENTS=true

# ---- Puerto expuesto ----
EXPOSE 10000

# ---- Comando de ejecución ----
# Render asigna un puerto dinámico ($PORT). Si no existe, usa 10000 por defecto.
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-10000}"]
