import os
import asyncio
import json
from playwright.async_api import async_playwright, TimeoutError as PWTimeout

SESSION_FILE = "/app/session_fielweb.json"
LOGIN_URL = os.getenv("FIELWEB_LOGIN_URL", "https://www.fielweb.com/Cuenta/Login.aspx")
USERNAME = os.getenv("FIELWEB_USERNAME", "consultor@hygabogados.ec")
PASSWORD = os.getenv("FIELWEB_PASSWORD", "")
NAV_TIMEOUT_MS = 35000


async def guardar_sesion(page):
    """Guarda el estado de sesión actual en archivo JSON."""
    state = await page.context.storage_state()
    with open(SESSION_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f)
    print("💾 Sesión guardada correctamente en session_fielweb.json")


async def cargar_o_iniciar_sesion():
    """Carga una sesión existente o inicia sesión nueva si no existe."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        context = None

        # --- Cargar sesión previa si existe ---
        if os.path.exists(SESSION_FILE):
            try:
                context = await browser.new_context(storage_state=SESSION_FILE)
                page = await context.new_page()
                await page.goto(LOGIN_URL, timeout=NAV_TIMEOUT_MS)
                print("✅ Sesión previa cargada correctamente.")
                return page, context
            except Exception as e:
                print(f"⚠️ No se pudo usar la sesión previa ({e}). Se iniciará una nueva sesión.")

        # --- Si no existe, iniciar sesión manualmente ---
        context = await browser.new_context()
        page = await context.new_page()
        await page.goto(LOGIN_URL, timeout=NAV_TIMEOUT_MS)
        print(f"🌐 Accediendo a {LOGIN_URL}...")

        # Campos de login
        await page.fill('#usuario, input[name="usuario"], input[id*="Usuario"]', USERNAME)
        await page.fill('#clave, input[name="clave"], input[type="password"]', PASSWORD)
        await page.click('#btnEntrar, button[type="submit"], input[value="Entrar"]')

        try:
            await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT_MS)
        except PWTimeout:
            print("⏳ Tiempo de carga excedido, pero se continuará.")

        # Guardar nueva sesión
        await guardar_sesion(page)

        print("✅ Sesión nueva autenticada y guardada.")
        return page, context


async def probar_sesion():
    """Verifica la validez actual de la sesión guardada."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        context = await browser.new_context(storage_state=SESSION_FILE if os.path.exists(SESSION_FILE) else None)
        page = await context.new_page()
        try:
            await page.goto(LOGIN_URL, timeout=NAV_TIMEOUT_MS)
            content = await page.content()
            if "Usuario" not in content and "Clave" not in content:
                print("✅ Sesión activa y válida en FielWeb.")
                return True
            else:
                print("⚠️ Sesión expirada o inválida.")
                return False
        finally:
            await context.close()
            await browser.close()


if __name__ == "__main__":
    asyncio.run(cargar_o_iniciar_sesion())
