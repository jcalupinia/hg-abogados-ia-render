"""
Conector HTTP para FielWeb Plus (sin Playwright).

Flujo:
1) POST /Cuenta/login.aspx/signin      -> establece cookies de sesión
2) POST /Cuenta/login.aspx/aceptoTerminosCondiciones
3) POST /Cuenta/login.aspx/traerUsuario -> obtiene token (tk)
4) POST /app/tpl/buscador/busquedas.aspx/buscar -> resultados

Para cada resultado se devuelven los campos visibles en la tarjeta y, si existe,
se arma una URL de previsualización del Registro Oficial (RO) usando los datos
de `registroOficialImagen.Url`. La descarga PDF se realiza en el front con
`/app/tpl/visualizador/visualizador.aspx/generarPDF`; se deja expuesto el
endpoint para usos posteriores.
"""

import os
import base64
import requests
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, parse_qs

FIELWEB_BASE = os.getenv("FIELWEB_BASE_URL", "https://www.fielweb.com").rstrip("/")
FIELWEB_LOGIN_URL = os.getenv("FIELWEB_LOGIN_URL", f"{FIELWEB_BASE}/Cuenta/Login.aspx")
FIELWEB_USERNAME = os.getenv("FIELWEB_USERNAME", "").strip()
FIELWEB_PASSWORD = os.getenv("FIELWEB_PASSWORD", "").strip()

DEFAULT_REFORMAS = "2"  # pestaña "Todo" en el front
DEFAULT_SECCION = 1     # s=1 observado en búsquedas
DEFAULT_PAGE = 1


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update(
        {
            "User-Agent": "Mozilla/5.0 (H&G Abogados IA)",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Content-Type": "application/json; charset=UTF-8",
            "Origin": FIELWEB_BASE,
            "Referer": FIELWEB_LOGIN_URL,
            "X-Requested-With": "XMLHttpRequest",
        }
    )
    return s


