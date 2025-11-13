import os
import asyncio
from typing import List, Dict, Any, Optional
from urllib.parse import urljoin
from playwright.async_api import async_playwright, TimeoutError as PWTimeout

# =====================================================
# ⚙️ CONFIGURACIÓN GLOBAL Y CONSTANTES
# =====================================================
URLS = {
    "satje": os.getenv("SATJE_URL", "https://satje.funcionjudicial.gob.ec/busquedaSentencias.aspx").strip(),
    "corte_constitucional": os.getenv("CORTE_CONSTITUCIONAL_URL", "https://portal.corteconstitucional.gob.ec/FichaRelatoria").strip(),
    "corte_nacional": os.getenv("CORTE_NACIONAL_URL", "https://portalcortej.justicia.gob.ec/FichaRelatoria").strip(),
}

PAGE_TIMEOUT_MS = 30_000
NAV_TIMEOUT_MS = 35_000
MAX_ITEMS = 12

# =====================================================
# 🔧 FUNCIONES AUXILIARES
# =====================================================
async def _first_selector(page, selectors: List[str]) -> Optional[str]:
    """Devuelve el primer selector que existe en la página."""
    for sel in selectors:
        try:
            if await page.query_selector(sel):
                return sel
        except Exception:
            continue
    return None


async def _inner_text_or(node, default: str = "") -> str:
    """Extrae texto interno de un nodo o devuelve valor por defecto."""
    try:
        txt = (await node.inner_text()).strip()
        return txt or default
    except Exception:
        return default


def _abs(page_url: str, href: str) -> str:
    """Construye una URL absoluta segura."""
    try:
        return urljoin(page_url, href or "")
    except Exception:
        return href or ""


def _dedup(items: List[Dict[str, Any]], key: str = "url") -> List[Dict[str, Any]]:
    """Elimina duplicados en base a la URL."""
    seen = set()
    result = []
    for it in items:
        val = it.get(key)
        if not val or val in seen:
            continue
        seen.add(val)
        result.append(it)
    return result

# =====================================================
# 🔍 MÓDULOS DE BÚSQUEDA POR FUENTE
# =====================================================
async def _buscar_satje(page, texto: str) -> List[Dict[str, Any]]:
    resultados: List[Dict[str, Any]] = []
    await page.goto(URLS["satje"], wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)

    q_sel = await _first_selector(page, ["#txtBuscar", 'input[id*="txtBuscar"]', 'input[placeholder*="Buscar"]', 'input[type="search"]'])
    b_sel = await _first_selector(page, ["#btnBuscar", 'button[id*="btnBuscar"]', 'button:has-text("Buscar")'])
    if not (q_sel and b_sel):
        return resultados

    await page.fill(q_sel, texto)
    await page.click(b_sel)

    try:
        await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT_MS)
    except PWTimeout:
        await page.wait_for_timeout(1500)

    for sel in [".DataGridItemStyle", ".DataGridAlternatingItemStyle", "table tr", ".resultado", ".card"]:
        nodes = await page.query_selector_all(sel)
        if nodes:
            for row in nodes[:MAX_ITEMS]:
                txt = await _inner_text_or(row, "")
                for a in await row.query_selector_all("a"):
                    href = await a.get_attribute("href")
                    if not href:
                        continue
                    resultados.append({
                        "fuente": "SATJE",
                        "titulo": txt.split("\n")[0][:160] if txt else "Sentencia SATJE",
                        "descripcion": "Sentencia o acto judicial encontrado en SATJE.",
                        "url": _abs(page.url, href)
                    })
            break

    return _dedup(resultados)


async def _buscar_corte_constitucional(page, texto: str) -> List[Dict[str, Any]]:
    resultados: List[Dict[str, Any]] = []
    await page.goto(URLS["corte_constitucional"], wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)

    q_sel = await _first_selector(page, ["#txtPalabraClave", 'input[id*="Palabra"]', 'input[placeholder*="Palabra"*]()*]()]()_
