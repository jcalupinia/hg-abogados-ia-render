import os
import asyncio
from typing import List, Dict, Any, Optional
from urllib.parse import urljoin
from playwright.async_api import async_playwright, TimeoutError as PWTimeout

# ======================================
# ⚙️ CONFIGURACIÓN Y CONSTANTES
# ======================================
URLS = {
    "satje": os.getenv("SATJE_URL", "https://satje.funcionjudicial.gob.ec/busquedaSentencias.aspx").strip(),
    "corte_constitucional": os.getenv("CORTE_CONSTITUCIONAL_URL", "https://portal.corteconstitucional.gob.ec/FichaRelatoria").strip(),
    "corte_nacional": os.getenv("CORTE_NACIONAL_URL", "https://portalcortej.justicia.gob.ec/FichaRelatoria").strip(),
}

PAGE_TIMEOUT_MS = 30_000
NAV_TIMEOUT_MS = 35_000
MAX_ITEMS = 12

# ======================================
# 🔧 FUNCIONES AUXILIARES
# ======================================
async def _first_selector(page, selectors: List[str]) -> Optional[str]:
    for sel in selectors:
        try:
            if await page.query_selector(sel):
                return sel
        except Exception:
            continue
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
    result = []
    for it in items:
        val = it.get(key)
        if not val or val in seen:
            continue
        seen.add(val)
        result.append(it)
    return result

# ======================================
# 🔍 BUSCADORES POR FUENTE
# ======================================
async def _buscar_satje(page, texto: str) -> List[Dict[str, Any]]:
    resultados: List[Dict[str, Any]] = []
    await page.goto(URLS["satje"], wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)

    q_sel = await _first_selector(page, [
        '#txtBuscar', 'input[id*="txtBuscar"]', 'input[placeholder*="Buscar"]', 'input[type="search"]'
    ])
    b_sel = await _first_selector(page, [
        '#btnBuscar', 'input[id*="btnBuscar"]', 'button[id*="btnBuscar"]', 'button:has-text("Buscar")'
    ])
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
                        "titulo": (txt.split("\n")[0] if txt else "Sentencia SATJE").strip()[:160],
                        "descripcion": "Sentencia o acto judicial encontrado en SATJE.",
                        "url": _abs(page.url, href),
                    })
            break

    return _dedup(resultados)


async def _buscar_corte_constitucional(page, texto: str) -> List[Dict[str, Any]]:
    resultados: List[Dict[str, Any]] = []
    await page.goto(URLS["corte_constitucional"], wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)

    q_sel = await _first_selector(page, [
        '#txtPalabraClave', 'input[id*="Palabra"]', 'input[placeholder*="Palabra"]', 'input[type="search"]'
    ])
    b_sel = await _first_selector(page, [
        '#btnBuscar', 'input[id*="btnBuscar"]', 'button[id*="btnBuscar"]', 'button:has-text("Buscar")'
    ])
    if not (q_sel and b_sel):
        return resultados

    await page.fill(q_sel, texto)
    await page.click(b_sel)

    try:
        await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT_MS)
    except PWTimeout:
        await page.wait_for_timeout(1500)

    for sel in [".list-group-item", ".panel-body", ".card", ".resultado", "table tr"]:
        nodes = await page.query_selector_all(sel)
        if nodes:
            for c in nodes[:MAX_ITEMS]:
                txt = await _inner_text_or(c, "")
                for a in await c.query_selector_all("a"):
                    href = await a.get_attribute("href")
                    if not href:
                        continue
                    resultados.append({
                        "fuente": "Corte Constitucional",
                        "titulo": (txt.split("\n")[0] if txt else "Relatoría Constitucional").strip()[:160],
                        "descripcion": "Registro de sentencia o relatoría en la Corte Constitucional.",
                        "url": _abs(page.url, href),
                    })
            break

    return _dedup(resultados)


async def _buscar_corte_nacional(page, texto: str) -> List[Dict[str, Any]]:
    resultados: List[Dict[str, Any]] = []
    await page.goto(URLS["corte_nacional"], wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)

    q_sel = await _first_selector(page, [
        '#txtPalabraClave', 'input[id*="Palabra"]', 'input[placeholder*="Palabra"]', 'input[type="search"]'
    ])
    b_sel = await _first_selector(page, [
        '#btnBuscar', 'input[id*="btnBuscar"]', 'button[id*="btnBuscar"]', 'button:has-text("Buscar")'
    ])
    if not (q_sel and b_sel):
        return resultados

    await page.fill(q_sel, texto)
    await page.click(b_sel)

    try:
        await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT_MS)
    except PWTimeout:
        await page.wait_for_timeout(1500)

    for sel in [".panel-body", ".list-group-item", ".card", ".resultado", "table tr"]:
        nodes = await page.query_selector_all(sel)
        if nodes:
            for b in nodes[:MAX_ITEMS]:
                txt = await _inner_text_or(b, "")
                for a in await b.query_selector_all("a"):
                    href = await a.get_attribute("href")
                    if not href:
                        continue
                    resultados.append({
                        "fuente": "Corte Nacional de Justicia",
                        "titulo": (txt.split("\n")[0] if txt else "Precedente de la Corte Nacional").strip()[:160],
                        "descripcion": "Precedente judicial o relatoría de la Corte Nacional de Justicia.",
                        "url": _abs(page.url, href),
                    })
            break

    return _dedup(resultados)

# ======================================
# 🚀 FLUJO PRINCIPAL ASÍNCRONO
# ======================================
async def _buscar_juris_async(texto: str) -> Dict[str, Any]:
    if not texto:
        return {"mensaje": "Texto vacío", "nivel_consulta": "Jurisprudencia", "resultado": []}

    launch_args = ["--no-sandbox", "--disable-dev-shm-usage"]

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=launch_args)
        context = await browser.new_context(
            user_agent=("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/121.0 Safari/537.36"),
            accept_downloads=False
        )
        page = await context.new_page()
        page.set_default_timeout(PAGE_TIMEOUT_MS)

        try:
            resultados: List[Dict[str, Any]] = []

            # SATJE
            try:
                resultados += await _buscar_satje(page, texto)
            except Exception as e:
                resultados.append({"fuente": "SATJE", "error": f"No disponible: {str(e)}"})

            # Corte Constitucional
            try:
                resultados += await _buscar_corte_constitucional(page, texto)
            except Exception as e:
                resultados.append({"fuente": "Corte Constitucional", "error": f"No disponible: {str(e)}"})

            # Corte Nacional
            try:
                resultados += await _buscar_corte_nacional(page, texto)
            except Exception as e:
                resultados.append({"fuente": "Corte Nacional de Justicia", "error": f"No disponible: {str(e)}"})

            resultados = _dedup(resultados, key="url")

            return {
                "mensaje": f"Resultados de jurisprudencia para '{texto}'.",
                "nivel_consulta": "Jurisprudencia",
                "resultado": resultados[:MAX_ITEMS]
            }

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
        return asyncio.run(_buscar_juris_async(texto))
    except PWTimeout as te:
        return {"error": f"Tiempo de espera agotado: {str(te)}", "nivel_consulta": "Jurisprudencia"}
    except Exception as e:
        return {"error": f"Ocurrió un error al consultar jurisprudencia: {str(e)}", "nivel_consulta": "Jurisprudencia"}
