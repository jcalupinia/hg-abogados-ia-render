import os
import asyncio
from typing import List, Dict, Any, Optional
from urllib.parse import urljoin
from playwright.async_api import async_playwright, TimeoutError as PWTimeout

URLS = {
    "satje": os.getenv("SATJE_URL", "https://satje.funcionjudicial.gob.ec/busquedaSentencias.aspx").strip(),
    "corte_constitucional": os.getenv("CORTE_CONSTITUCIONAL_URL", "https://portal.corteconstitucional.gob.ec/FichaRelatoria").strip(),
    "corte_nacional": os.getenv("CORTE_NACIONAL_URL", "https://portalcortej.justicia.gob.ec/FichaRelatoria").strip(),
}

PAGE_TIMEOUT_MS = 30_000
NAV_TIMEOUT_MS  = 35_000
MAX_ITEMS       = 12

async def _first_selector(page, selectors: List[str]) -> Optional[str]:
    for sel in selectors:
        try:
            if await page.query_selector(sel):
                return sel
        except Exception:
            pass
    return None

async def _inner_text_or(node, default: str = "") -> str:
    try:
        txt = (await node.inner_text()).strip()
        return txt or default
    except Exception:
        return default

def _abs(page_url: str, href: str) -> str:
    try:
        return urljoin(page_url, href or "")
    except Exception:
        return href or ""

def _dedup(items: List[Dict[str, Any]], key: str = "url") -> List[Dict[str, Any]]:
    seen = set()
    out = []
    for it in items:
        val = it.get(key)
        if not val or val in seen:
            continue
        seen.add(val)
        out.append(it)
    return out

# ======================================
# 🚀 FLUJO ASÍNCRONO PRINCIPAL
# ======================================
async def _buscar_juris_async(texto: str) -> Dict[str, Any]:
    if not texto:
        return {"mensaje": "Texto vacío", "nivel_consulta": "Jurisprudencia", "resultado": []}

    launch_args = ["--no-sandbox", "--disable-dev-shm-usage"]
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=launch_args)
        context = await browser.new_context()
        page = await context.new_page()
        page.set_default_timeout(PAGE_TIMEOUT_MS)

        try:
            resultados: List[Dict[str, Any]] = []
            # Aquí puedes agregar las funciones de scraping por fuente
            return {"mensaje": f"Resultados simulados para '{texto}'.", "resultado": resultados}
        finally:
            await context.close()
            await browser.close()

# ======================================
# 🧠 INTERFAZ PÚBLICA PARA FASTAPI
# ======================================
def consultar_jurisprudencia(payload: Dict[str, Any]) -> Dict[str, Any]:
    texto = (payload.get("texto") or payload.get("palabras_clave") or "").strip()
    if not texto:
        return {"error": "Debe proporcionar un texto de búsqueda en 'texto' o 'palabras_clave'."}

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            return loop.run_until_complete(_buscar_juris_async(texto))
        else:
            return asyncio.run(_buscar_juris_async(texto))
    except PWTimeout as te:
        return {"error": f"Tiempo de espera agotado: {str(te)}", "nivel_consulta": "Jurisprudencia"}
    except Exception as e:
        return {"error": f"Ocurrió un error al consultar jurisprudencia: {str(e)}", "nivel_consulta": "Jurisprudencia"}
