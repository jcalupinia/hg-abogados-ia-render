import os
import json
import base64
import requests
from typing import Any, Dict, Optional, List


BASE_URL = os.getenv("SORTEOS_BASE_URL", "https://esacc.corteconstitucional.gob.ec").rstrip("/")
DETALLE_BASE_URL = os.getenv("SORTEOS_DETALLE_BASE_URL", "https://buscador.corteconstitucional.gob.ec").rstrip("/")


def _b64_payload(data: Dict[str, Any]) -> str:
    return base64.b64encode(json.dumps(data).encode("utf-8")).decode("utf-8")


def _session(base: str) -> requests.Session:
    s = requests.Session()
    s.headers.update(
        {
            "User-Agent": "Mozilla/5.0 (H&G Abogados IA)",
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json; charset=UTF-8",
            "Origin": base,
            "Referer": f"{base}/buscadorsorteos/buscador",
        }
    )
    return s


def buscar_sorteos(payload: Dict[str, Any]) -> Dict[str, Any]:
    fecha_desde = payload.get("fecha_desde") or payload.get("fechaDesde")
    fecha_hasta = payload.get("fecha_hasta") or payload.get("fechaHasta")
    numero_causa = payload.get("numero_causa") or payload.get("numeroCausa") or ""
    despacho_id = payload.get("despacho_id") or payload.get("id") or None
    resorteado = payload.get("resorteado") if "resorteado" in payload else None

    if not fecha_desde or not fecha_hasta:
        return {"error": "Debe enviar fecha_desde y fecha_hasta"}

    body = {
        "id": despacho_id,
        "fechaDesde": fecha_desde,
        "fechaHasta": fecha_hasta,
        "numeroCausa": numero_causa,
        "contexto": "CAUSA",
        "resorteado": resorteado,
    }

    sess = _session(BASE_URL)
    try:
        resp = sess.post(
            f"{BASE_URL}/esacc/rest/api/buscadorSorteo/obtenerPorJuezFecha",
            json={"dato": _b64_payload(body)},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        resultados = data.get("dato") or []
        mapped = []
        for r in resultados:
            mapped.append(
                {
                    "causa_id": r.get("causa", {}).get("id"),
                    "numero_causa": r.get("numeroCausa") or r.get("causa", {}).get("numero"),
                    "ponente": r.get("ponente"),
                    "fecha_asignacion": r.get("fechaIngreso"),
                    "tipo_sorteo": r.get("tipoSorteo"),
                }
            )
        return {
            "mensaje": data.get("mensaje"),
            "total": data.get("totalFilas"),
            "resultado": mapped,
        }
    except Exception as e:
        return {"error": f"Error al buscar sorteos: {e}"}


def _map_doc(doc: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": doc.get("id"),
        "nombre": doc.get("nombreDocumento") or doc.get("nombre"),
        "carpeta": doc.get("carpeta"),
        "uuid": doc.get("uuid"),
        "uuidDocumento": doc.get("uuidDocumento"),
        "fecha_carga": doc.get("fechaCarga"),
        "repositorio": doc.get("repositorio"),
        "url": doc.get("uuid") or doc.get("uuidDocumento"),
    }


def detalle_expediente(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Requiere causa_id (id num�rico del resultado) y opcional numero_causa.
    Devuelve la ficha de la causa y, si se solicita, los documentos/anexos.
    """
    causa_id = payload.get("causa_id") or payload.get("id") or payload.get("causaId")
    numero_causa = payload.get("numero_causa") or payload.get("numeroCausa") or ""
    incluir_docs = payload.get("documentos") or payload.get("anexos") or payload.get("incluir_documentos")

    if not causa_id:
        return {"error": "Debe proporcionar causa_id"}

    ficha_body = {
        "numeroCausa": numero_causa,
        "idCausa": causa_id,
        "uid": "",
        "contexto": "CAUSA",
    }

    sess = _session(DETALLE_BASE_URL)
    try:
        ficha_resp = sess.post(
            f"{DETALLE_BASE_URL}/buscador-causa-juridico/rest/api/causa/obtenerFicha",
            json={"dato": _b64_payload(ficha_body)},
            timeout=30,
        )
        ficha_resp.raise_for_status()
        ficha_data = ficha_resp.json()
        result: Dict[str, Any] = {
            "mensaje": ficha_data.get("mensaje"),
            "ficha": ficha_data.get("dato"),
        }

        # Si el cliente solicita documentos, intentar obtenerlos.
        if incluir_docs:
            try:
                doc_resp = sess.post(
                    f"{DETALLE_BASE_URL}/buscador-causa-juridico/rest/api/expedienteDocumento/100_EXPEDIENTE_DCMTO",
                    json={"dato": _b64_payload({"id": causa_id})},
                    timeout=30,
                )
                doc_resp.raise_for_status()
                doc_data = doc_resp.json()
                items = doc_data.get("dato") or []
                documentos: List[Dict[str, Any]] = []
                anexos: List[Dict[str, Any]] = []
                for doc in items:
                    documentos.append(_map_doc(doc))
                    for an in doc.get("anexos") or []:
                        anexos.append(_map_doc(an))
                result["documentos"] = documentos
                result["anexos"] = anexos
            except Exception:
                # No fallar toda la llamada por documentos
                result.setdefault("incidencias", []).append("No se pudieron obtener documentos")

        return result
    except Exception as e:
        return {"error": f"Error al obtener detalle de expediente: {e}"}


def consultar_sorteos(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Si el payload incluye 'detalle' o 'causa_id', devuelve detalle de la causa.
    De lo contrario, realiza la b�squeda principal.
    """
    if payload.get("detalle") or payload.get("causa_id"):
        return detalle_expediente(payload)
    return buscar_sorteos(payload)
