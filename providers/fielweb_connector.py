# providers/fielweb_connector.py
import os
import asyncio
from typing import List, Dict, Any, Optional
from urllib.parse import urljoin

from playwright.async_api import async_playwright, TimeoutError as PWTimeout

# ================================
# ⚙️ CONFIGURACIÓN DESDE ENTORNO
# ================================
FIELWEB_URL = os.getenv("FIELWEB_LOGIN_URL", "").strip()
USERNAME = os.getenv("FIELWEB_USERNAME", "").strip()
PASSWORD = os.getenv("FIELWEB_PASSWORD", "").strip()

# Ajustes generales
PAGE_TIMEOUT_MS = 25_000
NAV_TIMEOUT_MS = 30_000
MAX_ITEMS = 12

# ================================
# 🔧 HELPERS DE SELECTORES
# ================================
LOGIN_SELECTORS = {
    "user": [
        'input[name="ctl00$ContentPlaceHolder1$txtUsuario"]',
        '#ctl00_ContentPlaceHolder1_txtUsuario',
        'input[id*="txtUsuario"]',
        'input[type="email"]',
        'input[name="usuario"]'
    ],
    "password": [
        'input[name="ctl00$ContentPlaceHolder1$txtClave"]',
        '#ctl00_ContentPlaceHolder1_txtClave',
        'input[id*="txtClave"]',
        'input[type="password"]',
        'input[name="clave"]'
    ],
    "submit": [
        'input[id="ctl00_ContentPlaceHolder1_btnIngresar"]',
        '#ctl00_ContentPlaceHolder1_btnIngresar',
        'button[id*="btnIngresar"]',
        'button[type="submit"]',
        'input[type="submit"]'
    ]
}

SEARCH_SELECTORS = {
    "query": [
        '#ctl00_ContentPlaceHolder1_txtBuscar',
        'input[id*="txtBuscar"]',
        'input[name="ctl00$ContentPlaceHolder1$txtBuscar"]',
        'input[placeholder*="Buscar"]',
        'input[type="search"]'
    ],
    "submit": [
        '#ctl00_ContentPlaceHolder1_btnBuscar',
        'input[id*="btnBuscar"]',
        'button[id*="btnBuscar"]',
        'button:has-text("Buscar")',
        'button[type="submit"]'
    ]
}

RESULT_ITEM_SELECTORS = [
    ".resultadoItem",
    ".card-body",
    "div.resultado",
    "div.search-result",
]

TITLE_CANDIDATES = [
    "h3", "h2", "h4", "a.title", "a strong", ".titulo", ".title", "a"
]

# Botones típicos en FielWeb (pueden tener iconos)
DOWNLOAD_ANCHOR_FILTERS = ["pdf", "word", "docx"]
LABEL_CONCORDANCIAS = ["Concordancia", "Concordancias"]
LABEL_JURIS = ["Jurisprudencia", "Sentencia", "Jurisprudencias", "Sentencias"]


# ================================
# 🔎 UTILIDADES
# ================================
async def _first_selector(page, selectors: List[str]) -> Optional[str]:
    """Devuelve el primer selector que existe en la página."""
    for sel in selectors:
        el = await page.query_selector(sel)
        if el:
            return sel
    return None


async def _inner_text_or(page, root, candidates: List[str], default: str = "") -> str:
    for sel in candidates:
        try:
            el = await root.query_selector(sel)
            if el:
                txt = (await el.inner_text()).strip()
                if txt:
                    return txt
        except Exception:
            continue
    # fallback: todo el bloque
    try:
        txt = (await root.inner_text()).strip()
        return txt or default
    except Exception:
        return default


def _classify_link_text(texto: str) -> str:
    t = (texto or "").lower()
    if any(k in t for k in [*DOWNLOAD_ANCHOR_FILTERS, "descargar", "download"]):
        return "descarga"
    if any(k.lower() in (texto or "") for k in LABEL_CONCORDANCIAS):
        return "concordancia"
    if any(k.lower() in (texto or "") for k in LABEL_JURIS):
        return "jurisprudencia"
    return "otro"


# ================================
# 🔐 LOGIN
# ================================
async def _login(page, base_url: str, user: str, password: str) -> None:
    await page.goto(base_url, wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)

    user_sel = await _first_selector(page, LOGIN_SELECTORS["user"])
    pass_sel = await _first_selector(page, LOGIN_SELECTORS["password"])
    subm_sel = await _first_selector(page, LOGIN_SELECTORS["submit"])

    if not (user_sel and pass_sel and subm_sel):
        raise RuntimeError("No se encontraron los campos de login en FielWeb (selectores cambiados).")

    await page.fill(user_sel, user)
    await page.fill(pass_sel, password)
    await page.click(subm_sel)

    # Esperar algún indicio de sesión iniciada o navegación
    try:
        await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT_MS)
    except PWTimeout:
        # A veces no navega; dar un pequeño respiro
        await page.wait_for_timeout(1500)

    # Heurística mínima: si vuelve a mostrar el botón, puede ser fallo
    still_login = await page.query_selector(subm_sel)
    if still_login:
        # Ver si existe un mensaje de error
        err = await page.locator(".validation-summary-errors, .text-danger").first
        if await err.count():
            msg = (await err.inner_text()).strip()
            raise RuntimeError(f"Fallo de autenticación en FielWeb: {msg or 'credenciales inválidas.'}")


