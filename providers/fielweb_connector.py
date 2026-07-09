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
import re
import base64
import html as html_lib
import requests
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, parse_qs

FIELWEB_BASE = os.getenv("FIELWEB_BASE_URL", "https://www.fielweb.com").rstrip("/")
FIELWEB_LOGIN_URL = os.getenv("FIELWEB_LOGIN_URL", f"{FIELWEB_BASE}/Cuenta/Login.aspx")
FIELWEB_USERNAME = os.getenv("FIELWEB_USERNAME", "").strip()
FIELWEB_PASSWORD = os.getenv("FIELWEB_PASSWORD", "").strip()

DEFAULT_REFORMAS = "2"  # pestaña "Todo" en el front
DEFAULT_SECCION = 1     # s=1 = normativa VIGENTE (2 = histórica / otro año)
DEFAULT_PAGE = 1
# Límite por defecto de resultados cuando el llamador no especifica uno.
# Evita devolver ~20 normas por página y prioriza precisión. Configurable por env.
DEFAULT_LIMITE = int(os.getenv("FIELWEB_DEFAULT_LIMITE", "5"))


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


def _as_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


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
    signin = _as_dict(data.get("d"))
    signin_data = _as_dict(signin.get("Data"))
    if not signin.get("Respuesta", True):
        raise RuntimeError(f"Login FielWeb falló: {data}")

    _post_json(sess, "/Cuenta/login.aspx/aceptoTerminosCondiciones", {"u": FIELWEB_USERNAME})
    usuario = _post_json(sess, "/app/main.aspx/traerUsuario", {})
    usuario_data = _as_dict(usuario.get("d"))
    usuario_data_block = _as_dict(usuario_data.get("Data"))
    token = (
        usuario_data_block.get("tk")
        or usuario_data_block.get("token")
        or signin_data.get("tk")
        or signin_data.get("token")
    )  # token de sesión
    if not token:
        raise RuntimeError(f"No se obtuvo token desde traerUsuario: {usuario}")
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
        resp_d = _as_dict(resp.get("d"))
        ruta = resp_d.get("Data")
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


def _filename_from_ruta(ruta: Optional[str], norma_id: int, formato: str) -> str:
    ext_map = {"pdf": "pdf", "word": "doc", "html": "html"}
    if ruta:
        raw = ruta.replace("\\\\", "\\")
        base = os.path.basename(raw)
        if base:
            return base
    return f"norma_{norma_id}.{ext_map.get(formato.lower(), 'bin')}"


