import os
import asyncio
from playwright.async_api import async_playwright

# ================================
# ⚙️ CONFIGURACIÓN
# ================================
FIELWEB_URL = os.getenv("FIELWEB_LOGIN_URL", "https://www.fielweb.com/Cuenta/Login.aspx")
USERNAME = os.getenv("FIELWEB_USERNAME")
PASSWORD = os.getenv("FIELWEB_PASSWORD")

# ================================
# 🔍 FUNCIÓN PRINCIPAL DE CONSULTA
# ================================
async def buscar_en_fielweb(texto):
    """
    Inicia sesión en FielWeb, busca el texto indicado y devuelve los resultados,
    incluyendo enlaces a documentos PDF, Word, concordancias y jurisprudencia relacionada.
    """
    resultados = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        # ---- 1️⃣ LOGIN ----
        await page.goto(FIELWEB_URL)
        await page.fill('input[name="ctl00$ContentPlaceHolder1$txtUsuario"]', USERNAME)
        await page.fill('input[name="ctl00$ContentPlaceHolder1$txtClave"]', PASSWORD)
        await page.click('input[id="ctl00_ContentPlaceHolder1_btnIngresar"]')
        await page.wait_for_load_state("networkidle")

        # ---- 2️⃣ BÚSQUEDA ----
        await page.fill('input[id="ctl00_ContentPlaceHolder1_txtBuscar"]', texto)
        await page.click('input[id="ctl00_ContentPlaceHolder1_btnBuscar"]')
        await page.wait_for_load_state("networkidle")

        # ---- 3️⃣ EXTRACCIÓN DE RESULTADOS ----
        filas = await page.query_selector_all(".resultadoItem, .card-body")
        for fila in filas:
            titulo = await fila.inner_text() if fila else "Sin título"
            links = await fila.query_selector_all("a")
            enlaces = []
            for link in links:
                href = await link.get_attribute("href")
                texto_link = await link.inner_text()
                if href and ("pdf" in href or "word" in href or "docx" in href):
                    enlaces.append({"tipo": "descarga", "texto": texto_link, "url": href})
                elif "Concordancia" in texto_link:
                    enlaces.append({"tipo": "concordancia", "texto": texto_link, "url": href})
                elif "Jurisprudencia" in texto_link or "Sentencia" in texto_link:
                    enlaces.append({"tipo": "jurisprudencia", "texto": texto_link, "url": href})
            resultados.append({
                "titulo": titulo.strip(),
                "enlaces": enlaces
            })

        await browser.close()
        return resultados

# ================================
# 🧠 INTERFAZ PÚBLICA USADA POR EL GPT
# ================================
def consultar_fielweb(payload: dict):
    """
    Interfaz sincronizada para FastAPI: recibe el payload, ejecuta la búsqueda
    y devuelve los resultados estructurados.
    """
    texto = payload.get("texto", "").strip()
    if not texto:
        return {"error": "Debe proporcionar un texto de búsqueda."}

    try:
        resultados = asyncio.run(buscar_en_fielweb(texto))
        if not resultados:
            return {
                "mensaje": f"No se encontraron resultados para '{texto}'.",
                "nivel_consulta": "FielWeb",
                "resultado": []
            }

        return {
            "mensaje": f"Resultados encontrados en FielWeb para '{texto}'.",
            "nivel_consulta": "FielWeb",
            "resultado": resultados
        }

    except Exception as e:
        return {
            "error": f"Ocurrió un error al consultar FielWeb: {str(e)}",
            "nivel_consulta": "FielWeb"
        }