# ================================
# 🔎 BÚSQUEDA Y EXTRACCIÓN
# ================================
async def _buscar(page, texto: str) -> List[Dict[str, Any]]:
    q_sel = await _first_selector(page, SEARCH_SELECTORS["query"])
    b_sel = await _first_selector(page, SEARCH_SELECTORS["submit"])
    if not (q_sel and b_sel):
        raise RuntimeError("No se encontraron los controles de búsqueda en FielWeb.")

    await page.fill(q_sel, texto)
    await page.click(b_sel)

    try:
        await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT_MS)
    except PWTimeout:
        await page.wait_for_timeout(1000)

    items = []
    # Buscar contenedores de resultados
    containers = []
    for s in RESULT_ITEM_SELECTORS:
        nodes = await page.query_selector_all(s)
        if nodes:
            containers = nodes
            break

    for node in containers[:MAX_ITEMS]:
        titulo = await _inner_text_or(page, node, TITLE_CANDIDATES, default="Resultado sin título")

        enlaces = []
        links = await node.query_selector_all("a")
        for a in links:
            href = (await a.get_attribute("href")) or ""
            text = ((await a.inner_text()) or "").strip()
            if not href:
                continue
            tipo = _classify_link_text(text)

            # convertir a URL absoluta por seguridad
            abs_url = urljoin(page.url, href)

            # Filtrar lo más útil por defecto
            if tipo in {"descarga", "concordancia", "jurisprudencia"}:
                enlaces.append({"tipo": tipo, "texto": text or "enlace", "url": abs_url})

        # Quitar duplicados por URL
        seen = set()
        enlaces_unique = []
        for e in enlaces:
            if e["url"] in seen:
                continue
            seen.add(e["url"])
            enlaces_unique.append(e)

        items.append({"titulo": titulo, "enlaces": enlaces_unique})

    return items


# ================================
# 🚀 FUNCIÓN ASÍNCRONA PRINCIPAL
# ================================
async def _buscar_en_fielweb_async(texto: str) -> Dict[str, Any]:
    """Flujo completo: login + búsqueda + extracción."""
    if not (FIELWEB_URL and USERNAME and PASSWORD):
        faltan = [k for k, v in {
            "FIELWEB_LOGIN_URL": FIELWEB_URL,
            "FIELWEB_USERNAME": USERNAME,
            "FIELWEB_PASSWORD": PASSWORD
        }.items() if not v]
        raise RuntimeError(f"Faltan variables de entorno: {', '.join(faltan)}")

    launch_args = ["--no-sandbox", "--disable-dev-shm-usage"]
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=launch_args)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/121.0 Safari/537.36",
            accept_downloads=False
        )
        page = await context.new_page()
        page.set_default_timeout(PAGE_TIMEOUT_MS)

        try:
            await _login(page, FIELWEB_URL, USERNAME, PASSWORD)
            resultados = await _buscar(page, texto)
            return {
                "mensaje": f"Resultados encontrados en FielWeb para '{texto}'.",
                "nivel_consulta": "FielWeb",
                "resultado": resultados
            }
        finally:
            await context.close()
            await browser.close()


# ================================
# 🧠 INTERFAZ PÚBLICA SINCRÓNICA
# ================================
def consultar_fielweb(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Punto de entrada usado por FastAPI (endpoints síncronos).
    - payload admite: {"texto": "..."} o {"consulta": "..."}
    """
    texto = (payload.get("texto") or payload.get("consulta") or "").strip()
    if not texto:
        return {"error": "Debe proporcionar un texto de búsqueda en 'texto' o 'consulta'."}

    try:
        # En FastAPI (worker sync) esto corre en un hilo → asyncio.run es seguro aquí.
        return asyncio.run(_buscar_en_fielweb_async(texto))
    except PWTimeout as te:
        return {
            "error": f"Tiempo de espera agotado en FielWeb: {str(te)}",
            "nivel_consulta": "FielWeb"
        }
    except Exception as e:
        return {
            "error": f"Ocurrió un error al consultar FielWeb: {str(e)}",
            "nivel_consulta": "FielWeb"
        }