def descargar_norma_archivo(
    norma_id: int,
    formato: str = "pdf",
    concordancias: bool = False,
    titulo: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Descarga un archivo (PDF/Word/HTML) de una norma por norma_id.
    Retorna bytes, content_type y filename para servirlo desde el backend.
    """
    fmt = (formato or "pdf").lower()
    sess = _session()
    _login_and_token(sess)
    info = _generar_doc(
        sess,
        norma_id,
        titulo or f"Norma {norma_id}",
        bool(concordancias),
        fmt,
        include_content=True,
    )
    if not info:
        return None
    archivo_base64 = info.get("archivo_base64")
    if not archivo_base64:
        return {"error": info.get("archivo_error") or "No se pudo descargar el archivo."}
    try:
        content_bytes = base64.b64decode(archivo_base64)
    except Exception:
        return {"error": "No se pudo decodificar el archivo."}
    return {
        "content_bytes": content_bytes,
        "content_type": info.get("content_type"),
        "filename": _filename_from_ruta(info.get("ruta"), norma_id, fmt),
    }


def _map_result(item: Dict[str, Any], descargar_pdf: bool, sess: requests.Session) -> Dict[str, Any]:
    reg_img = _as_dict(item.get("registroOficialImagen"))
    ro_info = _build_ro_links(reg_img)
    pdf_info = None
    if descargar_pdf:
        pdf_info = _download_pdf(
            sess,
            ro_info.get("nav"),
            ro_info.get("tpag"),
            ro_info.get("pag"),
            reg_img.get("NombreResultados") or item.get("fuente"),
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
            "titulo": reg_img.get("NombreResultados") or item.get("fuente"),
            "raw_url": reg_img.get("Url"),
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
    limite_resultados: Optional[int],
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
    data_block = _as_dict(data.get("d"))
    resultado = data_block.get("Data") or []
    if isinstance(resultado, dict):
        resultado = [resultado]
    if not isinstance(resultado, list):
        resultado = []
    if isinstance(limite_resultados, int) and limite_resultados > 0:
        resultado = resultado[:limite_resultados]
    mapped: List[Dict[str, Any]] = []
    for r in resultado:
        if not isinstance(r, dict):
            continue
        mapped_item = _map_result(r, descargar_pdf, sess)
        if incluir_descargas:
            norma_id = r.get("normaID")
            titulo = r.get("titulo") or ""
            if norma_id:
                try:
                    nid = int(norma_id)
                except Exception:
                    nid = None
                if nid:
                    for fmt in ("pdf", "word", "html"):
                        sin = _generar_doc(sess, nid, titulo, False, fmt, include_content=incluir_descargas)
                        con = _generar_doc(sess, nid, titulo, True, fmt, include_content=incluir_descargas)
                        key_sin = f"{fmt}_sin"
                        key_con = f"{fmt}_con"
                        mapped_item.setdefault("descargas", {})[key_sin] = sin
                        mapped_item.setdefault("descargas", {})[key_con] = con
        mapped.append(mapped_item)
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
        data_block = _as_dict(data.get("d"))
        return data_block.get("Data")
    except Exception:
        return None


def _traer_parte_norma(
    sess: requests.Session, norma_id: int, d_value: Optional[int], h_value: Optional[int]
) -> Optional[List[Dict[str, Any]]]:
    if d_value is None or h_value is None:
        return None
    data = _post_json(
        sess,
        "/app/tpl/norma/norma.aspx/traerParteNorma",
        {"id": norma_id, "d": d_value, "h": h_value},
    )
    data_block = _as_dict(data.get("d"))
    return data_block.get("Data")


# ---------------------------------------------------------------------------
# Articulado: traer y localizar artículos por número.
#
# NOTA: en FielWeb `traerParteNorma` recibe `d`/`h` que son OFFSETS de posición
# de los bloques de texto del articulado (no números de artículo). Por eso pedir
# `d=169` NO trae el "Art. 169". El articulado completo se obtiene con d=0 y un
# `h` grande, y cada artículo empieza en un bloque cuyo texto plano arranca con
# "Art. N.-". Aquí traemos el articulado y localizamos el artículo por ese patrón.
# ---------------------------------------------------------------------------

# Cantidad máxima de bloques a solicitar (el Código del Trabajo tiene ~1958).
ARTICULADO_H_MAX = int(os.getenv("FIELWEB_ARTICULADO_H_MAX", "20000"))

# Inicio de artículo: "Art. 169.-", "Art 169.-", "Art. 169 .-", etc.
_ART_INICIO_RE = re.compile(r"^\s*Art\.?\s*([0-9]+[A-Za-z\.\-]*)\s*\.-", re.IGNORECASE)


def _strip_html(texto: Optional[str]) -> str:
    """Convierte el HTML de un bloque de FielWeb a texto plano legible."""
    if not texto:
        return ""
    t = re.sub(r"(?i)<br\s*/?>", "\n", texto)
    t = re.sub(r"<[^>]+>", " ", t)
    t = html_lib.unescape(t)
    t = re.sub(r"[ \t ]+", " ", t)
    t = re.sub(r"\s*\n\s*", "\n", t)
    return t.strip()


def _norm_num_articulo(valor: Any) -> str:
    """Normaliza un número de artículo para comparar ('169', 'Art. 169', '169-A')."""
    return re.sub(r"[^0-9a-zA-Z]", "", str(valor or "")).lower()


def _traer_articulado(sess: requests.Session, norma_id: int) -> List[Dict[str, Any]]:
    """Devuelve la lista cruda de bloques (Texto/ArbolId/Id) del articulado completo."""
    data = _post_json(
        sess,
        "/app/tpl/norma/norma.aspx/traerParteNorma",
        {"id": norma_id, "d": 0, "h": ARTICULADO_H_MAX},
    )
    data_block = _as_dict(data.get("d"))
    partes = data_block.get("Data")
    return partes if isinstance(partes, list) else []


def _buscar_articulo(bloques: List[Dict[str, Any]], numero: Any) -> Optional[Dict[str, Any]]:
    """
    Localiza un artículo por su número dentro de los bloques del articulado.
    Agrupa desde el bloque que inicia con "Art. N.-" hasta el bloque anterior
    al siguiente artículo. Devuelve dict con {articulo, texto, html, bloque_indice}.
    """
    objetivo = _norm_num_articulo(numero)
    if not objetivo:
        return None

    inicio = None
    for idx, bloque in enumerate(bloques):
        plano = _strip_html(bloque.get("Texto", ""))
        m = _ART_INICIO_RE.match(plano)
        if m and _norm_num_articulo(m.group(1)) == objetivo:
            inicio = idx
            break
    if inicio is None:
        return None

    piezas_texto: List[str] = []
    piezas_html: List[str] = []
    for j in range(inicio, len(bloques)):
        plano = _strip_html(bloques[j].get("Texto", ""))
        if j > inicio and _ART_INICIO_RE.match(plano):
            break  # empezó el siguiente artículo
        if plano:
            piezas_texto.append(plano)
            piezas_html.append(bloques[j].get("Texto", ""))

    return {
        "articulo": str(numero),
        "texto": "\n".join(piezas_texto).strip(),
        "html": "".join(piezas_html),
        "bloque_indice": inicio,
    }


def _listar_articulos(bloques: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Parsea el articulado completo a una lista de {articulo, titulo, texto}."""
    articulos: List[Dict[str, Any]] = []
    actual: Optional[Dict[str, Any]] = None
    for bloque in bloques:
        plano = _strip_html(bloque.get("Texto", ""))
        if not plano:
            continue
        m = _ART_INICIO_RE.match(plano)
        if m:
            if actual:
                actual["texto"] = "\n".join(actual["_piezas"]).strip()
                actual.pop("_piezas", None)
                articulos.append(actual)
            resto = plano[m.end():].strip()
            titulo = resto.split(".-", 1)[0].strip() if ".-" in resto else ""
            actual = {"articulo": m.group(1), "titulo": titulo[:200], "_piezas": [plano]}
        elif actual:
            actual["_piezas"].append(plano)
    if actual:
        actual["texto"] = "\n".join(actual["_piezas"]).strip()
        actual.pop("_piezas", None)
        articulos.append(actual)
    return articulos


def consultar_fielweb(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Parámetros de entrada:
      - texto / consulta: término de búsqueda (obligatorio)
      - seccion / s: número de sección (opcional, por defecto 1)
      - reformas: pestaña (opcional, por defecto "2" = Todo)
      - page / pag: página (opcional, por defecto 1)
      - descargar_pdf (bool, opcional): si True, intenta generar y devolver pdf_base64 por cada resultado con RO.
      - norma_id (opcional): si se envía, devolver detalle de norma (traerDetalleNorma)
      - articulo / art (opcional): número de artículo a recuperar (ej. "169"). Junto a norma_id
        devuelve en `norma_parte` el texto del artículo localizado por su encabezado "Art. N.-".
      - articulado / todo_articulado (bool, opcional): junto a norma_id devuelve en
        `norma_articulado` el índice completo (número + título + texto por artículo).
      - parte_d / parte_h (opcionales, avanzado): offsets crudos de bloque para traerParteNorma
        (NO son números de artículo; para el texto de un artículo usar `articulo`).
      - descargas (bool, opcional): si True, devuelve rutas y URLs de descarga (pdf/word/html con/sin concordancias).
    """
    if not isinstance(payload, dict):
        return {"error": "Payload inválido (se esperaba objeto JSON).", "nivel_consulta": "FielWeb"}

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
    limite_resultados = payload.get("limite_resultados")
    if limite_resultados is None:
        limite_resultados = payload.get("max_resultados")
    if limite_resultados is None:
        limite_resultados = payload.get("limit")
    try:
        if limite_resultados is not None:
            limite_resultados = int(limite_resultados)
    except Exception:
        limite_resultados = None
    # Si no se pidió un límite explícito, aplicar uno bajo para priorizar precisión.
    if limite_resultados is None:
        limite_resultados = DEFAULT_LIMITE

    try:
        sess = _session()
        token = _login_and_token(sess)
        base = _buscar(
            sess,
            token,
            texto,
            seccion,
            reformas,
            page,
            descargar_pdf,
            incluir_descargas,
            limite_resultados,
        )

        # Opcional: traer detalle y articulado de una norma si se solicita
        norma_id = payload.get("norma_id") or payload.get("id_norma")
        if norma_id:
            try:
                norma_id_int = int(norma_id)
            except Exception:
                base["norma_detalle"] = {"error": f"norma_id inválido: {norma_id!r}"}
                return base

            try:
                base["norma_detalle"] = _traer_detalle_norma(sess, norma_id_int)
            except Exception as det_exc:
                base["norma_detalle"] = {"error": f"No se pudo obtener detalle de norma: {det_exc}"}

            articulo = payload.get("articulo") or payload.get("art")
            quiere_articulado = bool(payload.get("articulado") or payload.get("todo_articulado"))
            parte_d = payload.get("parte_d")
            parte_h = payload.get("parte_h")

            try:
                if articulo is not None and str(articulo).strip():
                    # Buscar un artículo puntual por su número (ej. "169").
                    bloques = _traer_articulado(sess, norma_id_int)
                    encontrado = _buscar_articulo(bloques, articulo)
                    if encontrado:
                        base["norma_parte"] = encontrado
                    else:
                        disponibles = [a.get("articulo") for a in _listar_articulos(bloques)]
                        base["norma_parte"] = {
                            "error": f"No se encontró el Art. {articulo} en la norma {norma_id_int}.",
                            "articulos_detectados": len(disponibles),
                            "ejemplos": disponibles[:10],
                        }
                elif quiere_articulado:
                    # Índice del articulado (liviano: número + título). El texto
                    # completo de un artículo se pide con el parámetro `articulo`.
                    bloques = _traer_articulado(sess, norma_id_int)
                    articulos = _listar_articulos(bloques)
                    base["norma_articulado"] = {
                        "total": len(articulos),
                        "articulos": [
                            {"articulo": a.get("articulo"), "titulo": a.get("titulo", "")}
                            for a in articulos
                        ],
                    }
                elif parte_d is not None and parte_h is not None:
                    # Compatibilidad: consulta cruda por offsets d/h.
                    base["norma_parte"] = _traer_parte_norma(
                        sess, norma_id_int, int(parte_d), int(parte_h)
                    )
            except Exception as art_exc:
                base["norma_parte"] = {
                    "error": f"No se pudo obtener el articulado: {art_exc}"
                }
        return base
    except requests.HTTPError as e:
        return {
            "error": f"HTTP {e.response.status_code} en FielWeb: {e.response.text}",
            "nivel_consulta": "FielWeb",
        }
    except Exception as e:
        return {"error": f"Error FielWeb: {e}", "nivel_consulta": "FielWeb"}

