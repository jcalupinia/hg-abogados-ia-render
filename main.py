# ======================================================
# H&G ABOGADOS IA - ROBOT JURÍDICO AUTOMATIZADO
# Compatible con Render.com + FastAPI + Playwright
# Version estable 2025-11
# ======================================================

from fastapi import FastAPI, Request, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
import os, traceback, asyncio
import requests
from typing import Optional, Dict, Any, List
import uvloop
import nest_asyncio

# ============================================
# Compatibilidad con entorno Render (modo sandbox)
# ============================================
try:
    import nest_asyncio
    nest_asyncio.apply()
    import uvloop
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    print("âœ… Modo Render seguro activado (nest_asyncio + uvloop)")
except Exception as e:
    print(f"âš ï¸ No se aplicÃ³ uvloop/nest_asyncio: {e}")

# ============================================
# Importacion de conectores
# ============================================
try:
    from providers.fielweb_connector import consultar_fielweb
    from providers.judicial_connectors import (
        consultar_jurisprudencia,
        consultar_corte_nacional,
        consultar_procesos_judiciales,
        consultar_procesos_avanzada,
        consultar_procesos_resueltos,
        consultar_juriscopio,
    )
    from providers.supercias_connectors import consultar_supercias_companias
    from providers.uafe_connector import consultar_uafe
    from providers.sorteos_connector import consultar_sorteos
    print("Conectores cargados correctamente.")
except ModuleNotFoundError as e:
    consultar_fielweb = None
    consultar_jurisprudencia = None
    consultar_corte_nacional = None
    consultar_procesos_judiciales = None
    consultar_procesos_avanzada = None
    consultar_procesos_resueltos = None
    consultar_juriscopio = None
    consultar_supercias_companias = None
    consultar_uafe = None
    consultar_sorteos = None
    print(f"Error al importar conectores: {e}")

# ============================================
# Inicializacion del servicio FastAPI
# ============================================
app = FastAPI(title="H&G Abogados IA - Robot Juri­dico Inteligente")
API_KEY = os.getenv("X_API_KEY")
API_KEY_DISABLED = os.getenv("DISABLE_API_KEY", "false").lower() == "true"

# ============================================
# Middleware de seguridad por API Key
# ============================================
@app.middleware("http")
async def verify_api_key(request: Request, call_next):
    allowed_routes = [
        "/",
        "/health",
        "/favicon.ico",
        "/check_fielweb_status",
        "/check_external_sources",
        "/check_corte_nacional_status",
        "/check_corte_constitucional_status",
        "/check_uafe_status",
    ]
    if request.url.path in allowed_routes or API_KEY_DISABLED or not API_KEY:
        return await call_next(request)

    key = request.headers.get("X-API-Key")
    if key != API_KEY:
        raise HTTPException(status_code=401, detail="API Key invÃ¡lida o ausente.")
    return await call_next(request)

# ============================================
# Endpoints basicos
# ============================================
@app.get("/")
async def root():
    return {"message": "Servicio activo: H&G Abogados IA"}

@app.get("/health")
async def health():
    return {"status": "ok", "service": "H&G Abogados IA"}

# ============================================
# Consultas FielWeb
# ============================================
@app.post("/consult_real_fielweb")
async def consult_fielweb_endpoint(payload: dict):
    if not consultar_fielweb:
        raise HTTPException(status_code=500, detail="Conector FielWeb no disponible.")
    try:
        return await run_in_threadpool(consultar_fielweb, payload)
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error FielWeb: {str(e)}")

# ============================================
# Consultas Jurisprudenciales
# ============================================
@app.post("/consult_real_jurisprudencia")
async def consult_jurisprudencia_endpoint(payload: dict):
    if not consultar_jurisprudencia:
        raise HTTPException(status_code=500, detail="Conector de Jurisprudencia no disponible.")
    try:
        return await run_in_threadpool(consultar_jurisprudencia, payload)
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error Jurisprudencia: {str(e)}")

# ============================================
# Consulta individual Corte Nacional (nuevo buscador)
# ============================================
@app.post("/consult_corte_nacional")
async def consult_corte_nacional_endpoint(payload: dict):
    if not consultar_corte_nacional:
        raise HTTPException(status_code=500, detail="Conector Corte Nacional no disponible.")
    try:
        return await run_in_threadpool(consultar_corte_nacional, payload)
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error Corte Nacional: {str(e)}")