def _post_json(sess: requests.Session, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    url = path if path.startswith("http") else urljoin(FIELWEB_BASE, path)
    resp = sess.post(url, json=payload, timeout=30)
    resp.raise_for_status()
    try:
        data = resp.json()
    except Exception:
        raise RuntimeError(f"Respuesta no JSON desde {url}")
    if not isinstance(data, dict):
        raise RuntimeError(f"Respuesta inesperada desde {url}")
    return data


def _login_and_token(sess: requests.Session) -> str:
    if not FIELWEB_USERNAME or not FIELWEB_PASSWORD:
        raise RuntimeError("Faltan credenciales FIELWEB_USERNAME/FIELWEB_PASSWORD.")

    # GET inicial para iniciar sesion ASP.NET y obtener cookies como ASP.NET_SessionId
    try:
        sess.get(FIELWEB_LOGIN_URL, timeout=20)
    except Exception:
        pass

    signin_payload = {"u": FIELWEB_USERNAME, "c": FIELWEB_PASSWORD, "r": False, "aQS": False}
    data = _post_json(sess, "/Cuenta/login.aspx/signin", signin_payload)
    if not data.get("d", {}).get("Respuesta", True):
        raise RuntimeError(f"Login FielWeb falló: {data}")

    _post_json(sess, "/Cuenta/login.aspx/aceptoTerminosCondiciones", {"u": FIELWEB_USERNAME})

    usuario = _post_json(sess, "/app/main.aspx/traerUsuario", {})
    token = usuario.get("d", {}).get("Data", {}).get("token")
    if not token:
        raise RuntimeError("No se obtuvo token desde traerUsuario.")
    return token


def _build_ro_links(reg_img: Optional[Dict[str, Any]]) -> Dict[str, Optional[str]]:
    """Construye URL de visor RO a partir de registroOficialImagen.Url (&nav=...&tpag=...&pag=...)."""
    if not reg_img:
        return {"preview_url": None, "nav": None, "tpag": None, "pag": None}

    raw = (reg_img.get("Url") or "").lstrip("&")
    qs = parse_qs(raw)
    nav = qs.get("nav", [None])[0]
    tpag = qs.get("tpag", [None])[0]
    pag = qs.get("pag", [None])[0]
    preview = None
    if nav and tpag and pag:
        preview = f"{FIELWEB_BASE}/app/tpl/visualizador/visualizador.aspx?t=3&nav={nav}&tpag={tpag}&pag={pag}"
    return {"preview_url": preview, "nav": nav, "tpag": tpag, "pag": pag}


def _download_pdf(
    sess: requests.Session,
    nav: Optional[str],
    tpag: Optional[str],
    pag: Optional[str],
    titulo: Optional[str],
) -> Optional[Dict[str, Any]]:
    """
    Descarga el PDF usando el flujo del front:
    1) GET visualizador.aspx?t=3&nav=...&tpag=...&pag=...
    2) POST generarPDF con el HTML devuelto.
    Retorna un dict con pdf_base64 y tamaño en bytes, o None si falla.
    """
    if not (nav and tpag and pag):
        return None

    preview_url = f"{FIELWEB_BASE}/app/tpl/visualizador/visualizador.aspx?t=3&nav={nav}&tpag={tpag}&pag={pag}"
    try:
        resp_view = sess.get(preview_url, timeout=30)
        resp_view.raise_for_status()
        html = resp_view.text
    except Exception:
        return None

    payload = {
        "concordancias": False,
        "contenido": html,
        "desde": None,
        "hasta": None,
        "idCarga": None,
        "idNormas": [],
        "textoAdicional": None,
        "titulo": titulo or f"{nav}".replace("/", ""),
    }
    try:
        pdf_resp = sess.post(
            f"{FIELWEB_BASE}/app/tpl/visualizador/visualizador.aspx/generarPDF",
            json=payload,
            timeout=60,
        )
        pdf_resp.raise_for_status()
        pdf_bytes = pdf_resp.content
        return {
            "pdf_base64": base64.b64encode(pdf_bytes).decode("ascii"),
            "pdf_size": len(pdf_bytes),
        }
    except Exception:
        return None


def _generar_doc(
    sess: requests.Session,
    norma_id: int,
    titulo: str,
    concordancias: bool,
    formato: str,
    include_content: bool = False,
) -> Optional[Dict[str, Any]]:
    """
    Genera ruta de descarga para PDF/Word/HTML usando los endpoints generarPDF/generarDOC/generarHTML.
    formato: "pdf" | "word" | "html"
    Retorna dict con ruta y url_iframe para descarga directa.
    """
    endpoints = {
        "pdf": "/app/tpl/visualizador/visualizador.aspx/generarPDF",
        "word": "/app/tpl/visualizador/visualizador.aspx/generarDOC",
        "html": "/app/tpl/visualizador/visualizador.aspx/generarHTML",
    }
    tipo_archivo_map = {"pdf": "1", "word": "2", "html": "3"}
    ep = endpoints.get(formato.lower())
    if not ep:
        return None
    payload = {
        "contenido": "",
        "titulo": f"{norma_id} - {titulo}",
        "idNormas": [norma_id],
        "concordancias": bool(concordancias),
        "idCarga": None,
        "textoAdicional": "<b>Última Reforma: </b>(No reformado)",
        "desde": None,
        "hasta": None,
    }
    try:
        resp = _post_json(sess, ep, payload)
        ruta = resp.get("d", {}).get("Data")
        if not ruta:
            return None
        ruta_enc = ruta.replace("\\", "\\\\")
        download_url = (
            f"{FIELWEB_BASE}/Clases/iFrameDescarga.aspx?"
            f"ArchivoDescarga={ruta}&TipoArchivo={tipo_archivo_map[formato.lower()]}"
        )
        resultado: Dict[str, Any] = {"ruta": ruta_enc, "download_url": download_url}
        if include_content:
            try:
                headers = {"Referer": f"{FIELWEB_BASE}/Index.aspx?nid={norma_id}#norma/{norma_id}"}
                archivo_resp = sess.get(download_url, headers=headers, timeout=60)
                archivo_resp.raise_for_status()
                resultado["archivo_base64"] = base64.b64encode(archivo_resp.content).decode("ascii")
                resultado["content_type"] = archivo_resp.headers.get("Content-Type")
            except Exception as file_exc:
                resultado["archivo_error"] = str(file_exc)
        return resultado
    except Exception:
        return None


def _map_result(item: Dict[str, Any], descargar_pdf: bool, sess: requests.Session) -> Dict[str, Any]:
    ro_info = _build_ro_links(item.get("registroOficialImagen") or {})
    pdf_info = None
    if descargar_pdf:
        pdf_info = _download_pdf(
            sess,
            ro_info.get("nav"),
            ro_info.get("tpag"),
            ro_info.get("pag"),
            item.get("registroOficialImagen", {}).get("NombreResultados") or item.get("fuente"),
        )
    return {
        "area_principal": item.get("area"),
        "tipo_documento": item.get("tipoDocumento"),
        "numero": item.get("numero"),
        "titulo": item.get("titulo"),
        "tipo_publicacion": item.get("tipoPublicacion"),
        "fecha_publicacion": item.get("fechaPublicacion"),
        "fecha_emision": item.get("fechaExpedicion"),
        "derogado": item.get("derogado"),
        "emisor": item.get("emisor"),
        "fuente": item.get("fuente"),
        "norma_id": item.get("normaID"),
        "aciertos": item.get("aciertos"),
        "registro_oficial": {
            "titulo": item.get("registroOficialImagen", {}).get("NombreResultados") or item.get("fuente"),
            "raw_url": item.get("registroOficialImagen", {}).get("Url"),
            **ro_info,
            # Endpoint de descarga PDF: requiere POST con HTML (payload observado en generarPDF)
            "download_endpoint": f"{FIELWEB_BASE}/app/tpl/visualizador/visualizador.aspx/generarPDF",
            "pdf": pdf_info,
        },
        "descargas": {
            # generamos rutas on-demand en consultar_fielweb cuando se pide descargar_pdf
        },
        "cita": _build_citation(item),
    }


def _build_citation(item: Dict[str, Any]) -> Dict[str, Optional[str]]:
    """
    Construye un texto de cita y una URL básica a la norma.
    """
    norma_id = item.get("normaID")
    titulo = item.get("titulo") or ""
    numero = item.get("numero") or ""
    fuente = item.get("fuente") or ""
    fecha_pub = item.get("fechaPublicacion") or ""
    emisor = item.get("emisor") or ""

    partes = []
    if titulo:
        partes.append(titulo)
    if numero:
        partes.append(f"({numero})")
    if fuente or fecha_pub:
        partes.append(f"({fuente} {fecha_pub})".strip())
    if emisor:
        partes.append(emisor)
    texto = ". ".join([p for p in partes if p]).strip()

    url = None
    if norma_id:
        url = f"{FIELWEB_BASE}/Index.aspx?nid={norma_id}#norma/{norma_id}"

    return {"texto": texto, "url": url}


def _buscar(
    sess: requests.Session,
    token: str,
    texto: str,
    seccion: int,
    reformas: str,
    page: int,
    descargar_pdf: bool,
    incluir_descargas: bool,
) -> Dict[str, Any]:
    payload = {
        "tk": token,
        "s": seccion,
        "t": texto,
        "p": page,
        "ed": "",
        "eh": "",
        "pd": "",
        "ph": "",
        "la": [],
        "ld": [],
        "lr": [],
        "lac": [],
        "ls": [],
        "li": [],
        "c": None,
        "d": None,
        "reformas": reformas,
    }
    data = _post_json(sess, "/app/tpl/buscador/busquedas.aspx/buscar", payload)
    resultado = data.get("d", {}).get("Data") or []
    mapped = [_map_result(r, descargar_pdf, sess) for r in resultado]

    if incluir_descargas:
        for idx, r in enumerate(resultado):
            norma_id = r.get("normaID")
            titulo = r.get("titulo") or ""
            if not norma_id:
                continue
            try:
                nid = int(norma_id)
            except Exception:
                continue
            # Construir descargas para pdf/word/html con y sin concordancias
            for fmt in ("pdf", "word", "html"):
                sin = _generar_doc(sess, nid, titulo, False, fmt, include_content=incluir_descargas)
                con = _generar_doc(sess, nid, titulo, True, fmt, include_content=incluir_descargas)
                key_sin = f"{fmt}_sin"
                key_con = f"{fmt}_con"
                mapped[idx].setdefault("descargas", {})[key_sin] = sin
                mapped[idx].setdefault("descargas", {})[key_con] = con
    return {
        "mensaje": f"Resultados para '{texto}'",
        "nivel_consulta": "FielWeb",
        "texto": texto,
        "seccion": seccion,
        "reformas": reformas,
        "pagina": page,
        "resultado": mapped,
    }


def _traer_detalle_norma(sess: requests.Session, norma_id: int) -> Optional[Dict[str, Any]]:
    try:
        data = _post_json(sess, "/app/tpl/norma/norma.aspx/traerDetalleNorma", {"idNorma": norma_id})
        return data.get("d", {}).get("Data")
    except Exception:
        return None


def _traer_parte_norma(
    sess: requests.Session, norma_id: int, d_value: Optional[int], h_value: Optional[int]
) -> Optional[List[Dict[str, Any]]]:
    if d_value is None or h_value is None:
        return None
    try:
        data = _post_json(
            sess,
            "/app/tpl/norma/norma.aspx/traerParteNorma",
            {"id": norma_id, "d": d_value, "h": h_value},
        )
        return data.get("d", {}).get("Data")
    except Exception:
        return None


def consultar_fielweb(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Parámetros de entrada:
      - texto / consulta: término de búsqueda (obligatorio)
      - seccion / s: número de sección (opcional, por defecto 1)
      - reformas: pestaña (opcional, por defecto "2" = Todo)
      - page / pag: página (opcional, por defecto 1)
      - descargar_pdf (bool, opcional): si True, intenta generar y devolver pdf_base64 por cada resultado con RO.
      - norma_id (opcional): si se envía, devolver detalle de norma (traerDetalleNorma)
      - parte_d / parte_h (opcionales): si se envían junto a norma_id, traerParteNorma y devolver la lista de textos.
      - descargas (bool, opcional): si True, devuelve rutas y URLs de descarga (pdf/word/html con/sin concordancias).
    """
    texto = (payload.get("texto") or payload.get("consulta") or "").strip()
    if not texto:
        return {"error": "Debe proporcionar 'texto' o 'consulta'."}

    try:
        seccion = int(payload.get("seccion") or payload.get("s") or DEFAULT_SECCION)
    except Exception:
        seccion = DEFAULT_SECCION
    reformas = str(payload.get("reformas") or DEFAULT_REFORMAS)
    try:
        page = int(payload.get("page") or payload.get("pag") or DEFAULT_PAGE)
    except Exception:
        page = DEFAULT_PAGE

    descargar_pdf = bool(payload.get("descargar_pdf") or False)
    incluir_descargas = bool(payload.get("descargas") or False)

    try:
        sess = _session()
        token = _login_and_token(sess)
        base = _buscar(sess, token, texto, seccion, reformas, page, descargar_pdf, incluir_descargas)

        # Opcional: traer detalle y parte de norma si se solicita
        norma_id = payload.get("norma_id") or payload.get("id_norma")
        if norma_id:
            try:
                norma_id_int = int(norma_id)
                detalle = _traer_detalle_norma(sess, norma_id_int)
                parte_d = payload.get("parte_d")
                parte_h = payload.get("parte_h")
                parte = None
                try:
                    if parte_d is not None and parte_h is not None:
                        parte = _traer_parte_norma(sess, norma_id_int, int(parte_d), int(parte_h))
                except Exception:
                    parte = None
                base["norma_detalle"] = detalle
                if parte is not None:
                    base["norma_parte"] = parte
            except Exception:
                base["norma_detalle"] = {"error": "No se pudo obtener detalle de norma"}
        return base
    except requests.HTTPError as e:
        return {
            "error": f"HTTP {e.response.status_code} en FielWeb: {e.response.text}",
            "nivel_consulta": "FielWeb",
        }
    except Exception as e:
        return {"error": f"Error FielWeb: {e}", "nivel_consulta": "FielWeb"}
