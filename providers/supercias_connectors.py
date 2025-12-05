import base64
import io
import os
import re
from typing import Dict, Any, Optional
from urllib.parse import urljoin

import requests
from PIL import Image

SUPERCIAS_BASE = os.getenv(
    "SUPERCIAS_BASE_URL",
    os.getenv(
        "SUPERCIA_BASE_URL",
        # Fallback al dominio móvil (resuelve mejor en algunos entornos)
        "https://appscvsmovil.supercias.gob.ec/consultaCompanias/societario/",
    ),
).rstrip("/") + "/"
MAIN_URL = urljoin(SUPERCIAS_BASE, "busquedaCompanias.jsf")


def _extract_viewstate(html: str) -> Optional[str]:
    m = re.search(r'name="javax\.faces\.ViewState"[^>]*value="([^"]+)"', html)
    return m.group(1) if m else None


def _extract_captcha_src(html: str) -> Optional[str]:
    m = re.search(r'src="(tmp/[^"]+\.png)"', html)
    return m.group(1) if m else None


def _ocr_digits(img_bytes: bytes) -> str:
    """
    OCR simple para dígitos del captcha; requiere Tesseract instalado en el sistema.
    Si no está disponible, lanza excepción para que el caller lo maneje.
    """
    try:
        import pytesseract
    except Exception as e:
        raise RuntimeError(f"OCR no disponible (pytesseract no instalado): {e}")

    img = Image.open(io.BytesIO(img_bytes)).convert("L")
    # Umbral sencillo para resaltar dígitos blancos sobre fondo azul
    img = img.point(lambda x: 255 if x > 80 else 0)
    text = pytesseract.image_to_string(img, config="--psm 7 -c tessedit_char_whitelist=0123456789")
    digits = re.sub(r"\D", "", text)
    if len(digits) < 4:
        raise RuntimeError(f"OCR falló, salida: {text}")
    return digits[:6]


def _session_headers() -> Dict[str, str]:
    return {
        "User-Agent": "Mozilla/5.0 (compatible; H&G Abogados IA)",
        "Accept-Language": "es-419,es;q=0.9",
    }


def _get_initial_state(session: requests.Session) -> Dict[str, Any]:
    resp = session.get(MAIN_URL, headers=_session_headers(), timeout=20)
    resp.raise_for_status()
    html = resp.text
    viewstate = _extract_viewstate(html)
    if not viewstate:
        raise RuntimeError("No se pudo extraer javax.faces.ViewState")
    captcha_src = _extract_captcha_src(html)
    return {"viewstate": viewstate, "captcha_src": captcha_src, "html": html}


def _get_captcha(session: requests.Session, captcha_src: Optional[str]) -> bytes:
    if not captcha_src:
        # fallback a tmp aleatorio puede fallar
        raise RuntimeError("No se encontró src del captcha en la página inicial")
    url = urljoin(SUPERCIAS_BASE, captcha_src)
    resp = session.get(url, headers={"Referer": MAIN_URL, **_session_headers()}, timeout=20)
    resp.raise_for_status()
    return resp.content


def _parse_viewstate_from_partial(xml_text: str) -> Optional[str]:
    m = re.search(r'<update id="javax\.faces\.ViewState">\s*<!\[CDATA\[(.*?)\]\]>', xml_text, re.S)
    return m.group(1).strip() if m else None


def _post_partial(session: requests.Session, data: Dict[str, Any]) -> str:
    headers = {
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Faces-Request": "partial/ajax",
        "Referer": MAIN_URL,
        **_session_headers(),
    }
    resp = session.post(MAIN_URL, data=data, headers=headers, timeout=20)
    resp.raise_for_status()
    return resp.text


def _autocomplete(session: requests.Session, viewstate: str, query: str, tipo_busqueda: int) -> str:
    data = {
        "javax.faces.partial.ajax": "true",
        "javax.faces.source": "frmBusquedaCompanias:parametroBusqueda",
        "javax.faces.partial.execute": "frmBusquedaCompanias:parametroBusqueda",
        "javax.faces.partial.render": "frmBusquedaCompanias:parametroBusqueda",
        "javax.faces.behavior.event": "query",
        "javax.faces.partial.event": "query",
        "frmBusquedaCompanias": "frmBusquedaCompanias",
        "frmBusquedaCompanias:parametroBusqueda_query": query,
        "frmBusquedaCompanias:tipoBusqueda": str(tipo_busqueda),
        "frmBusquedaCompanias:browser": "Chrome",
        "frmBusquedaCompanias:altoBrowser": "900",
        "frmBusquedaCompanias:anchoBrowser": "1440",
        "frmBusquedaCompanias:menuDispositivoMovil": "hidden",
        "javax.faces.ViewState": viewstate,
    }
    return _post_partial(session, data)


