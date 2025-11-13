# ==========================================================
# 🧠 H&G Abogados IA - Contenedor Optimizado para Render.com
# ----------------------------------------------------------
# Base: Python 3.11 Slim + Dependencias Chromium para Playwright
# ==========================================================

FROM python:3.11-slim

# =========================
# 🔧 Configuración inicial
# =========================
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

# =========================
# 🧩 Instalación de dependencias del sistema
# =========================
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget curl gnupg unzip fontconfig fonts-liberation libnss3 libatk1.0-0 \
    libatk-bridge2.0-0 libcups2 libdrm2 libxkbcommon0 libxcomposite1 \
    libxdamage1 libxfixes3 libxrandr2 libxss1 libxtst6 \
    libpango-1.0-0 libcairo2 libasound2 libxshmfence1 libgbm1 \
    libgtk-3-0 libx11-xcb1 ca-certificates \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# =========================
# 📂 Directorio de trabajo
# =========================
WORKDIR /app

# =========================
# 📦 Copiar archivos de la app
# =========================
COPY . /app

# =========================
# 🧰 Instalación de dependencias Python
# =========================
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# =========================
# 🌐 Instalación de navegadores Playwright
# =========================
RUN python -m playwright install chromium --with-deps

# =========================
# ⚙️ Variables de entorno
# =========================
ENV PLAYWRIGHT_BROWSERS_PATH=/usr/local/share/playwright-browsers
ENV PORT=10000

# =========================
# 🚀 Comando de ejecución
# =========================
EXPOSE 10000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "10000"]

