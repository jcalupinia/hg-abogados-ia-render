from fastapi import FastAPI, Request, HTTPException
import os
import traceback

# ============================================
# 🔌 Importar los conectores (proveedores)
# ============================================
try:
    from providers.fielweb_connector import consultar_fielweb
    from providers.judicial_connectors import consultar_jurisprudencia
except ModuleNotFoundError as e:
    consultar_fielweb = None
    consultar_jurisprudencia = None
    print(f"⚠️ Error al importar conectores: {e}")

# ============================================
# ⚙️ Configuración general del servicio
# ============================================
app = FastAPI(title="H&G Abogados IA - Robot Jurídico")

API_KEY = os.getenv("X_API_KEY", "HYGABOGADOS-SECURE-2025")

# ============================================
# 🔐 Middleware de seguridad
# ============================================
@app.middleware("http")
async def verify_api_key(request: Request, call_next):
    # Permitir accesos sin autenticación a ciertas rutas
    if request.url.path in ["/", "/health", "/favicon.ico", "/check_fielweb_status"]:
        return await call_next(request)
    
    key = request.headers.get("X-API-Key")
    if key != API_KEY:
        raise HTTPException(status_code=401, detail="API Key inválida o ausente.")
    
    return await call_next(request)

# ============================================
# ✅ Endpoints básicos
# ============================================
@app.get("/")
async def root():
    return {"message": "Servicio activo: H&G Abogados IA"}

@app.get("/health")
async def health():
    return {"status": "ok", "service": "H&G Abogados IA"}

# ============================================
# ⚖️ Consultas reales individuales
# ============================================
@app.post("/consult_real_fielweb")
async def consult_fielweb_endpoint(payload: dict):
    """
    Consulta el portal FielWeb (leyes, códigos, concordancias, jurisprudencia vinculada).
    """
    if not consultar_fielweb:
        raise HTTPException(status_code=500, detail="Conector FielWeb no disponible.")
    try:
        return consultar_fielweb(payload)
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error al consultar FielWeb: {str(e)}")

@app.post("/consult_real_jurisprudencia")
async def consult_jurisprudencia_endpoint(payload: dict):
    """
    Consulta en los portales judiciales (SATJE, Corte Constitucional, Corte Nacional).
    """
    if not consultar_jurisprudencia:
        raise HTTPException(status_code=500, detail="Conector de Jurisprudencia no disponible.")
    try:
        return consultar_jurisprudencia(payload)
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error al consultar Jurisprudencia: {str(e)}")

# ============================================
# 🤖 Flujo híbrido (FielWeb + Jurisprudencia)
# ============================================
@app.post("/consult_hybrid")
async def consult_hybrid(payload: dict):
    """
    Ejecuta el flujo híbrido:
    1️⃣ Busca normas, reglamentos y concordancias en FielWeb.
    2️⃣ Si aplica, busca sentencias y jurisprudencia en fuentes judiciales.
    Devuelve los resultados combinados y clasificados.
    """
    texto = payload.get("texto", "")
    tipo = payload.get("tipo_usuario", "")

    try:
        resultado_fielweb = consultar_fielweb(payload) if consultar_fielweb else None
        resultado_juris = consultar_jurisprudencia(payload) if consultar_jurisprudencia else None

        # Clasificación jerárquica de resultados
        resultado_combinado = {
            "normativa_y_concordancias": resultado_fielweb.get("resultado") if resultado_fielweb else [],
            "jurisprudencia_y_sentencias": resultado_juris.get("resultado") if resultado_juris else []
        }

        return {
            "status": "ok",
            "mensaje": "Consulta híbrida completada con éxito",
            "texto_consultado": texto,
            "tipo_usuario": tipo,
            "fuentes_consultadas": {
                "FielWeb": bool(resultado_fielweb),
                "Jurisprudencia": bool(resultado_juris)
            },
            "resultado": resultado_combinado
        }

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error en consulta híbrida: {str(e)}")

# ============================================
# 🧠 Diagnóstico de entorno y conexión
# ============================================
@app.get("/check_fielweb_status")
async def check_fielweb_status():
    """
    Verifica el estado del entorno, Playwright, credenciales y API key.
    """
    try:
        import playwright
        from playwright.async_api import async_playwright
        playwright_status = "✅ Instalado correctamente"
    except Exception as e:
        playwright_status = f"❌ Error Playwright: {str(e)}"

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
        "api_key_configurada": "✅" if API_KEY else "❌ No definida"
    }
