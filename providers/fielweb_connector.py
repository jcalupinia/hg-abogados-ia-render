import os
import asyncio
from typing import List, Dict, Any, Optional
from urllib.parse import urljoin
from playwright.async_api import async_playwright, TimeoutError as PWTimeout

# ================================
# ⚙️ CONFIGURACIÓN GLOBAL
# ================================
DEBUG = os.getenv("DEBUG", "false").lower() == "true"

def debug_log(msg: str):
    if DEBUG:
        print(f"[DEBUG] {msg}")

# ================================
# 🧩 Compatibilidad con Render
# ================================
def aplicar_nest_asyncio_si_es_necesario():
    """Permite compatibilidad entre Render y entornos locales"""
    try:
        import nest_asyncio
        loop = asyncio.get_event_loop()
        if "uvloop" not in str(type(loop)).lower():
            nest_asyncio.apply()
            debug_log("nest_asyncio aplicado correctamente (modo local).")
        else:
            debug_log("uvloop detectado, no se aplica nest_asyncio (modo Render).")
    except Exception as e:
        print(f"⚠️ No se aplicó nest_asyncio: {e}")

aplicar_nest_asyncio_si_es_necesario()

# ================================
# 🔐 CONFIGURACIÓN DESDE ENTORNO
# ================================
FIELWEB_URL = os.getenv("FIELWEB_LOGIN_URL", "https://www.fielweb.com/Cuenta/Login.aspx").strip()
USERNAME = os.getenv("FIELWEB_USERNAME", "consultor@hygabogados.ec").strip()
PASSWORD = os.getenv("FIELWEB_PASSWORD", "").strip()

PAGE_TIMEOUT_MS = 30_000
NAV_TIMEOUT_MS = 35_000
MAX_ITEMS = 10

# ================================
# Proxy opcional desde entorno
# ================================
def _proxy_config() -> Optional[dict]:
    """
    Construye la configuración de proxy si se definen:
    HTTP_PROXY/HTTPS_PROXY (server) y HTTP_PROXY_USER/HTTP_PROXY_PASS (auth opcional).
    """
    proxy = os.getenv("HTTP_PROXY") or os.getenv("HTTPS_PROXY")
    if not proxy:
        return None
    cfg = {"server": proxy}
    user = os.getenv("HTTP_PROXY_USER")
    pwd = os.getenv("HTTP_PROXY_PASS")
    if user:
        cfg["username"] = user
        if pwd:
            cfg["password"] = pwd
    return cfg

# ================================
# 🔧 SELECTORES ADAPTATIVOS
# ================================
LOGIN_SELECTORS = {
    # Nuevos ids detectados en la pantalla actual de login (fielweb plus) y algunos comodines
    "user": [
        '#username-input', '#usuario',
        'input[name="usuario"]', 'input[placeholder*="Usuario"]', 'input[id*="txtUsuario"]',
        'input[name*="username"]', 'input[id*="username"]', 'input[id*="user"]'
    ],
    "password": [
        '#password-input', '#clave',
        'input[name="clave"]', 'input[placeholder*="Clave"]', 'input[id*="txtClave"]',
        'input[type="password"]', 'input[name*="password"]', 'input[id*="password"]'
    ],
    "submit": [
        '#entrar-button', '#btnEntrar',
        'button:has-text("Entrar")', 'input[value="Entrar"]', 'button[type="submit"]',
        '#ctl00_ContentPlaceHolder1_btnIngresar', 'button[id*="entrar"]'
    ]
}

SEARCH_SELECTORS = {
    "query": ['input[id*="txtBuscar"]', 'input[placeholder*="Buscar"]', 'input[name*="txtBuscar"]'],
    "submit": ['button:has-text("Buscar")', '#ctl00_ContentPlaceHolder1_btnBuscar', 'button[type="submit"]']
}

RESULT_ITEM_SELECTORS = [".resultadoItem", ".card-body", "div.resultado", "div.search-result"]
TITLE_CANDIDATES = ["h3", "h2", "a.title", ".titulo", "a"]
DOWNLOAD_FILTERS = ["pdf", "word", "docx"]
LABEL_CONCORDANCIAS = ["Concordancia", "Concordancias"]
LABEL_JURIS = ["Jurisprudencia", "Sentencia", "Jurisprudencias", "Sentencias"]

# ================================
# 🔍 UTILIDADES INTERNAS
# ================================
async def _first_selector(page, selectors: List[str]) -> Optional[str]:
    for sel in selectors:
        try:
            if await page.query_selector(sel):
                return sel
        except Exception:
            continue
    return None

async def _wait_first_selector(page, selectors: List[str], timeout_ms: int = 4000) -> Optional[str]:
    """
    Espera secuencialmente el primer selector disponible.
    Útil cuando el DOM tarda en construir los campos de login.
    """
    for sel in selectors:
        try:
            await page.wait_for_selector(sel, timeout=timeout_ms, state="visible")
            return sel
        except Exception:
            continue
    return None
def _classify_link(texto: str) -> str:
    t = texto.lower()
    if any(k in t for k in DOWNLOAD_FILTERS): return "descarga"
    if any(k in t for k in LABEL_CONCORDANCIAS): return "concordancia"
    if any(k in t for k in LABEL_JURIS): return "jurisprudencia"
    return "otro"

