# providers/judicial_connectors.py
import asyncio
from typing import Dict, Any, List
from playwright.async_api import async_playwright, TimeoutError as PWTimeout

# ================================
# ⚙️ URLs DE FUENTES JUDICIALES
# ================================
URLS = {
    "satje": "https://satje.funcionjudicial.gob.ec/busquedaSentencias.aspx",
    "corte_constitucional": "https://portal.corteconstitucional.gob.ec/FichaRelatoria",
    "corte_nacional": "https://portalcortej.justicia.gob.ec/FichaRelatoria"
}

PAGE_TIMEOUT_MS = 25_000
NAV_TIMEOUT_MS = 30_000
MAX_RESULTS = 10


# ================================
# 🔍 CONSULTA EN UNA FUENTE
# ================================
async def _buscar_en_fuente(playwright, nombre: str, url: str, texto: str) -> List[Dict[str, Any]]:
    resultados = []
    browser = await playwright.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
    context = await browser.new_context()
    page = await context.new_page()
    page.set_default_timeout(PAGE_TIMEOUT_MS)

    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
        await page.wait_for_timeout(2000)

        # SATJE
        if "satje" in nombre:
            await page.fill("#txtBuscar, input[name='ctl00$ContentPlaceHolder1$txtBuscar']", texto)
            await page.click("#btnBuscar, input[id*='btnBuscar']")
            await page.wait_for_timeout(4000)

            items = await page.query_selector_all(".DataGridItemStyle, .DataGridAlternatingItemStyle")
            for item in items[:MAX_RESULTS]:
                texto_item = (await item.inner_text())[:300]
                links = await item.query_selector_all("a")
                for link in links:
                    href = await link.get_attribute("href")
                    if href:
                        resultados.append({
                            "fuente": "SATJE",
                            "titulo": texto_item.split("\n")[0],
                            "descripcion": "Sentencia o proceso judicial identificado.",
                            "url": href
                        })

        # CORTE CONSTITUCIONAL
        elif "constitucional" in nombre:
            await page.fill("#txtPalabraClave, input[name='PalabraClave']", texto)
            await page.click("#btnBuscar, button[type='submit']")
            await page.wait_for_timeout(4000)

            items = await page.query_selector_all(".list-group-item, .panel-body")
            for item in items[:MAX_RESULTS]:
                contenido = (await item.inner_text())[:300]
                links = await item.query_selector_all("a")
                for link in links:
                    href = await link.get_attribute("href")
                    if href:
                        resultados.append({
                            "fuente": "Corte Constitucional",
                            "titulo": contenido.split("\n")[0],
                            "descripcion": "Relatoría o jurisprudencia constitucional relacionada.",
                            "url": href
                        })

        # CORTE NACIONAL
        elif "nacional" in nombre:
            await page.fill("#txtPalabraClave, input[name='PalabraClave']", texto)
            await page.click("#btnBuscar, button[type='submit']")
            await page.wait_for_timeout(4000)

            items = await page.query_selector_all(".panel-body, .list-group-item")
            for item in items[:MAX_RESULTS]:
                contenido = (await item.inner_text())[:300]
                links = await item.query_selector_all("a")
                for link in links:
                    href = await link.get_attribute("href")
                    if href:
                        resultados.append({
                            "fuente": "Corte Nacional de Justicia",
                            "titulo": contenido.split("\n")[0],
                            "descripcion": "Sentencia o precedente judicial nacional.",
                            "url": href
                        })

    except PWTimeout:
        resultados.append({"fuente": nombre, "error": f"Tiempo de espera agotado en {nombre}"})
    except Exception as e:
        resultados.append({"fuente": nombre, "error": f"Error en {nombre}: {str(e)}"})
    finally:
        await context.close()
        await browser.close()

    return resultados


# ================================
# 🤖 BÚSQUEDA PARALELA
# ================================
async def buscar_sentencias_async(texto: str) -> Dict[str, Any]:
    async with async_playwright() as p:
        tasks = [
            _buscar_en_fuente(p, "satje", URLS["satje"], texto),
            _buscar_en_fuente(p, "corte_constitucional", URLS["corte_constitucional"], texto),
            _buscar_en_fuente(p, "corte_nacional", URLS["corte_nacional"], texto)
        ]
        resultados = await asyncio.gather(*tasks, return_exceptions=True)

    combinados = []
    for r in resultados:
        if isinstance(r, list):
            combinados.extend(r)
        else:
            combinados.append({"error": f"Excepción general: {r}"})

    return {
        "mensaje": f"Consulta completada en fuentes judiciales para '{texto}'.",
        "nivel_consulta": "Jurisprudencia",
        "resultado": combinados
    }


# ================================
# 🧠 INTERFAZ PÚBLICA PARA FASTAPI
# ================================
def consultar_jurisprudencia(payload: dict) -> Dict[str, Any]:
    texto = (payload.get("texto") or "").strip()
    if not texto:
        return {"error": "Debe proporcionar un texto de búsqueda para jurisprudencia."}

    try:
        return asyncio.run(buscar_sentencias_async(texto))
    except Exception as e:
        return {
            "error": f"Ocurrió un error al consultar fuentes judiciales: {str(e)}",
            "nivel_consulta": "Jurisprudencia"
        }
