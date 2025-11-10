from fastapi import FastAPI, Request, HTTPException
import os
import traceback

# Importar conectores (asegúrate de tener los archivos en /providers/)
try:
    from providers.fielweb_connector import consultar_fielweb
    from providers.judicial_connectors import consultar_jurisprudencia
except ModuleNotFoundError as e:
    consultar_fielweb = None
    consultar_jurisprudencia = None
    print(f"⚠️ Error al importar conectores: {e}")

app = FastAPI(title="H&G Abogados IA - Robot Jurídico")

# -------------------------------
# 🔐 CONFIGURACIÓN DE SEGURIDAD
# -------------------------------
API_KEY = os.getenv("X_API_KEY", "HYGABOGADOS-SECURE-2025")

@app.middleware("http")
async def verify_api_key(request: Request, call_next):
    # Excepciones sin autenticación
    if request.url.path in ["/", "/health", "/favicon.ico", "/check_fielweb_status"]:
        return await call_next(request)
    
    key = request.headers.get("X-API-Key")
    if key != API_KEY:
        raise HTTPException(status_code=401, detail="API Key inválida o ausente.")
    
    return await call_next(request)

# -------------------------------
# ✅ ENDPOINTS BÁSICOS
# -------------------------------
@app.get("/")
async def root():
    return {"message": "Servicio activo: H&G Abogados IA"}

@app.get("/health")
async def health():
    return {"status": "ok", "service": "H&G Abogados IA"}

# -------------------------------
# ⚙️ CONSULTAS REALES
# -------------------------------
@app.post("/consult_real_fielweb")
async def consult_fielweb_endpoint(payload: dict):
    if not consultar_fielweb:
        raise HTTPException(status_code=500, detail="Conector FielWeb no disponible.")
    try:
        return consultar_fielweb(payload)
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error al consultar FielWeb: {str(e)}")

@app.post("/consult_real_jurisprudencia")
async def consult_jurisprudencia_endpoint(payload: dict):
    if not consultar_jurisprudencia:
        raise HTTPException(status_code=500, detail="Conector de Jurisprudencia no disponible.")
    try:
        return consultar_jurisprudencia(payload)
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error al consultar Jurisprudencia: {str(e)}")

@app.post("/consult_hybrid")
async def consult_hybrid(payload: dict):
    texto = payload.get("texto", "")
    tipo = payload.get("tipo_usuario", "")
    try:
        resultado = None
        if consultar_fielweb:
            resultado = consultar_fielweb(payload)
        if not resultado and consultar_jurisprudencia:
            resultado = consultar_jurisprudencia(payload)
        return {
            "status": "ok",
            "mensaje": "Consulta híbrida ejecutada correctamente.",
            "texto": texto,
            "tipo_usuario": tipo,
            "resultado": resultado,
        }
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error en consulta híbrida: {str(e)}")

# -------------------------------
# 🧠 VERIFICADOR AUTOMÁTICO FIELWEB
# -------------------------------
@app.get("/check_fielweb_status")
async def check_fielweb_status():
    try:
        import playwright
        from playwright.async_api import async_playwright
        playwright_status = "✅ Instalado correctamente"
    except Exception as e:
        playwright_status = f"❌ Error Playwright: {str(e)}"

    # Verificar credenciales desde variables de entorno
    user = os.getenv("FIELWEB_USERNAME")
    pwd = os.getenv("FIELWEB_PASSWORD")
    url = os.getenv("FIELWEB_LOGIN_URL")

    credenciales_ok = all([user, pwd, url])
    credenciales_status = "✅ Configuradas" if credenciales_ok else "❌ Faltan variables de entorno"

    return {
        "estado": "verificación completada",
        "playwright": playwright_status,
        "credenciales": credenciales_status,
        "usuario_detectado": user,
        "url_login": url,
        "api_key_configurada": "✅" if API_KEY else "❌ No definida",
    }
