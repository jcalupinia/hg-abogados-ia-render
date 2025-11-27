# ======================================================
# H&G ABOGADOS IA - ROBOT JURÍDICO AUTOMATIZADO
# Compatible con Render.com + FastAPI + Playwright
# Versión estable 2025-11
# ======================================================

from fastapi import FastAPI, Request, HTTPException
import os, traceback, asyncio
import requests
from typing import Optional
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
API_KEY = os.getenv("X_API_KEY")
API_KEY_DISABLED = os.getenv("DISABLE_API_KEY", "false").lower() == "true"

# ============================================
# 🔐 Middleware de seguridad por API Key
# ============================================
@app.middleware("http")
async def verify_api_key(request: Request, call_next):
    allowed_routes = ["/", "/health", "/favicon.ico", "/check_fielweb_status"]
    if request.url.path in allowed_routes or API_KEY_DISABLED or not API_KEY:
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
def _ping_url(url: str, label: str) -> dict:
    """Prueba de conectividad HTTP simple con User-Agent de navegador."""
    headers = {"User-Agent": "Mozilla/5.0 (H&G Abogados IA)"}
    try:
        resp = requests.get(url, timeout=10, headers=headers, allow_redirects=True)
        return {
            "fuente": label,
            "url": url,
            "status": resp.status_code,
            "ok": 200 <= resp.status_code < 400,
            "final_url": str(resp.url)
        }
    except Exception as e:
        return {
            "fuente": label,
            "url": url,
            "status": None,
            "ok": False,
            "error": str(e)
        }

@app.get("/check_external_sources")
async def check_external_sources():
    """
    Verifica conectividad HTTP a las fuentes externas sin credenciales.
    Incluye FielWeb, portales judiciales y organismos oficiales.
    """
    fuentes = [
        ("fielweb", "FielWeb", os.getenv("FIELWEB_LOGIN_URL", "https://www.fielweb.com/Cuenta/Login.aspx")),
        ("satje", "SATJE", "https://www.funcionjudicial.gob.ec"),
        ("procesos_judiciales", "Procesos Judiciales (búsqueda)", "https://procesosjudiciales.funcionjudicial.gob.ec/busqueda"),
        ("corte_constitucional_portal", "Corte Constitucional (portal)", "https://www.corteconstitucional.gob.ec/"),
        ("corte_constitucional_relatoria", "Corte Constitucional (relatoría)", os.getenv("CORTE_CONSTITUCIONAL_URL", "https://portal.corteconstitucional.gob.ec/FichaRelatoria")),
        ("corte_nacional_portal", "Corte Nacional (portal)", "https://www.cortenacional.gob.ec/cnj/"),
        ("corte_nacional_relatoria", "Corte Nacional (ficha relatoría)", os.getenv("CORTE_NACIONAL_URL", "https://portalcortej.justicia.gob.ec/FichaRelatoria")),
        ("corte_nacional_nuevo", "Corte Nacional (buscador nuevo)", os.getenv("CORTE_NACIONAL_NUEVO_URL", "https://busquedasentencias.cortenacional.gob.ec/")),
        ("consejo_judicatura", "Consejo de la Judicatura", "https://www.funcionjudicial.gob.ec/"),
        ("tce", "Tribunal Contencioso Electoral", "https://www.tce.gob.ec/"),
        ("sri_home", "SRI (home)", "https://www.sri.gob.ec/web/intersri/home"),
        ("sri_principal", "SRI (principal)", "https://www.sri.gob.ec/"),
        ("trabajo", "Ministerio de Trabajo", "https://www.trabajo.gob.ec/"),
        ("supercias", "Superintendencia de Compañías", "https://www.supercias.gob.ec/portalscvs/index.htm"),
        ("senae", "SENAE", "https://www.aduana.gob.ec/")
    ]

    resultados = [{
        "id": fid,
        **_ping_url(url, label)
    } for fid, label, url in fuentes]
    return {
        "resumen": {
            "total": len(resultados),
            "ok": sum(1 for r in resultados if r.get("ok")),
            "fallidos": [r["fuente"] for r in resultados if not r.get("ok")]
        },
        "detalle": resultados
    }

@app.get("/check_corte_nacional_status")
async def check_corte_nacional_status():
    """Diagnóstico rápido de conectividad a los portales de la Corte Nacional (antiguo y nuevo)."""
    urls = {
        "corte_nacional_relatoria": os.getenv("CORTE_NACIONAL_URL", "https://portalcortej.justicia.gob.ec/FichaRelatoria"),
        "corte_nacional_nuevo": os.getenv("CORTE_NACIONAL_NUEVO_URL", "https://busquedasentencias.cortenacional.gob.ec/")
    }
    detalle = []
    for fid, url in urls.items():
        detalle.append({"id": fid, **_ping_url(url, fid)})
    return {
        "resumen": {
            "total": len(detalle),
            "ok": sum(1 for r in detalle if r.get("ok")),
            "fallidos": [r["fuente"] for r in detalle if not r.get("ok")]
        },
        "detalle": detalle
    }

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