# ============================================
# Consulta individual Procesos Judiciales (E-SATJE)
# ============================================
@app.post("/consult_procesos_judiciales")
async def consult_procesos_judiciales_endpoint(payload: dict):
    if not consultar_procesos_judiciales:
        raise HTTPException(status_code=500, detail="Conector Procesos Judiciales no disponible.")
    try:
        return await run_in_threadpool(consultar_procesos_judiciales, payload)
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error Procesos Judiciales: {str(e)}")

# ============================================
# Consulta Procesos Judiciales - Búsqueda avanzada (API)
# ============================================
@app.post("/consult_procesos_avanzada")
async def consult_procesos_avanzada_endpoint(payload: dict):
    if not consultar_procesos_avanzada:
        raise HTTPException(status_code=500, detail="Conector Procesos Judiciales (avanzada) no disponible.")
    try:
        return await run_in_threadpool(consultar_procesos_avanzada, payload)
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error Procesos Judiciales (avanzada): {str(e)}")

# ============================================
# Consulta Procesos resueltos por juez
# ============================================
@app.post("/consult_procesos_resueltos")
async def consult_procesos_resueltos_endpoint(payload: dict):
    if not consultar_procesos_resueltos:
        raise HTTPException(status_code=500, detail="Conector Procesos resueltos no disponible.")
    try:
        return await run_in_threadpool(consultar_procesos_resueltos, payload)
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error Procesos resueltos: {str(e)}")

# ============================================
# Consulta Superintendencia de Compañias (compañias)
# ============================================
@app.post("/consult_supercias_companias")
async def consult_supercias_companias_endpoint(payload: dict):
    if not consultar_supercias_companias:
        raise HTTPException(status_code=500, detail="Conector Supercias no disponible.")
    try:
        return await run_in_threadpool(consultar_supercias_companias, payload)
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error Supercias: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error Procesos Judiciales: {str(e)}")

# ============================================
# Consulta Juriscopio
# ============================================
@app.post("/consult_juriscopio")
async def consult_juriscopio_endpoint(payload: dict):
    if not consultar_juriscopio:
        raise HTTPException(status_code=500, detail="Conector Juriscopio no disponible.")
    try:
        return await run_in_threadpool(consultar_juriscopio, payload)
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error Juriscopio: {str(e)}")

# Buscador de Sorteos (Corte Constitucional)
@app.post("/consult_sorteos")
async def consult_sorteos_endpoint(payload: dict):
    if not consultar_sorteos:
        raise HTTPException(status_code=500, detail="Conector Sorteos no disponible.")
    try:
        return await run_in_threadpool(consultar_sorteos, payload)
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error Sorteos: {str(e)}")

# Consulta UAFE (sujetos obligados)
# ============================================
@app.post("/consult_real_uafe")
async def consult_uafe_endpoint(payload: dict):
    if not consultar_uafe:
        return JSONResponse(
            content={"error": "Conector UAFE no disponible."},
            status_code=200
        )
    try:
        return JSONResponse(content=consultar_uafe(payload), status_code=200)
    except Exception as e:
        traceback.print_exc()
        return JSONResponse(
            content={"error": f"Error UAFE: {str(e)}"},
            status_code=200
        )

