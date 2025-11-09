import os
import asyncio
from playwright.async_api import async_playwright

# Función principal del conector FielWeb
async def _consultar_fielweb_async(payload: dict):
    """
    Automatiza la búsqueda en FielWeb:
    1️⃣ Inicia sesión.
    2️⃣ Busca el texto indicado.
    3️⃣ Extrae los enlaces de descarga disponibles (PDF, Word, Concordancias, Jurisprudencia).
    4️⃣ Devuelve los resultados en formato JSON.
    """
    username = os.getenv("FIELWEB_USERNAME")
    password = os.getenv("FIELWEB_PASSWORD")
    login_url = os.getenv("FIELWEB_LOGIN_URL", "https://www.fielweb.com/Cuenta/Login.aspx")

    consulta = payload.get("texto", "").strip()
    if not consulta:
        return {"estado": "error", "mensaje": "Debe indicar un texto de búsqueda."}

    resultados = []

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context()
            page = await context.new_page()

            # 1️⃣ Ir a la página de login
            await page.goto(login_url, timeout=60000)
            await page.fill('input[name="ctl00$ContentPlaceHolder1$txtUsuario"]', username)
            await page.fill('input[name="ctl00$ContentPlaceHolder1$txtClave"]', password)
            await page.click('input[id="ctl00_ContentPlaceHolder1_btnIngresar"]')
            await page.wait_for_load_state("networkidle")

            print("✅ Sesión iniciada en FielWeb")

            # 2️⃣ Ir al módulo de búsqueda
            await page.goto("https://www.fielweb.com/ConsultaGeneral.aspx", timeout=60000)
            await page.fill('input[id="ctl00_ContentPlaceHolder1_txtBuscar"]', consulta)
            await page.click('input[id="ctl00_ContentPlaceHolder1_btnBuscar"]')
            await page.wait_for_load_state("networkidle")

            # 3️⃣ Extraer resultados
            links = await page.query_selector_all("a[href]")
            for link in links:
                href = await link.get_attribute("href")
                texto = (await link.inner_text()).strip()

                if not href:
                    continue

                # Detectar enlaces de descarga y concordancias
                if any(word in href.lower() for word in ["pdf", "doc", "descargar", "concordancia", "jurisprudencia"]):
                    resultado = {
                        "titulo": texto or "Documento legal",
                        "url": f"https://www.fielweb.com/{href}" if href.startswith("Archivos") else href
                    }
                    resultados.append(resultado)
                    print(f"📄 Enlace detectado: {resultado['titulo']} -> {resultado['url']}")

            await browser.close()

            if not resultados:
                return {
                    "estado": "sin_resultados",
                    "mensaje": f"No se encontraron enlaces de descarga para: {consulta}"
                }

            return {
                "estado": "éxito",
                "mensaje": f"Se encontraron {len(resultados)} resultados en FielWeb.",
                "busqueda": consulta,
                "resultados": resultados
            }

    except Exception as e:
        print(f"❌ Error en FielWeb: {str(e)}")
        return {"estado": "error", "detalle": str(e)}

# Función síncrona compatible con FastAPI
def consultar_fielweb(payload: dict):
    return asyncio.run(_consultar_fielweb_async(payload))