# ================================
# 🔐 LOGIN UNIVERSAL
# ================================
async def _login(page, url: str, user: str, password: str):
    debug_log(f"Iniciando sesión en {url}")
    resp = await page.goto(url, wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)

    # Si la respuesta es 4xx/5xx, devolvemos un error claro para evitar seguir esperando selectores
    try:
        status = resp.status if resp else None
        if status and status >= 400:
            raise RuntimeError(f"Login FielWeb devolvió HTTP {status} (posible bloqueo/captcha).")
    except Exception:
        pass

    user_sel = await _wait_first_selector(page, LOGIN_SELECTORS["user"])
    pass_sel = await _wait_first_selector(page, LOGIN_SELECTORS["password"])
    subm_sel = await _wait_first_selector(page, LOGIN_SELECTORS["submit"])

    if not all([user_sel, pass_sel, subm_sel]):
        title = ""
        try:
            title = await page.title()
        except Exception:
            title = ""
        raise RuntimeError(f"Campos de login no encontrados (posible cambio en FielWeb). URL={page.url} title='{title}'")

    await page.fill(user_sel, user)
    await page.fill(pass_sel, password)
    await page.click(subm_sel)

    try:
        await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT_MS)
    except PWTimeout:
        debug_log("Timeout leve al iniciar sesión, continuando...")
        await page.wait_for_timeout(2000)

# ================================
# 🔎 BÚSQUEDA Y EXTRACCIÓN
# ================================
async def _buscar(page, texto: str):
    debug_log(f"Buscando en FielWeb: {texto}")
    q_sel = await _first_selector(page, SEARCH_SELECTORS["query"])
    b_sel = await _first_selector(page, SEARCH_SELECTORS["submit"])
    if not all([q_sel, b_sel]):
        raise RuntimeError("No se encontraron los controles de búsqueda.")

    await page.fill(q_sel, texto)
    await page.click(b_sel)
    try:
        await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT_MS)
    except PWTimeout:
        await page.wait_for_timeout(2000)

    resultados = []
    for sel in RESULT_ITEM_SELECTORS:
        nodes = await page.query_selector_all(sel)
        if nodes:
            for node in nodes[:MAX_ITEMS]:
                title = (await node.inner_text()).split("\n")[0].strip()
                links = await node.query_selector_all("a")
                enlaces = []
                for a in links:
                    href = (await a.get_attribute("href")) or ""
                    text = (await a.inner_text()) or ""
                    tipo = _classify_link(text)
                    if href:
                        enlaces.append({
                            "tipo": tipo,
                            "texto": text.strip() or "enlace",
                            "url": urljoin(page.url, href)
                        })
                resultados.append({"titulo": title, "enlaces": enlaces})
            break
    return resultados

# ================================
# 🚀 CONSULTA PRINCIPAL ASÍNCRONA
# ================================
async def _buscar_en_fielweb_async(texto: str) -> Dict[str, Any]:
    if not all([FIELWEB_URL, USERNAME, PASSWORD]):
        raise RuntimeError("Faltan variables de entorno para FielWeb (URL, usuario o contraseña).")

    # Configuración del navegador compatible con Render
    launch_args = [
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--disable-gpu",
        "--disable-setuid-sandbox",
        "--disable-web-security"
    ]

    proxy_cfg = _proxy_config()
    if proxy_cfg:
        debug_log(f"Usando proxy: {proxy_cfg.get('server')}")

    debug_log("Lanzando navegador Playwright Chromium...")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=launch_args, proxy=proxy_cfg)
        context = await browser.new_context()
        page = await context.new_page()
        page.set_default_timeout(PAGE_TIMEOUT_MS)

        try:
            await _login(page, FIELWEB_URL, USERNAME, PASSWORD)
            await page.wait_for_timeout(2500)
            data = await _buscar(page, texto)
            return {"mensaje": f"Resultados para '{texto}'", "nivel_consulta": "FielWeb", "resultado": data}
        except Exception as e:
            return {"error": f"Error interno en la búsqueda: {e}", "nivel_consulta": "FielWeb"}
        finally:
            await context.close()
            await browser.close()
            debug_log("Chromium cerrado correctamente.")

# ================================
# ⚙️ UTILIDAD DE EJECUCIÓN BLOQUEANTE
# ================================
def _run_async_blocking(coro):
    """
    Ejecuta la corrutina en un bucle nuevo y aislado para evitar conflictos con uvloop/nest_asyncio.
    """
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)
    finally:
        loop.close()
        asyncio.set_event_loop(None)

# ================================
# 🧠 INTERFAZ SINCRÓNICA PARA FASTAPI
# ================================
def consultar_fielweb(payload: Dict[str, Any]) -> Dict[str, Any]:
    texto = (payload.get("texto") or payload.get("consulta") or "").strip()
    if not texto:
        return {"error": "Debe proporcionar un texto de búsqueda en 'texto' o 'consulta'."}

    try:
        return _run_async_blocking(_buscar_en_fielweb_async(texto))
    except PWTimeout as te:
        return {"error": f"Tiempo de espera agotado: {te}", "nivel_consulta": "FielWeb"}
    except Exception as e:
        return {"error": f"Error general al consultar FielWeb: {e}", "nivel_consulta": "FielWeb"}
