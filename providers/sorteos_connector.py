import os
import json
import base64
import unicodedata
import requests
from typing import Any, Dict, List, Optional

BASE_URL = os.getenv("SORTEOS_BASE_URL", "https://esacc.corteconstitucional.gob.ec").rstrip("/")
DETALLE_BASE_URL = os.getenv("SORTEOS_DETALLE_BASE_URL", "https://buscador.corteconstitucional.gob.ec").rstrip("/")
SORTEOS_COOKIE = os.getenv("SORTEOS_COOKIE", "")


def _normalize_nombre(value: str) -> str:
    return unicodedata.normalize("NFD", value or "").encode("ascii", "ignore").decode("ascii").lower().strip()


def _load_jueces_map() -> Dict[str, str]:
    """
    Permite definir via env SORTEOS_JUECES_MAP un JSON del tipo {"Jhoel Marlin Escudero Soliz": "jhoel.escudero"}
    """
    raw = os.getenv("SORTEOS_JUECES_MAP")
    mapping: Dict[str, str] = {}
    if not raw:
        return mapping
    try:
        data = json.loads(raw)
        for nombre, usuario in (data or {}).items():
            if nombre and usuario:
                mapping[_normalize_nombre(nombre)] = usuario
    except Exception:
        pass
    return mapping


JUECES_USUARIOS = _load_jueces_map()


def _b64_payload(data: Dict[str, Any]) -> str:
    return base64.b64encode(json.dumps(data).encode("utf-8")).decode("utf-8")


def _session(base: str, referer_suffix: str = "/buscadorsorteos/buscador") -> requests.Session:
    s = requests.Session()
    s.headers.update(
        {
            "User-Agent": "Mozilla/5.0 (H&G Abogados IA)",
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json; charset=UTF-8",
            "Origin": base,
            "Referer": f"{base}{referer_suffix}",
        }
    )
    if SORTEOS_COOKIE:
        s.headers["Cookie"] = SORTEOS_COOKIE
    return s


def buscar_sorteos(payload: Dict[str, Any]) -> Dict[str, Any]:
    fecha_desde = payload.get("fecha_desde") or payload.get("fechaDesde")
    fecha_hasta = payload.get("fecha_hasta") or payload.get("fechaHasta")
    numero_causa = payload.get("numero_causa") or payload.get("numeroCausa") or ""
    despacho_id = payload.get("despacho_id") or payload.get("id") or None
    resorteado = payload.get("resorteado") if "resorteado" in payload else None
    usuario_sorteado = payload.get("usuario_sorteado") or payload.get("usuarioSorteado")
    nombre_juez = payload.get("nombre_juez") or payload.get("juez") or payload.get("nombreJuez")

    if not fecha_desde or not fecha_hasta:
        return {"error": "Debe enviar fecha_desde y fecha_hasta"}

    resolved_usuario = _resolve_usuario_sorteado(usuario_sorteado, nombre_juez)
    if resolved_usuario:
        body = {
            "usuarioSorteado": resolved_usuario,
            "fechaInicio": _to_iso(fecha_desde),
            "fechaFin": _to_iso(fecha_hasta),
        }
    else:
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
    causa_id = payload.get("causa_id") or payload.get("id") or payload.get("causaId")
    numero_causa = payload.get("numero_causa") or payload.get("numeroCausa") or ""
    incluir_docs = payload.get("documentos") or payload.get("anexos") or payload.get("incluir_documentos")

    if not causa_id and not numero_causa:
        return {"error": "Debe proporcionar causa_id o numero_causa"}

    ficha_body = {"numero": numero_causa} if numero_causa and not causa_id else {
        "nemeroCausa": numero_causa,
        "idCausa": causa_id,
        "uid": "",
        "contexto": "CAUUA",
    }

    referer = f"/buscador-externo/causa/ficha?contexto=CAUSA&uuid=&numero={numero_causa}" if numero_causa else "/buscador-externo/causa/ficha?contexto=CAUSA"
    sess = _session(DETALLE_BASE_URL, referer_suffix=referer)

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
        if not causa_id:
            ficha = result.get("ficha") or {}
            causa_dto = ficha.get("causaDTO") or ficha.get("causa") or {}
            causa_id = causa_dto.get("id") or ficha.get("idCausa")

        if incluir_docs:
            try:
                # El front usa 100_EXPEDNTE_DCMTO (sin la "I") con dato base64 {"id": <idCausa>}
                doc_payload = {"id": causa_id} if causa_id else {"numero": numero_causa}
                doc_url = f"{DETALLE_BASE_URL}/buscador-externo/rest/api/expedienteDocumento/100_EXPEDNTE_DCMTO"
                doc_resp = sess.post(
                    doc_url,
                    json={"dato": _b64_payload(doc_payload)},
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
            except requests.RequestException as dre:
                msg = f"{getattr(dre.response, 'status_code', '')} {getattr(dre.response, 'text', '')}"
                result.setdefault("incidencias", []).append(f"Documentos no disponibles: {msg}")
            except Exception as doc_e:
                result.setdefault("incidencias", []).append(f"Documentos no disponibles: {doc_e}")

        return result
    except requests.RequestException as re:
        msg = re.response.text if re.response is not None else str(re)
        return {"error": f"Error al obtener detalle de expediente: {msg}"}
    except Exception as e:
        return {"error": f"Error al obtener detalle de expediente: {e}"}


def consultar_sorteos(payload: Dict[str, Any]) -> Dict[str, Any]:
    if payload.get("detalle") or payload.get("causa_id") or payload.get("numero_causa"):
        return detalle_expediente(payload)
    return buscar_sorteos(payload)


def _resolve_usuario_sorteado(usuario: Optional[str], nombre_juez: Optional[str]) -> Optional[str]:
    if usuario:
        return usuario.strip()
    if not nombre_juez:
        return None
    nombre_norm = _normalize_nombre(nombre_juez)
    if nombre_norm in JUECES_USUARIOS:
        return JUECES_USUARIOS[nombre_norm]
    parts = [p for p in nombre_norm.split() if p]
    if len(parts) >= 2:
        return f"{parts[0]}.{parts[-1]}"
    return None


def _to_iso(fecha: str) -> str:
    if not fecha:
        return ""
    if "T" in fecha:
        return fecha
    return f"{fecha}T00:00:00.000Z"
