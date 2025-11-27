import os
import asyncio
from typing import List, Dict, Any, Optional
from urllib.parse import urljoin
from playwright.async_api import async_playwright, TimeoutError as PWTimeout

# ================================
# ⚙️ CONFIGURACIÓN GLOBAL Y DEBUG
# ================================
DEBUG = os.getenv("DEBUG", "false").lower() == "true"

def debug_log(msg: str):
    if DEBUG:
        print(f"[DEBUG] {msg}")

# ================================
# 🧩 COMPATIBILIDAD CON RENDER
# ================================
def aplicar_nest_asyncio_si_es_necesario():
    """Permite compatibilidad entre Render y entornos locales."""
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
# ⚙️ CONFIGURACIÓN DE ENTORNO
# ================================
URLS = {
    "satje": os.getenv("SATJE_URL", "https://satje.funcionjudicial.gob.ec/busquedaSentencias.aspx").strip(),
    "corte_constitucional": os.getenv("CORTE_CONSTITUCIONAL_URL", "https://portal.corteconstitucional.gob.ec/FichaRelatoria").strip(),
    # Se utiliza el buscador nuevo como URL principal de la Corte Nacional
    "corte_nacional": os.getenv("CORTE_NACIONAL_URL", "https://busquedasentencias.cortenacional.gob.ec/").strip(),
}

PAGE_TIMEOUT_MS = 30_000
NAV_TIMEOUT_MS  = 35_000
MAX_ITEMS       = 10

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
# 🔧 UTILIDADES INTERNAS
# ================================
async def _first_selector(page, selectors: List[str]) -> Optional[str]:
    for sel in selectors:
        try:
            if await page.query_selector(sel):
                return sel
        except Exception:
            continue
    return None

async def _safe_inner_text(node, default="") -> str:
    try:
        txt = (await node.inner_text()).strip()
        return txt or default
    except Exception:
        return default

def _abs_url(base: str, href: str) -> str:
    try:
        return urljoin(base, href or "")
    except Exception:
        return href or ""

def _dedup(items: List[Dict[str, Any]], key: str = "url") -> List[Dict[str, Any]]:
    seen, out = set(), []
    for i in items:
        val = i.get(key)
        if val and val not in seen:
            seen.add(val)
            out.append(i)
    return out

# ================================
# 🔎 FUNCIONES DE BÚSQUEDA
# ================================
async def _buscar_satje(page, texto: str) -> List[Dict[str, Any]]:
    """SATJE – Función Judicial"""
    debug_log(f"Consultando SATJE con: {texto}")
    resultados = []
    await page.goto(URLS["satje"], wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)

    q_sel = await _first_selector(page, ["#txtBuscar", 'input[id*="Buscar"]'])
    b_sel = await _first_selector(page, ["#btnBuscar", 'button[id*="btnBuscar"]'])
    if not q_sel or not b_sel:
        return []

    await page.fill(q_sel, texto)
    await page.click(b_sel)
    try:
        await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT_MS)
    except PWTimeout:
        await page.wait_for_timeout(1500)

    nodes = await page.query_selector_all(".DataGridItemStyle, .card, tr, .resultado")
    for n in nodes[:MAX_ITEMS]:
        txt = await _safe_inner_text(n)
        for a in await n.query_selector_all("a"):
            href = await a.get_attribute("href")
            if href:
                resultados.append({
                    "fuente": "SATJE",
                    "titulo": txt.split("\n")[0][:140],
                    "descripcion": "Sentencia registrada en SATJE",
                    "url": _abs_url(page.url, href)
                })
    return _dedup(resultados)

async def _buscar_corte_constitucional(page, texto: str) -> List[Dict[str, Any]]:
    """Corte Constitucional"""
    debug_log(f"Consultando Corte Constitucional con: {texto}")
    resultados = []
    await page.goto(URLS["corte_constitucional"], wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)

    q_sel = await _first_selector(page, ["#txtPalabraClave", 'input[id*="Palabra"]'])
    b_sel = await _first_selector(page, ["#btnBuscar", 'button[id*="btnBuscar"]'])
    if not q_sel or not b_sel:
        return []

    await page.fill(q_sel, texto)
    await page.click(b_sel)
    try:
        await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT_MS)
    except PWTimeout:
        await page.wait_for_timeout(1500)

    nodes = await page.query_selector_all(".list-group-item, .panel-body, tr, .resultado")
    for n in nodes[:MAX_ITEMS]:
        txt = await _safe_inner_text(n)
        for a in await n.query_selector_all("a"):
            href = await a.get_attribute("href")
            if href:
                resultados.append({
                    "fuente": "Corte Constitucional",
                    "titulo": txt.split("\n")[0][:140],
                    "descripcion": "Relatoría Constitucional",
                    "url": _abs_url(page.url, href)
                })
    return _dedup(resultados)

