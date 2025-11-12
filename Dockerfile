# ==============================================
# 🧱 BASE IMAGE LIGERA CON FASTAPI
# ==============================================
FROM python:3.11-slim

# Evita prompts interactivos
ENV DEBIAN_FRONTEND=noninteractive

# ==============================================
# ⚙️ DEPENDENCIAS DEL SISTEMA (para Chromium y PDFs)
# ==============================================
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libffi-dev \
    libnss3 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    libxshmfence1 \
    libgtk-3-0 \
    libcairo2 \
    libcairo2-dev \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libjpeg62-turbo-dev \
    shared-mime-info \
    fonts-dejavu-core \
    fonts-liberation \
    wget \
    curl \
    ca-certificates \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# ==============================================
# 🧠 INSTALAR PLAYWRIGHT
# ==============================================
RUN pip install --upgrade pip setuptools wheel && \
    pip install --no-cache-dir playwright==1.47.0 && \
    playwright install chromium

# ==============================================
# 📦 CONFIGURACIÓN DEL PROYECTO
# ==============================================
WORKDIR /app
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app

# ==============================================
# 🌐 CONFIGURACIÓN DE SERVICIO
# ==============================================
EXPOSE 10000
ENV HEALTHCHECK_PATH=/healthz

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-10000}"]
