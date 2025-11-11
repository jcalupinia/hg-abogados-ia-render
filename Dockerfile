# --------------------------------------------------------
# ⚖️ H&G ABOGADOS IA — DOCKERFILE FINAL PARA RENDER.COM
# Backend con FastAPI + Playwright + Chromium
# --------------------------------------------------------

FROM python:3.10-slim

# Evitar prompts y logs truncados
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# --------------------------------------------------------
# 🧠 Dependencias del sistema necesarias para Chromium
# --------------------------------------------------------
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget gnupg unzip curl fonts-liberation \
    libnss3 libxss1 libatk1.0-0 libatk-bridge2.0-0 libcups2 \
    libdrm2 libxkbcommon0 libxcomposite1 libxrandr2 libxdamage1 \
    libpango-1.0-0 libcairo2 libasound2 xvfb \
    gcc python3-dev libxml2-dev libxslt1-dev \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# --------------------------------------------------------
# 🧩 Instalar Playwright y Chromium
# --------------------------------------------------------
RUN pip install --upgrade pip setuptools wheel && \
    pip install --no-cache-dir playwright==1.47.0 && \
    python -m playwright install chromium && \
    chmod -R 777 /root/.cache/ms-playwright

# --------------------------------------------------------
# 📦 Instalar dependencias del proyecto
# --------------------------------------------------------
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# --------------------------------------------------------
# 📂 Copiar el resto del proyecto
# --------------------------------------------------------
COPY . .

# --------------------------------------------------------
# 🌍 Variables de entorno de Playwright
# --------------------------------------------------------
ENV PLAYWRIGHT_BROWSERS_PATH=/root/.cache/ms-playwright
ENV PYPPETEER_HOME=/root/.cache/ms-playwright

# --------------------------------------------------------
# 🚀 Exponer puerto y comando de inicio
# --------------------------------------------------------
EXPOSE 10000
CMD ["gunicorn", "-k", "uvicorn.workers.UvicornWorker", "main:app", "--bind", "0.0.0.0:10000", "--timeout", "120"]
