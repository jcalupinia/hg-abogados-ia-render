# providers/fielweb_connector.py
import os
import asyncio
from typing import List, Dict, Any, Optional
from urllib.parse import urljoin
from playwright.async_api import async_playwright, TimeoutError as PWTimeout

# ================================
# ⚙️ CONFIGURACIÓN DESDE ENTORNO
# ================================
FIELWEB_URL = os.getenv("FIELWEB_LOGIN_URL", "https://www.fielweb.com/Cuenta/Login.aspx").strip()
USERNAME = os.getenv("FIELWEB_USERNAME", "consultor@hygabogados.ec").strip()
PASSWORD = os.getenv("FIELWEB_PASSWORD", "").strip()

PAGE_TIMEOUT_MS = 30_000
NAV_TIMEOUT_MS = 35_000
MAX_ITEMS = 12

# ================================
# 🔧 SELECTORES ADAPTATIVOS
# ================================
LOGIN_SELECTORS = {
    "user": [
        '#usuario',  # Nuevo FielWeb Plus
        'input[name="usuario"]',
        'input[placeholder*="Usuario"]',
        'input[id*="txtUsuario"]',
        'input[name="ctl00$ContentPlaceHolder1$txtUsuario"]'
    ],
    "password": [
        '#clave',  # Nuevo FielWeb Plus
        'input[name="clave"]',
        'input[placeholder*="Clave"]',
        'input[id*="txtClave"]',
        'input[name="ctl00$ContentPlaceHolder1$txtClave"]',
        'input[type="password"]'
    ],
    "submit": [
        '#btnEntrar',  # Nuevo FielWeb Plus
        'button:has-text("Entrar")',
        'input[value="Entrar"]',
        'button[type="submit"]',
        'input[type="submit"]',
        '#ctl00_ContentPlaceHolder1_btnIngresar'
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
    "div.search-result"
]

TITLE_CANDIDATES = ["h3", "h2", "h4", "a.title", "a strong", ".titulo", ".title", "a"]
DOWNLOAD_ANCHOR_FILTERS = ["pdf", "word", "docx"]
LABEL_CONCORDANCIAS = ["Concordancia", "Concordancias"]
LABEL_JURIS = ["Jurisprudencia", "Sentencia", "Jurisprudencias", "Sentencias"]

# ================================
# 🔍 UTILIDADES
# ================================
async def _first_selector(page, selectors: List[str]) -> Optional[str]:
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
    try:
        txt = (await root.inner_text()).strip()
        return txt or default
    except Exception:
        return default

def _classify_link_text(texto: str) -> str:
    t = (texto or "").lower()
    if any(k in t for k in DOWNLOAD_ANCHOR_FILTERS):
        return "descarga"
    if any(k.lower() in t for k in LABEL_CONCORDANCIAS):
        return "concordancia"
    if any(k.lower() in t for k in LABEL_JURIS):
        return "jurisprudencia"
    return "otro"

# ================================
# 🔐 LOGIN UNIVERSAL
# ================================
async def _login(page, base_url: str, user: str, password: str) -> None:
    await page.goto(base_url, wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)

    user_sel = await _first_selector(page, LOGIN_SELECTORS["user"])
    pass_sel = await _first_selector(page, LOGIN_SELECTORS["password"])
    subm_sel = await _first_selector(page, LOGIN_SELECTORS["submit"])

    if not (user_sel and pass_sel and subm_sel):
        raise RuntimeError("No se encontraron los campos de login en FielWeb (posible cambio de estructura).")

    await page.fill(user_sel, user)
    await page.fill(pass_sel, password)
    await page.click(subm_sel)

    try:
        await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT_MS)
    except PWTimeout:
        await page.wait_for_timeout(2000)

    still_login = await page.query_selector(subm_sel)
    if still_login:
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
        await page.wait_for_timeout(2000)

    items = []
    for sel in RESULT_ITEM_SELECTORS:
        containers = await page.query_selector_all(sel)
        if containers:
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
                    abs_url = urljoin(page.url, href)
                    if tipo in {"descarga", "concordancia", "jurisprudencia"}:
                        enlaces.append({"tipo": tipo, "texto": text or "enlace", "url": abs_url})
                items.append({"titulo": titulo, "enlaces": enlaces})
            break
    return items

# ================================
# 🚀 FUNCIÓN ASÍNCRONA PRINCIPAL
# ================================
async def _buscar_en_fielweb_async(texto: str) -> Dict[str, Any]:
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
        context = await browser.new_context()
        page = await context.new_page()
        page.set_default_timeout(PAGE_TIMEOUT_MS)

        try:
            await _login(page, FIELWEB_URL, USERNAME, PASSWORD)
            await page.wait_for_timeout(3000)
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
# 🧠 INTERFAZ SINCRÓNICA PARA FASTAPI
# ================================
def consultar_fielweb(payload: Dict[str, Any]) -> Dict[str, Any]:
    texto = (payload.get("texto") or payload.get("consulta") or "").strip()
    if not texto:
        return {"error": "Debe proporcionar un texto de búsqueda en 'texto' o 'consulta'."}

    try:
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
