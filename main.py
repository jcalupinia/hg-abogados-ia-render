# ======================================================
# H&G ABOGADOS IA - ROBOT JURÍDICO AUTOMATIZADO
# Compatible con Render.com + FastAPI + Playwright
# Version estable 2025-11
# ======================================================

from fastapi import FastAPI, Request, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field
import os, traceback, asyncio
import requests
from typing import Optional, Dict, Any, List
import base64
import json
import hmac
import hashlib
import time
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
    from providers.fielweb_connector import consultar_fielweb, descargar_norma_archivo
    from providers.judicial_connectors import (
        consultar_jurisprudencia,
        consultar_corte_nacional,
        consultar_procesos_judiciales,
        consultar_procesos_avanzada,
        consultar_procesos_resueltos,
        consultar_juriscopio,
        consultar_spdp,
        exportar_pdf_satje,
    )
    from providers.supercias_connectors import consultar_supercias_companias
    from providers.uafe_connector import consultar_uafe
    from providers.sorteos_connector import consultar_sorteos
    print("Conectores cargados correctamente.")
except ModuleNotFoundError as e:
    consultar_fielweb = None
    descargar_norma_archivo = None
    consultar_jurisprudencia = None
    consultar_corte_nacional = None
    consultar_procesos_judiciales = None
    consultar_procesos_avanzada = None
    consultar_procesos_resueltos = None
    consultar_juriscopio = None
    consultar_spdp = None
    exportar_pdf_satje = None
    consultar_supercias_companias = None
    consultar_uafe = None
    consultar_sorteos = None
    print(f"Error al importar conectores: {e}")

# ============================================
# Inicializacion del servicio FastAPI
# ============================================
app = FastAPI(title="H&G Abogados IA - Robot Juri­dico Inteligente")
DOWNLOAD_TOKEN_SECRET = os.getenv("DOWNLOAD_TOKEN_SECRET", "").strip()


class ConsultarFielwebRequest(BaseModel):
    texto: str = Field(..., description="Termino de busqueda.")
    seccion: Optional[int] = Field(1, description="Seccion (1 vigente, 2 historica, etc).")
    reformas: Optional[str] = Field("2", description="Pestana de reformas (\"2\" = Todo).")
    page: Optional[int] = Field(1, description="Pagina de resultados.")
    limite_resultados: Optional[int] = Field(None, description="Limita la cantidad de resultados devueltos.")
    descargar_pdf: Optional[bool] = Field(False, description="Si es true intenta adjuntar pdf_base64 de RO.")
    descargas: Optional[bool] = Field(False, description="Incluye rutas y links de descarga por formato.")
    norma_id: Optional[int] = Field(None, description="Solicita el detalle puntual de una norma.")
    parte_d: Optional[int] = Field(None, description="Indice inicial del bloque de articulos cuando se consulta norma_id.")
    parte_h: Optional[int] = Field(None, description="Indice final del bloque de articulos cuando se consulta norma_id.")
    # Alias utiles para compatibilidad con el conector
    consulta: Optional[str] = Field(None, description="Alias de texto.")
    max_resultados: Optional[int] = Field(None, description="Alias de limite_resultados.")
    limit: Optional[int] = Field(None, description="Alias de limite_resultados.")

    class Config:
        extra = "allow"
        allow_population_by_field_name = True

# ============================================
# Helpers para enlaces de descarga firmados (FielWeb)
# ============================================
def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def _sign_download_payload(payload: Dict[str, Any], secret: str) -> str:
    body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    sig = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"{_b64url_encode(body)}.{sig}"


def _verify_download_token(token: str, secret: str) -> Dict[str, Any]:
    try:
        body_b64, sig = token.rsplit(".", 1)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Token de descarga invalido.") from exc
    body = _b64url_decode(body_b64)
    expected = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        raise HTTPException(status_code=401, detail="Token de descarga invalido.")
    payload = json.loads(body.decode("utf-8"))
    exp = payload.get("exp")
    if exp and time.time() > float(exp):
        raise HTTPException(status_code=401, detail="Token de descarga expirado.")
    return payload

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
async def consult_fielweb_endpoint(payload: ConsultarFielwebRequest):
    if not consultar_fielweb:
        raise HTTPException(status_code=500, detail="Conector FielWeb no disponible.")
    try:
        try:
            payload_dict = payload.model_dump(exclude_none=True)
        except AttributeError:
            payload_dict = payload.dict(exclude_none=True)
        return await run_in_threadpool(consultar_fielweb, payload_dict)
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error FielWeb: {str(e)}")


@app.post("/fielweb/download_link")
async def fielweb_download_link(payload: dict, request: Request):
    norma_id = payload.get("norma_id")
    if norma_id is None:
        raise HTTPException(status_code=400, detail="Debe proporcionar 'norma_id'.")
    try:
        norma_id_int = int(norma_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="norma_id invalido.") from exc

    formato = (payload.get("formato") or "pdf").lower()
    if formato not in ("pdf", "word", "html"):
        raise HTTPException(status_code=400, detail="formato debe ser pdf, word o html.")

    concordancias = bool(payload.get("concordancias") or False)
    ttl_seconds = int(payload.get("ttl_seconds") or 600)
    secret = DOWNLOAD_TOKEN_SECRET
    if not secret:
        raise HTTPException(status_code=500, detail="DOWNLOAD_TOKEN_SECRET no configurado.")

    exp = int(time.time()) + ttl_seconds
    token_payload = {
        "norma_id": norma_id_int,
        "formato": formato,
        "concordancias": concordancias,
        "exp": exp,
    }
    token = _sign_download_payload(token_payload, secret)
    base_url = str(request.base_url).rstrip("/")
    return {
        "download_url": f"{base_url}/fielweb/download?token={token}",
        "exp": exp,
    }


