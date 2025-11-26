# ======================================================
# H&G ABOGADOS IA - ROBOT JURÍDICO AUTOMATIZADO
# Compatible con Render.com + FastAPI + Playwright
# Versión estable 2025-11
# ======================================================

from fastapi import FastAPI, Request, HTTPException
import os, traceback, asyncio
import uvloop
import nest_asyncio

# ============================================
# ⚙️ Compatibilidad con entorno Render (modo sandbox)
# ============================================
try:
    import nest_asyncio
    nest_asyncio.apply()
    import uvloop
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    print("✅ Modo Render seguro activado (nest_asyncio + uvloop)")
except Exception as e:
    print(f"⚠️ No se aplicó uvloop/nest_asyncio: {e}")

# ============================================
# 🔌 Importación de conectores
# ============================================
try:
    from providers.fielweb_connector import consultar_fielweb
    from providers.judicial_connectors import consultar_jurisprudencia
    print("✅ Conectores cargados correctamente.")
except ModuleNotFoundError as e:
    consultar_fielweb = None
    consultar_jurisprudencia = None
    print(f"⚠️ Error al importar conectores: {e}")

# ============================================
# 🚀 Inicialización del servicio FastAPI
# ============================================
app = FastAPI(title="H&G Abogados IA - Robot Jurídico Inteligente")
API_KEY = os.getenv("X_API_KEY", "HYGABOGADOS-SECURE-2025")
API_KEY_DISABLED = os.getenv("DISABLE_API_KEY", "false").lower() == "true"

# ============================================
# 🔐 Middleware de seguridad por API Key
# ============================================
@app.middleware("http")
async def verify_api_key(request: Request, call_next):
    allowed_routes = ["/", "/health", "/favicon.ico", "/check_fielweb_status"]
    if request.url.path in allowed_routes:
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
# ⚖️ Consultas FielWeb
# ============================================
@app.post("/consult_real_fielweb")
async def consult_fielweb_endpoint(payload: dict):
    if not consultar_fielweb:
        raise HTTPException(status_code=500, detail="Conector FielWeb no disponible.")
    try:
        return consultar_fielweb(payload)
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error FielWeb: {str(e)}")

# ============================================
# ⚖️ Consultas Jurisprudenciales
# ============================================
@app.post("/consult_real_jurisprudencia")
async def consult_jurisprudencia_endpoint(payload: dict):
    if not consultar_jurisprudencia:
        raise HTTPException(status_code=500, detail="Conector de Jurisprudencia no disponible.")
    try:
        return consultar_jurisprudencia(payload)
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error Jurisprudencia: {str(e)}")

# ============================================
# 🤖 Flujo Híbrido (Normativa + Jurisprudencia)
# ============================================
@app.post("/consult_hybrid")
async def consult_hybrid(payload: dict):
    texto = payload.get("texto", "")
    tipo = payload.get("tipo_usuario", "")

    try:
        resultado_fielweb = consultar_fielweb(payload) if consultar_fielweb else None
        resultado_juris = consultar_jurisprudencia(payload) if consultar_jurisprudencia else None

        combinado = {
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
            "resultado": combinado
        }

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error híbrido: {str(e)}")

# ============================================
# 🧠 Diagnóstico de entorno
# ============================================
@app.get("/check_fielweb_status")
async def check_fielweb_status():
    """
    🔍 Verifica la configuración completa del entorno FielWeb y Render.
    Muestra estado de Playwright, variables de entorno, loop y autenticación.
    """
    import sys
    import platform
    from providers import check_providers_status

    # --- Comprobación básica del entorno ---
    loop_type = str(type(asyncio.get_running_loop()))
    render_mode = "Render (uvloop seguro)" if "uvloop" in loop_type else "Local / VSCode"

    # --- Estado de los conectores ---
    try:
        provider_status = check_providers_status()
    except Exception as e:
        provider_status = {"error": f"No se pudo obtener estado de providers: {str(e)}"}

    # --- Verificar instalación de Playwright ---
    try:
        import playwright
        playwright_status = "✅ Instalado correctamente"
    except Exception as e:
        playwright_status = f"❌ No disponible ({str(e)})"

    # --- Verificar credenciales FielWeb ---
    user = os.getenv("FIELWEB_USERNAME")
    pwd = os.getenv("FIELWEB_PASSWORD")
    url = os.getenv("FIELWEB_LOGIN_URL")
    credenciales_ok = all([user, pwd, url])
    credenciales_estado = "✅ Configuradas" if credenciales_ok else "⚠️ Incompletas"

    # --- Test rápido de acceso a la URL de FielWeb ---
    import requests
    try:
        resp = requests.get(url, timeout=8)
        if resp.status_code == 200:
            conexion_estado = "✅ Acceso correcto a FielWeb"
        elif resp.status_code == 403:
            conexion_estado = "⚠️ Bloqueo 403 (IP o sesión restringida)"
        else:
            conexion_estado = f"⚠️ Respuesta inesperada HTTP {resp.status_code}"
    except Exception as e:
        conexion_estado = f"❌ Error de conexión: {str(e)}"

    # --- Resumen de entorno ---
    return {
        "estado": "verificación completada",
        "entorno": render_mode,
        "python_version": sys.version.split()[0],
        "so": platform.system(),
        "playwright": playwright_status,
        "credenciales": credenciales_estado,
        "usuario_detectado": user,
        "url_login": url,
        "conexion_fielweb": conexion_estado,
        "providers": provider_status,
        "api_key_configurada": "✅" if os.getenv("X_API_KEY") else "❌ No definida",
        "debug_mode": os.getenv("DEBUG", "false"),
    }

# ============================================
# 🧩 Ejecución local o Render
# ============================================
if __name__ == "__main__":
    port = int(os.getenv("PORT", 10000))
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=port)
