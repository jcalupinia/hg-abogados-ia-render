import os
import asyncio
from typing import List, Dict, Any
from urllib.parse import urljoin
from playwright.async_api import async_playwright, TimeoutError as PWTimeout

# ================================
# ⚙️ CONFIGURACIÓN GLOBAL
# ================================
PAGE_TIMEOUT_MS = 30_000
NAV_TIMEOUT_MS = 35_000
MAX_ITEMS = 12

URLS = {
    "satje": os.getenv("SATJE_URL", "https://satje.funcionjudicial.gob.ec/busquedaSentencias.aspx").strip(),
    "corte_constitucional": os.getenv("CORTE_CONSTITUCIONAL_URL", "https://portal.corteconstitucional.gob.ec/FichaRelatoria").strip(),
    "corte_nacional": os.getenv("CORTE_NACIONAL_URL", "https://portalcortej.justicia.gob.ec/FichaRelatoria").strip(),
}

# ================================
# 🔍 BÚSQUEDA ASÍNCRONA PRINCIPAL
# ================================
async def _buscar_juris_async(texto: str) -> Dict[str, Any]:
    """
    Realiza una consulta básica (simulada o real) en portales judiciales.
    Adaptable para integración posterior con scraping o APIs reales.
    """
    if not texto:
        return {
            "mensaje": "Texto vacío o inválido.",
            "nivel_consulta": "Jurisprudencia",
            "resultado": []
        }

    launch_args = ["--no-sandbox", "--disable-dev-shm-usage"]

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=launch_args)
        context = await browser.new_context()
        page = await context.new_page()
        page.set_default_timeout(PAGE_TIMEOUT_MS)

        try:
            await page.goto(URLS["satje"], wait_until="domcontentloaded")
            # 🔹 Aquí puedes extender el scraping para portales oficiales.
            return {
                "mensaje": f"Consulta simulada de jurisprudencia para '{texto}'.",
                "nivel_consulta": "Jurisprudencia",
                "resultado": []
            }

        except PWTimeout:
            return {
                "error": f"Tiempo de espera agotado al intentar acceder a {URLS['satje']}.",
                "nivel_consulta": "Jurisprudencia"
            }

        except Exception as e:
            return {
                "error": f"Error inesperado al consultar jurisprudencia: {str(e)}",
                "nivel_consulta": "Jurisprudencia"
            }

        finally:
            await context.close()
            await browser.close()

# ================================
# 🧠 INTERFAZ SINCRÓNICA PARA FASTAPI
# ================================
def consultar_jurisprudencia(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Interfaz directa para FastAPI (llamada desde main.py).
    Gestiona automáticamente el bucle de eventos y errores.
    """
    texto = (payload.get("texto") or payload.get("palabras_clave") or "").strip()

    if not texto:
        return {
            "error": "Debe proporcionar un texto de búsqueda en 'texto' o 'palabras_clave'.",
            "nivel_consulta": "Jurisprudencia"
        }

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Render usa un loop activo, manejarlo con coroutine segura
            return asyncio.run_coroutine_threadsafe(_buscar_juris_async(texto), loop).result()
        else:
            return loop.run_until_complete(_buscar_juris_async(texto))

    except PWTimeout as te:
        return {
            "error": f"Tiempo de espera agotado: {str(te)}",
            "nivel_consulta": "Jurisprudencia"
        }

    except Exception as e:
        return {
            "error": f"Ocurrió un error al consultar jurisprudencia: {str(e)}",
            "nivel_consulta": "Jurisprudencia"
        }