async def _buscar_corte_nacional(page, texto: str) -> List[Dict[str, Any]]:
    """Corte Nacional - buscador nuevo (busquedasentencias.cortenacional.gob.ec)"""
    debug_log(f"Consultando Corte Nacional (nuevo) con: {texto}")
    resultados = []
    await page.goto(URLS["corte_nacional"], wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)

    q_sel = await _first_selector(page, [
        'input[placeholder*="Digite"]',
        'input[placeholder*="Buscar"]',
        'input[type="text"]'
    ])
    b_sel = await _first_selector(page, ['button:has-text("Buscar")', 'button[type="submit"]'])
    if not q_sel or not b_sel:
        return []

    await page.fill(q_sel, texto[:50])
    await page.click(b_sel)
    try:
        await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT_MS)
    except PWTimeout:
        await page.wait_for_timeout(1500)

    cards = await page.query_selector_all("div, article, li")
    for card in cards:
        try:
            anchor = await card.query_selector('a[href*="Proceso"], a[href*="proceso"], a[href*=".pdf"], a')
            if not anchor:
                continue
            href = await anchor.get_attribute("href")
            if not href:
                continue
            titulo = (await anchor.inner_text()) or ""
            descripcion = await _safe_inner_text(card, "")

            pdf_link = await card.query_selector('a[href$=".pdf"], a[href*=".pdf"]')
            if pdf_link:
                pdf_href = await pdf_link.get_attribute("href")
            else:
                pdf_href = None

            resultados.append({
                "fuente": "Corte Nacional de Justicia (nuevo)",
                "titulo": titulo.strip()[:180] or "Sentencia Corte Nacional",
                "descripcion": descripcion.split("\n")[0][:200],
                "url": _abs_url(page.url, pdf_href or href)
            })
        except Exception:
            continue
    return _dedup(resultados)

# ================================
# 🚀 FUNCIÓN ASÍNCRONA PRINCIPAL
# ================================
async def _buscar_juris_async(texto: str) -> Dict[str, Any]:
    if not texto:
        return {"error": "Debe ingresar un texto de búsqueda."}

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

    debug_log("Lanzando navegador Chromium para consultas judiciales...")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=launch_args, proxy=proxy_cfg)
        context = await browser.new_context()
        page = await context.new_page()
        page.set_default_timeout(PAGE_TIMEOUT_MS)

        resultados = []
        try:
            # Consulta secuencial y controlada
            for fuente, funcion in [
                ("SATJE", _buscar_satje),
                ("Corte Constitucional", _buscar_corte_constitucional),
                ("Corte Nacional de Justicia", _buscar_corte_nacional),
            ]:
                try:
                    res = await funcion(page, texto)
                    resultados.extend(res)
                except Exception as e:
                    resultados.append({
                        "fuente": fuente,
                        "error": f"No disponible: {e}"
                    })

            resultados = _dedup(resultados)
            return {
                "mensaje": f"Consulta completada para '{texto}'.",
                "nivel_consulta": "Jurisprudencia",
                "resultado": resultados[:MAX_ITEMS]
            }

        finally:
            await context.close()
            await browser.close()
            debug_log("Cierre limpio del navegador Chromium completado.")

# ================================
# 🧠 INTERFAZ PÚBLICA PARA FASTAPI
# ================================
def consultar_jurisprudencia(payload: Dict[str, Any]) -> Dict[str, Any]:
    texto = (payload.get("texto") or payload.get("palabras_clave") or "").strip()
    if not texto:
        return {"error": "Debe proporcionar un texto válido para búsqueda."}

    try:
        return asyncio.run(_buscar_juris_async(texto))
    except PWTimeout as te:
        return {"error": f"Tiempo de espera agotado: {te}", "nivel_consulta": "Jurisprudencia"}
    except Exception as e:
        return {"error": f"Error general al consultar jurisprudencia: {e}", "nivel_consulta": "Jurisprudencia"}