# ============================================
# Flujo Hibrido (Normativa + Jurisprudencia)
# ============================================
@app.post("/consult_hybrid")
async def consult_hybrid(payload: dict):
    texto = payload.get("texto", "")
    tipo = payload.get("tipo_usuario", "")

    try:
        resultado_fielweb = await run_in_threadpool(consultar_fielweb, payload) if consultar_fielweb else None
        resultado_juris = await run_in_threadpool(consultar_jurisprudencia, payload) if consultar_jurisprudencia else None

        combinado = {
            "normativa_y_concordancias": resultado_fielweb.get("resultado") if resultado_fielweb else [],
            "jurisprudencia_y_sentencias": resultado_juris.get("resultado") if resultado_juris else []
        }

        return {
            "status": "ok",
            "mensaje": "Consulta hÃ­brida completada con Ã©xito",
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
        raise HTTPException(status_code=500, detail=f"Error hÃ­brido: {str(e)}")

# ============================================
# Pre-busqueda global (resumen por fuente)
# ============================================
def _min_fielweb_item(item: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "titulo": item.get("titulo"),
        "numero": item.get("numero"),
        "fecha_publicacion": item.get("fecha_publicacion"),
        "fuente": "FielWeb",
        "norma_id": item.get("norma_id"),
        "seccion": item.get("seccion"),
    }


def _min_generic_item(item: Dict[str, Any], fuente: str) -> Dict[str, Any]:
    return {
        "titulo": item.get("titulo") or item.get("numero_sentencia") or item.get("numero_caso") or item.get("numero_proceso"),
        "numero": item.get("numero_sentencia") or item.get("numero_caso") or item.get("numero_proceso"),
        "fecha": item.get("fecha"),
        "fuente": fuente,
        "id": item.get("id") or item.get("id_causa"),
    }


@app.post("/consult_global")
async def consult_global(payload: dict):
    texto = (payload.get("texto") or payload.get("consulta") or payload.get("query") or "").strip()
    if not texto:
        raise HTTPException(status_code=400, detail="Debe proporcionar 'texto' para la pre-busqueda global.")

    limit = int(payload.get("limit_por_fuente") or 3)
    secciones_fielweb = payload.get("secciones_fielweb") or [1, 4]
    fuentes = payload.get("usar_fuentes") or [
        "fielweb",
        "juriscopio",
        "corte_nacional",
        "jurisprudencia",
        "uafe",
    ]
    fuentes = [f.lower() for f in fuentes]

    resultado: Dict[str, Any] = {"texto": texto, "fuentes": {}}

    # FielWeb (secciones 1 y 4 por defecto)
    if "fielweb" in fuentes and consultar_fielweb:
        fw_items: List[Dict[str, Any]] = []
        for sec in secciones_fielweb:
            try:
                fw_payload = {
                    "texto": texto,
                    "seccion": sec,
                    "reformas": "2",
                    "page": 1,
                    "descargar_pdf": False,
                    "descargas": False,
                }
                resp = await run_in_threadpool(consultar_fielweb, fw_payload)
                items = resp.get("resultado") or []
                for it in items[:limit]:
                    it["seccion"] = sec
                    fw_items.append(_min_fielweb_item(it))
            except Exception as e:
                fw_items.append({"error": str(e), "seccion": sec})
        resultado["fuentes"]["fielweb"] = fw_items[: max(1, limit * len(secciones_fielweb))]

    # Juriscopio (casos + sentencias por texto)
    if "juriscopio" in fuentes and consultar_juriscopio:
        try:
            casos_payload = {
                "seccion": "sentencias_causas",
                "ambito": "caso",
                "tipo_busqueda": "texto_caso",
                "texto": texto,
                "page": 1,
                "size": limit,
            }
            sent_payload = {
                "seccion": "sentencias_causas",
                "ambito": "sentencia",
                "tipo_busqueda": "texto_sentencia",
                "texto": texto,
                "page": 1,
                "size": limit,
            }
            casos = await run_in_threadpool(consultar_juriscopio, casos_payload)
            sent = await run_in_threadpool(consultar_juriscopio, sent_payload)
            resultado["fuentes"]["juriscopio_casos"] = [_min_generic_item(i, "Juriscopio - Casos") for i in (casos.get("resultado") or [])[:limit]]
            resultado["fuentes"]["juriscopio_sentencias"] = [_min_generic_item(i, "Juriscopio - Sentencias") for i in (sent.get("resultado") or [])[:limit]]
        except Exception as e:
            resultado["fuentes"]["juriscopio"] = [{"error": str(e)}]

    # Corte Nacional
    if "corte_nacional" in fuentes and consultar_corte_nacional:
        try:
            cn_payload = {"texto": texto, "tipo_busqueda": "aproximada"}
            cn = await run_in_threadpool(consultar_corte_nacional, cn_payload)
            resultado["fuentes"]["corte_nacional"] = [_min_generic_item(i, "Corte Nacional") for i in (cn.get("resultado") or [])[:limit]]
        except Exception as e:
            resultado["fuentes"]["corte_nacional"] = [{"error": str(e)}]

    # Jurisprudencia general
    if "jurisprudencia" in fuentes and consultar_jurisprudencia:
        try:
            j_payload = {"texto": texto}
            jr = await run_in_threadpool(consultar_jurisprudencia, j_payload)
            resultado["fuentes"]["jurisprudencia"] = [_min_generic_item(i, "Jurisprudencia") for i in (jr.get("resultado") or [])[:limit]]
        except Exception as e:
            resultado["fuentes"]["jurisprudencia"] = [{"error": str(e)}]

    # UAFE
    if "uafe" in fuentes and consultar_uafe:
        try:
            uafe_payload = {"texto": texto}
            uf = consultar_uafe(uafe_payload)
            resultado["fuentes"]["uafe"] = (uf.get("resultado") or [])[:limit]
        except Exception as e:
            resultado["fuentes"]["uafe"] = [{"error": str(e)}]

    return {
        "mensaje": "Pre-busqueda global completada",
        "texto": texto,
        "fuentes": resultado["fuentes"],
    }

# ============================================
# Diagnostico de entorno
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
        ("procesos_judiciales", "Procesos Judiciales (bÃºsqueda)", "https://procesosjudiciales.funcionjudicial.gob.ec/busqueda"),
        ("corte_constitucional_portal", "Corte Constitucional (portal)", "https://www.corteconstitucional.gob.ec/"),
        ("corte_constitucional_relatoria", "Corte Constitucional (relatorÃ­a)", os.getenv("CORTE_CONSTITUCIONAL_URL", "https://portal.corteconstitucional.gob.ec/FichaRelatoria")),
        ("corte_nacional_portal", "Corte Nacional (portal)", "https://www.cortenacional.gob.ec/cnj/"),
        ("corte_nacional_relatoria", "Corte Nacional (ficha relatorÃ­a)", os.getenv("CORTE_NACIONAL_URL", "https://portalcortej.justicia.gob.ec/FichaRelatoria")),
        ("corte_nacional_nuevo", "Corte Nacional (buscador nuevo)", os.getenv("CORTE_NACIONAL_NUEVO_URL", "https://busquedasentencias.cortenacional.gob.ec/")),
        ("consejo_judicatura", "Consejo de la Judicatura", "https://www.funcionjudicial.gob.ec/"),
        ("tce", "Tribunal Contencioso Electoral", "https://www.tce.gob.ec/"),
        ("sri_home", "SRI (home)", "https://www.sri.gob.ec/web/intersri/home"),
        ("sri_principal", "SRI (principal)", "https://www.sri.gob.ec/"),
        ("trabajo", "Ministerio de Trabajo", "https://www.trabajo.gob.ec/"),
        ("supercias", "Superintendencia de CompaÃ±Ã­as", "https://www.supercias.gob.ec/portalscvs/index.htm"),
        ("senae", "SENAE", "https://www.aduana.gob.ec/"),
        ("uafe", "UAFE", os.getenv("UAFE_URL", "https://www.uafe.gob.ec/resoluciones-sujetos-obligados/"))
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
    """DiagnÃ³stico rÃ¡pido de conectividad a los portales de la Corte Nacional (antiguo y nuevo)."""
    try:
        urls = {
            "corte_nacional": os.getenv("CORTE_NACIONAL_URL", "https://busquedasentencias.cortenacional.gob.ec/")
        }
        detalle = []
        for fid, url in urls.items():
            detalle.append({"id": fid, **_ping_url(url, fid)})
        payload = {
            "resumen": {
                "total": len(detalle),
                "ok": sum(1 for r in detalle if r.get("ok")),
                "fallidos": [r["fuente"] for r in detalle if not r.get("ok")]
            },
            "detalle": detalle
        }
        return JSONResponse(content=payload, status_code=200)
    except Exception as e:
        return JSONResponse(
            content={"error": f"Fallo interno al verificar Corte Nacional: {e}"},
            status_code=200
        )

@app.get("/check_corte_constitucional_status")
async def check_corte_constitucional_status():
    """DiagnÃ³stico rÃ¡pido de conectividad al buscador de la Corte Constitucional."""
    try:
        url = os.getenv("CORTE_CONSTITUCIONAL_URL", "http://buscador.corteconstitucional.gob.ec/buscador-externo/principal")
        detalle = [{"id": "corte_constitucional", **_ping_url(url, "Corte Constitucional")}]
        payload = {
            "resumen": {
                "total": len(detalle),
                "ok": sum(1 for r in detalle if r.get("ok")),
                "fallidos": [r["fuente"] for r in detalle if not r.get("ok")]
            },
            "detalle": detalle
        }
        return JSONResponse(content=payload, status_code=200)
    except Exception as e:
        return JSONResponse(
            content={"error": f"Fallo interno al verificar Corte Constitucional: {e}"},
            status_code=200
        )

@app.get("/check_uafe_status")
async def check_uafe_status():
    """Diagnostico rapido de conectividad al portal de UAFE (resoluciones)."""
    try:
        url = os.getenv("UAFE_URL", "https://www.uafe.gob.ec/resoluciones-sujetos-obligados/")
        detalle = [{"id": "uafe", **_ping_url(url, "UAFE")}]
        payload = {
            "resumen": {
                "total": len(detalle),
                "ok": sum(1 for r in detalle if r.get("ok")),
                "fallidos": [r["fuente"] for r in detalle if not r.get("ok")]
            },
            "detalle": detalle
        }
        return JSONResponse(content=payload, status_code=200)
    except Exception as e:
        return JSONResponse(
            content={"error": f"Fallo interno al verificar UAFE: {e}"},
            status_code=200
        )

@app.get("/check_fielweb_status")
async def check_fielweb_status():
    """
    Verifica la configuracion completa del entorno FielWeb y Render.
    Muestra estado de Playwright, variables de entorno, loop y autenticaciÃ³n.
    """
    import sys
    import platform
    from providers import check_providers_status

    # --- ComprobaciÃ³n bÃ¡sica del entorno ---
    loop_type = str(type(asyncio.get_running_loop()))
    render_mode = "Render (uvloop seguro)" if "uvloop" in loop_type else "Local / VSCode"

    # --- Estado de los conectores ---
    try:
        provider_status = check_providers_status()
    except Exception as e:
        provider_status = {"error": f"No se pudo obtener estado de providers: {str(e)}"}

    # --- Verificar instalaciÃ³n de Playwright ---
    try:
        import playwright
        playwright_status = "âœ… Instalado correctamente"
    except Exception as e:
        playwright_status = f"âŒ No disponible ({str(e)})"

    # --- Verificar credenciales FielWeb ---
    user = os.getenv("FIELWEB_USERNAME")
    pwd = os.getenv("FIELWEB_PASSWORD")
    url = os.getenv("FIELWEB_LOGIN_URL")
    credenciales_ok = all([user, pwd, url])
    credenciales_estado = "Configuradas" if credenciales_ok else "Incompletas"

    # --- Test rÃ¡pido de acceso a la URL de FielWeb ---
    import requests
    try:
        resp = requests.get(url, timeout=8)
        if resp.status_code == 200:
            conexion_estado = "Acceso correcto a FielWeb"
        elif resp.status_code == 403:
            conexion_estado = "Bloqueo 403 (IP o sesion restringida)"
        else:
            conexion_estado = f"Respuesta inesperada HTTP {resp.status_code}"
    except Exception as e:
        conexion_estado = f"Error de conexion: {str(e)}"

    # --- Resumen de entorno ---
    return {
        "estado": "verificacion completada",
        "entorno": render_mode,
        "python_version": sys.version.split()[0],
        "so": platform.system(),
        "playwright": playwright_status,
        "credenciales": credenciales_estado,
        "usuario_detectado": user,
        "url_login": url,
        "conexion_fielweb": conexion_estado,
        "providers": provider_status,
        "api_key_configurada": "…" if os.getenv("X_API_KEY") else "No definida",
        "debug_mode": os.getenv("DEBUG", "false"),
    }

# ============================================
# Ejecucion local o Render
# ============================================
if __name__ == "__main__":
    port = int(os.getenv("PORT", 10000))
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=port)