@app.get("/fielweb/download")
async def fielweb_download(token: str):
    if not descargar_norma_archivo:
        raise HTTPException(status_code=500, detail="Conector FielWeb no disponible.")
    secret = DOWNLOAD_TOKEN_SECRET
    if not secret:
        raise HTTPException(status_code=500, detail="DOWNLOAD_TOKEN_SECRET no configurado.")
    payload = _verify_download_token(token, secret)

    norma_id = payload.get("norma_id")
    formato = payload.get("formato") or "pdf"
    concordancias = bool(payload.get("concordancias") or False)

    try:
        result = await run_in_threadpool(
            descargar_norma_archivo,
            int(norma_id),
            formato,
            concordancias,
            None,
        )
    except Exception as exc:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error FielWeb descarga: {exc}") from exc
    if not result:
        raise HTTPException(status_code=502, detail="No se pudo descargar el archivo.")
    if result.get("error"):
        raise HTTPException(status_code=502, detail=result["error"])

    content_type = result.get("content_type")
    if not content_type:
        if formato == "pdf":
            content_type = "application/pdf"
        elif formato == "word":
            content_type = "application/msword"
        else:
            content_type = "text/html; charset=utf-8"

    filename = result.get("filename") or f"norma_{norma_id}.{formato}"
    headers = {"Content-Disposition": f'inline; filename="{filename}"'}
    return Response(content=result["content_bytes"], media_type=content_type, headers=headers)

# ============================================
# Exportar PDF SATJE (procesos judiciales)
# ============================================
@app.post("/satje/export_pdf_link")
async def satje_export_pdf_link(payload: dict, request: Request):
    id_juicio = payload.get("id_juicio") or payload.get("idJuicio") or payload.get("numero_causa")
    if not id_juicio:
        raise HTTPException(status_code=400, detail="Debe proporcionar id_juicio o numero_causa.")

    try:
        max_actuaciones = int(payload.get("max_actuaciones") or 200)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="max_actuaciones invalido.") from exc
    if max_actuaciones < 1:
        max_actuaciones = 1

    ttl_seconds = int(payload.get("ttl_seconds") or 600)
    secret = DOWNLOAD_TOKEN_SECRET
    if not secret:
        raise HTTPException(status_code=500, detail="DOWNLOAD_TOKEN_SECRET no configurado.")

    exp = int(time.time()) + ttl_seconds
    token_payload = {
        "id_juicio": str(id_juicio),
        "max_actuaciones": max_actuaciones,
        "exp": exp,
    }
    # Campos opcionales para obtener actuaciones completas
    for key in (
        "idMovimientoJuicioIncidente",
        "idIncidenteJudicatura",
        "idJudicatura",
        "incidente",
        "nombreJudicatura",
    ):
        if payload.get(key) is not None:
            token_payload[key] = payload.get(key)
    token = _sign_download_payload(token_payload, secret)
    base_url = str(request.base_url).rstrip("/")
    return {
        "download_url": f"{base_url}/satje/export_pdf?token={token}",
        "exp": exp,
    }


@app.get("/satje/export_pdf")
async def satje_export_pdf(token: str):
    if not exportar_pdf_satje:
        raise HTTPException(status_code=500, detail="Conector SATJE no disponible.")
    secret = DOWNLOAD_TOKEN_SECRET
    if not secret:
        raise HTTPException(status_code=500, detail="DOWNLOAD_TOKEN_SECRET no configurado.")
    payload = _verify_download_token(token, secret)

    try:
        result = await run_in_threadpool(exportar_pdf_satje, payload)
    except Exception as exc:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error SATJE PDF: {exc}") from exc
    if not result:
        raise HTTPException(status_code=502, detail="No se pudo generar el PDF.")
    if result.get("error"):
        raise HTTPException(status_code=502, detail=result["error"])

    content = result.get("content") or b""
    filename = result.get("filename") or "satje_export.pdf"
    headers = {"Content-Disposition": f'inline; filename=\"{filename}\"'}
    return Response(content=content, media_type="application/pdf", headers=headers)

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
# Consulta SPDP
# ============================================
@app.post("/consult_spdp")
async def consult_spdp_endpoint(payload: dict):
    if not consultar_spdp:
        return JSONResponse(
            content={"error": "Conector SPDP no disponible."},
            status_code=200
        )
    try:
        return JSONResponse(content=consultar_spdp(payload), status_code=200)
    except Exception as e:
        traceback.print_exc()
        return JSONResponse(
            content={"error": f"Error SPDP: {str(e)}"},
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
        "debug_mode": os.getenv("DEBUG", "false"),
    }

# ============================================
# Ejecucion local o Render
# ============================================
if __name__ == "__main__":
    port = int(os.getenv("PORT", 10000))
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=port)


