import asyncio
import re
from playwright.async_api import async_playwright

# ================================
# ⚙️ CONFIGURACIÓN GENERAL
# ================================
URLS = {
    "satje": "https://satje.funcionjudicial.gob.ec/busquedaSentencias.aspx",
    "corte_constitucional": "https://portal.corteconstitucional.gob.ec/FichaRelatoria",
    "corte_nacional": "https://portalcortej.justicia.gob.ec/FichaRelatoria"
}

# ================================
# 🧠 FUNCIÓN GENERAL DE CONSULTA
# ================================
async def buscar_sentencias(texto):
    """
    Realiza búsqueda simultánea en las tres fuentes judiciales (SATJE, Corte Constitucional y Corte Nacional).
    Devuelve resultados estructurados con títulos, descripciones y enlaces.
    """
    resultados_totales = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        # ----------------------------------------
        # 1️⃣ CONSULTA EN SATJE
        # ----------------------------------------
        try:
            await page.goto(URLS["satje"])
            await page.fill("#txtBuscar", texto)
            await page.click("#btnBuscar")
            await page.wait_for_timeout(4000)

            items = await page.query_selector_all(".DataGridItemStyle, .DataGridAlternatingItemStyle")
            for item in items:
                texto_item = await item.inner_text()
                links = await item.query_selector_all("a")
                for l in links:
                    href = await l.get_attribute("href")
                    if href and "Sentencia" in texto_item:
                        resultados_totales.append({
                            "fuente": "SATJE",
                            "titulo": texto_item.split("\n")[0],
                            "descripcion": "Sentencia encontrada en SATJE",
                            "url": href
                        })
        except Exception as e:
            resultados_totales.append({
                "fuente": "SATJE",
                "error": f"No se pudo consultar SATJE: {str(e)}"
            })

        # ----------------------------------------
        # 2️⃣ CONSULTA EN CORTE CONSTITUCIONAL
        # ----------------------------------------
        try:
            await page.goto(URLS["corte_constitucional"])
            await page.fill("#txtPalabraClave", texto)
            await page.click("#btnBuscar")
            await page.wait_for_timeout(4000)

            resultados = await page.query_selector_all(".list-group-item, .panel-body")
            for r in resultados:
                contenido = await r.inner_text()
                links = await r.query_selector_all("a")
                for link in links:
                    href = await link.get_attribute("href")
                    if href:
                        resultados_totales.append({
                            "fuente": "Corte Constitucional",
                            "titulo": contenido.split("\n")[0][:150],
                            "descripcion": "Relatoría constitucional relacionada",
                            "url": href
                        })
        except Exception as e:
            resultados_totales.append({
                "fuente": "Corte Constitucional",
                "error": f"No se pudo consultar Corte Constitucional: {str(e)}"
            })

        # ----------------------------------------
        # 3️⃣ CONSULTA EN CORTE NACIONAL
        # ----------------------------------------
        try:
            await page.goto(URLS["corte_nacional"])
            await page.fill("#txtPalabraClave", texto)
            await page.click("#btnBuscar")
            await page.wait_for_timeout(4000)

            resultados = await page.query_selector_all(".panel-body, .list-group-item")
            for r in resultados:
                texto_r = await r.inner_text()
                links = await r.query_selector_all("a")
                for link in links:
                    href = await link.get_attribute("href")
                    if href:
                        resultados_totales.append({
                            "fuente": "Corte Nacional de Justicia",
                            "titulo": texto_r.split("\n")[0][:150],
                            "descripcion": "Precedente judicial de la Corte Nacional",
                            "url": href
                        })
        except Exception as e:
            resultados_totales.append({
                "fuente": "Corte Nacional de Justicia",
                "error": f"No se pudo consultar Corte Nacional: {str(e)}"
            })

        await browser.close()
        return resultados_totales

# ================================
# ⚙️ INTERFAZ USADA POR FASTAPI
# ================================
def consultar_jurisprudencia(payload: dict):
    """
    Recibe el texto de búsqueda y devuelve resultados consolidados
    de jurisprudencia (SATJE + Corte Constitucional + Corte Nacional).
    """
    texto = payload.get("texto", "").strip()
    if not texto:
        return {"error": "Debe proporcionar un texto de búsqueda para jurisprudencia."}

    try:
        resultados = asyncio.run(buscar_sentencias(texto))
        if not resultados:
            return {
                "mensaje": f"No se encontraron jurisprudencias para '{texto}'.",
                "nivel_consulta": "Jurisprudencia",
                "resultado": []
            }

        return {
            "mensaje": f"Resultados encontrados en fuentes judiciales para '{texto}'.",
            "nivel_consulta": "Jurisprudencia",
            "resultado": resultados
        }

    except Exception as e:
        return {
            "error": f"Ocurrió un error al consultar fuentes judiciales: {str(e)}",
            "nivel_consulta": "Jurisprudencia"
        }
