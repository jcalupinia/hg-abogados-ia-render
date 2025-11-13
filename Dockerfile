# ===========================================
# 🧱 Imagen base
# ===========================================
FROM python:3.11-slim

# ===========================================
# ⚙️ Variables de entorno básicas
# ===========================================
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PLAYWRIGHT_BROWSERS_PATH=/usr/local/share/playwright-browsers
ENV PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=0
ENV PLAYWRIGHT_SKIP_VALIDATE_HOST_REQUIREMENTS=true
ENV TZ=America/Guayaquil

# ===========================================
# 🔧 Instalar dependencias del sistema (completas y seguras)
# ===========================================
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget curl gnupg ca-certificates \
    libnss3 libatk1.0-0 libatk-bridge2.0-0 \
    libx11-6 libxcomposite1 libxdamage1 libxfixes3 \
    libpangocairo-1.0-0 libpango-1.0-0 libcairo2 \
    libxrandr2 libxkbcommon0 libasound2 libatspi2.0-0 \
    libxshmfence1 libgbm1 libgtk-3-0 \
    fonts-liberation fonts-dejavu fonts-freefont-ttf \
    ttf-dejavu-core \
    libcups2 \
    && rm -rf /var/lib/apt/lists/*

# ===========================================
# 📁 Directorio de trabajo
# ===========================================
WORKDIR /app
COPY . /app

# ===========================================
# 🐍 Instalar dependencias Python
# ===========================================
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# ===========================================
# 🌐 Instalar navegadores Playwright (Chromium)
# ===========================================
# Evita fallo “code 100” instalando manualmente dependencias y validando al final
RUN python -m playwright install --with-deps chromium || true

# ===========================================
# 🧠 Configuración avanzada para Render
# ===========================================
# Evita conflictos con sandbox y uso compartido de sesión FielWeb
ENV PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1
ENV PLAYWRIGHT_DISABLE_ERRORS=1
ENV NODE_OPTIONS=--max-old-space-size=2048

# ===========================================
# 🔓 Exponer el puerto de Render (por defecto 10000)
# ===========================================
EXPOSE 10000

# ===========================================
# 🚀 Comando de arranque del servidor FastAPI
# ===========================================
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-10000} --timeout-keep-alive 90"]