def _select_item(session: requests.Session, viewstate: str, display_value: str, query: str, tipo_busqueda: int) -> str:
    data = {
        "javax.faces.partial.ajax": "true",
        "javax.faces.source": "frmBusquedaCompanias:parametroBusqueda",
        "javax.faces.partial.execute": "frmBusquedaCompanias:parametroBusqueda",
        "javax.faces.partial.render": "frmBusquedaCompanias:parametroBusqueda frmBusquedaCompanias:panelCompaniaSeleccionada",
        "javax.faces.behavior.event": "itemSelect",
        "javax.faces.partial.event": "itemSelect",
        "frmBusquedaCompanias": "frmBusquedaCompanias",
        "frmBusquedaCompanias:parametroBusqueda_input": display_value,
        "frmBusquedaCompanias:parametroBusqueda_itemSelect": display_value,
        "frmBusquedaCompanias:parametroBusqueda_query": query,
        "frmBusquedaCompanias:tipoBusqueda": str(tipo_busqueda),
        "frmBusquedaCompanias:browser": "Chrome",
        "frmBusquedaCompanias:altoBrowser": "900",
        "frmBusquedaCompanias:anchoBrowser": "1440",
        "frmBusquedaCompanias:menuDispositivoMovil": "hidden",
        "javax.faces.ViewState": viewstate,
    }
    return _post_partial(session, data)


def _final_consulta(session: requests.Session, viewstate: str, captcha: str) -> str:
    data = {
        "javax.faces.partial.ajax": "true",
        "javax.faces.source": "frmBusquedaCompanias:btnConsultarCompania",
        "javax.faces.partial.execute": "frmBusquedaCompanias:btnConsultarCompania frmBusquedaCompanias:captcha frmBusquedaCompanias:browser frmBusquedaCompanias:altoBrowser frmBusquedaCompanias:anchoBrowser frmBusquedaCompanias:menuDispositivoMovil",
        "frmBusquedaCompanias:btnConsultarCompania": "frmBusquedaCompanias:btnConsultarCompania",
        "frmBusquedaCompanias:captcha": captcha,
        "frmBusquedaCompanias:browser": "Chrome",
        "frmBusquedaCompanias:altoBrowser": "900",
        "frmBusquedaCompanias:anchoBrowser": "1440",
        "frmBusquedaCompanias:menuDispositivoMovil": "hidden",
        "javax.faces.ViewState": viewstate,
    }
    return _post_partial(session, data)


def consultar_supercias_companias(payload: Dict[str, Any]) -> Dict[str, Any]:
    termino = (payload.get("termino") or payload.get("texto") or "").strip()
    tipo = int(payload.get("tipo_busqueda") or 1)  # 1 expediente, 2 ruc, 3 nombre
    if not termino:
        return {"error": "Debe enviar 'termino' y 'tipo_busqueda' (1=expediente,2=ruc,3=nombre)."}

    session = requests.Session()
    try:
        # Paso 1: inicial
        init = _get_initial_state(session)
        viewstate = init["viewstate"]
        captcha_src = init["captcha_src"]

        # Paso 2: captcha
        captcha_bytes = _get_captcha(session, captcha_src)
        captcha_code = _ocr_digits(captcha_bytes)

        # Paso 3: autocomplete
        auto_resp = _autocomplete(session, viewstate, termino, tipo)
        new_vs = _parse_viewstate_from_partial(auto_resp) or viewstate

        # Paso 4: seleccionar item (usamos el mismo término como display)
        sel_resp = _select_item(session, new_vs, termino, termino, tipo)
        new_vs2 = _parse_viewstate_from_partial(sel_resp) or new_vs

        # Paso 5: consulta final
        final_resp = _final_consulta(session, new_vs2, captcha_code)

        # Retornar datos crudos (JSF parcial). Parsing HTML no trivial sin ejemplos; devolvemos las respuestas.
        return {
            "mensaje": "Consulta enviada a Supercias",
            "nivel_consulta": "Supercias - compañías",
            "termino": termino,
            "tipo_busqueda": tipo,
            "captcha": captcha_code,
            "responses": {
                "autocomplete": auto_resp,
                "itemSelect": sel_resp,
                "final": final_resp,
            },
        }
    except Exception as e:
        return {"error": f"Fallo en consulta Supercias: {e}"}
