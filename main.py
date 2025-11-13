from fastapi import FastAPI, Request, HTTPException
import os
import traceback
import requests

# ===============================================================
# 🔌 Importar los conectores (proveedores)
# ===============================================================
try:
    from providers.fielweb_connector import consultar_fielweb
    from providers.judicial_connectors import consultar_jurisprudencia
except ModuleNotFoundError as e:
    consultar_fielweb = None
    consultar_jurisprudencia = None
    print(f"⚠️ Error al importar conectores: {e}")

# ===============================================================
# ⚙️ Configuración general del servicio
# ===============================================================
app = FastAPI(
    title="H&G Abogados IA - Robot Jurídico",
    description="Sistema jurídico automatizado que integra FielWeb y portales judiciales del Ecuador.",
    version="2.0"
)

API_KEY = os.getenv("X_API_KEY", "HYGABOGADOS-SECURE-2025")

# ===============================================================
# 🔐 Middleware de seguridad por API Key
# ===============================================================
@app.middleware("http")
async def verify_api_key(request: Request, call_next):
    """Verifica la API Key en cada solicitud HTTP."""
    allowed_paths = ["/", "/health", "/favicon.ico", "/check_fielweb_status"]
    if request.url.path in allowed_paths:
        return await call_next(request)

    key = request.headers.get("x-api-key") or request.headers.get("X-Api-Key")
    if key != API_KEY:
        raise HTTPException(status_code=401, detail="API Key inválida o ausente.")
    
    return await call_next(request)

# ===============================================================
# ✅ Endpoints básicos
# ===============================================================
@app.get("/")
async def root():
    return {"message": "Servicio activo: H&G Abogados IA", "status": "ok"}

@app.get("/health")
async def health():
    return {"status": "ok", "service": "H&G Abogados IA"}

# ===============================================================
# ⚖️ Consultas reales individuales
# ===============================================================
@app.post("/consult_real_fielweb")
async def consult_fielweb_endpoint(payload: dict):
    """
    Consulta el portal FielWeb (leyes, códigos, concordancias, jurisprudencia vinculada).
    """
    if not consultar_fielweb:
        raise HTTPException(status_code=500, detail="Conector FielWeb no disponible.")
    try:
        # Asíncrono si el conector lo soporta
        if callable(consultar_fielweb):
            return await consultar_fielweb(payload)
        else:
            raise HTTPException(status_code=500, detail="El conector FielWeb no es ejecutable.")
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
        if callable(consultar_jurisprudencia):
            return await consultar_jurisprudencia(payload)
        else:
            raise HTTPException(status_code=500, detail="El conector Jurisprudencial no es ejecutable.")
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error al consultar Jurisprudencia: {str(e)}")

# ===============================================================
# 🤖 Flujo híbrido (FielWeb + Jurisprudencia)
# ===============================================================
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
        resultado_fielweb = await consultar_fielweb(payload) if consultar_fielweb else None
        resultado_juris = await consultar_jurisprudencia(payload) if consultar_jurisprudencia else None

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

# ===============================================================
# 🧠 Diagnóstico de entorno y conexión
# ===============================================================
@app.get("/check_fielweb_status")
async def check_fielweb_status():
    """
    Verifica el estado del entorno, Playwright, credenciales y API key.
    """
    try:
        import playwright
        playwright_status = "✅ Instalado correctamente"
    except Exception as e:
        playwright_status = f"❌ Error Playwright: {str(e)}"

    user = os.getenv("FIELWEB_USERNAME")
    pwd = os.getenv("FIELWEB_PASSWORD")
    url = os.getenv("FIELWEB_LOGIN_URL")

    # Verificar conexión HTTP con FielWeb
    try:
        resp = requests.head(url, timeout=5)
        conexion = "✅ FielWeb accesible" if resp.status_code == 200 else f"⚠️ HTTP {resp.status_code}"
    except Exception as e:
        conexion = f"❌ Error conexión: {str(e)}"

    credenciales_ok = all([user, pwd, url])
    credenciales_status = "✅ Configuradas" if credenciales_ok else "❌ Faltan variables de entorno"

    return {
        "estado": "verificación completada",
        "playwright": playwright_status,
        "credenciales": credenciales_status,
        "usuario_detectado": user,
        "url_login": url,
        "conexion_fielweb": conexion,
        "api_key_configurada": "✅" if API_KEY else "❌ No definida"
    }

# ===============================================================
# 🚀 Endpoint de fallback (opcional)
# ===============================================================
@app.get("/{path_name}")
async def fallback(path_name: str):
    return {
        "status": "error",
        "mensaje": f"La ruta '/{path_name}' no existe o no está habilitada en este entorno."
    }
