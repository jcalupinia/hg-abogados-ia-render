import os
import asyncio
import json
import time
from typing import List, Dict, Any
from urllib.parse import urljoin
from playwright.async_api import async_playwright, TimeoutError as PWTimeout

# =========================================
# ⚙️ CONFIGURACIÓN BASE
# =========================================
FIELWEB_URL = os.getenv("FIELWEB_LOGIN_URL", "https://www.fielweb.com/Cuenta/Login.aspx")
USERNAME = os.getenv("FIELWEB_USERNAME")
PASSWORD = os.getenv("FIELWEB_PASSWORD")
SESSION_PATH = "/app/fielweb_session.json"

PAGE_TIMEOUT_MS = 30000
NAV_TIMEOUT_MS = 35000
MAX_ITEMS = 10


# =========================================
# 🧠 FUNCIONES DE UTILIDAD
# =========================================
def session_expired() -> bool:
    """Verifica si la sesión persistente debe regenerarse."""
    try:
        last_mod = os.path.getmtime(SESSION_PATH)
        # Renovar cada 24h (ajustable)
        return (time.time() - last_mod) > 86400
    except FileNotFoundError:
        return True


async def _first_selector(page, selectors: List[str]):
    """Devuelve el primer selector que exista."""
    for sel in selectors:
        el = await page.query_selector(sel)
        if el:
            return sel
    return None


# =========================================
# 🔐 LOGIN MANUAL PARA SESIÓN PERSISTENTE
# =========================================
async def generar_sesion_persistente():
    """Crea una sesión FielWeb y la guarda en JSON (solo se ejecuta si expira)."""
    print("🔄 Generando nueva sesión persistente de FielWeb...")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        context = await browser.new_context()
        page = await context.new_page()

        await page.goto(FIELWEB_URL, wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)

        # Intentar llenar los campos de login
        user_sel = await _first_selector(page, ['#usuario', 'input[name="usuario"]', 'input[id*="Usuario"]'])
        pass_sel = await _first_selector(page, ['#clave', 'input[name="clave"]', 'input[type="password"]'])
        sub_sel = await _first_selector(page, ['#btnEntrar', 'button[type="submit"]', 'input[type="submit"]'])

        if not (user_sel and pass_sel and sub_sel):
            raise RuntimeError("❌ No se encontraron los campos de login en FielWeb.")

        await page.fill(user_sel, USERNAME)
        await page.fill(pass_sel, PASSWORD)
        await page.click(sub_sel)

        try:
            await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT_MS)
        except PWTimeout:
            pass

        # Guardar sesión persistente
        await context.storage_state(path=SESSION_PATH)
        print("✅ Sesión persistente generada correctamente.")
        await context.close()
        await browser.close()


# =========================================
# 🔍 CONSULTA A FIELWEB (CON SESIÓN)
# =========================================
async def _buscar_en_fielweb_async(texto: str) -> Dict[str, Any]:
    if not (USERNAME and PASSWORD):
        raise RuntimeError("❌ Faltan variables de entorno FIELWEB_USERNAME o FIELWEB_PASSWORD")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])

        # Crear contexto con sesión persistente si existe
        if not session_expired() and os.path.exists(SESSION_PATH):
            print("🧩 Usando sesión persistente FielWeb.")
            context = await browser.new_context(storage_state=SESSION_PATH)
        else:
            print("⚠️ Sesión expirada o inexistente. Regenerando...")
            await generar_sesion_persistente()
            context = await browser.new_context(storage_state=SESSION_PATH)

        page = await context.new_page()
        page.set_default_timeout(PAGE_TIMEOUT_MS)

        try:
            await page.goto("https://www.fielweb.com", wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
            await page.wait_for_timeout(2000)

            # Buscar en FielWeb
            search_selectors = ['#ctl00_ContentPlaceHolder1_txtBuscar', 'input[name*="Buscar"]']
            button_selectors = ['#ctl00_ContentPlaceHolder1_btnBuscar', 'button[type="submit"]']

            q_sel = await _first_selector(page, search_selectors)
            b_sel = await _first_selector(page, button_selectors)

            if not (q_sel and b_sel):
                raise RuntimeError("No se encontraron los controles de búsqueda.")

            await page.fill(q_sel, texto)
            await page.click(b_sel)

            try:
                await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT_MS)
            except PWTimeout:
                pass

            items = await page.query_selector_all(".resultadoItem, .card-body, .card, .resultado")

            resultados = []
            for item in items[:MAX_ITEMS]:
                titulo = (await item.inner_text()).strip().split("\n")[0]
                resultados.append({
                    "titulo": titulo,
                    "url": page.url,
                })

            if not resultados:
                return {"mensaje": f"Sin resultados visibles para '{texto}'.", "resultado": []}

            return {
                "mensaje": f"Resultados de FielWeb para '{texto}' obtenidos exitosamente.",
                "nivel_consulta": "FielWeb",
                "resultado": resultados
            }

        except Exception as e:
            if "403" in str(e):
                print("⚠️ Error HTTP 403 detectado. Regenerando sesión...")
                await generar_sesion_persistente()
                return await _buscar_en_fielweb_async(texto)
            raise e
        finally:
            await context.close()
            await browser.close()


# =========================================
# 🧩 INTERFAZ SINCRÓNICA PARA FASTAPI
# =========================================
def consultar_fielweb(payload: Dict[str, Any]) -> Dict[str, Any]:
    texto = (payload.get("texto") or payload.get("consulta") or "").strip()
    if not texto:
        return {"error": "Debe proporcionar un texto de búsqueda en 'texto' o 'consulta'."}

    try:
        return asyncio.run(_buscar_en_fielweb_async(texto))
    except Exception as e:
        return {
            "error": f"Error en FielWeb: {str(e)}",
            "nivel_consulta": "FielWeb"
        }
