import os
import asyncio
from typing import List, Dict, Any, Optional
from urllib.parse import urljoin, quote
from playwright.async_api import async_playwright, TimeoutError as PWTimeout

# ================================
# ⚙️ CONFIGURACIÓN GLOBAL Y DEBUG
# ================================
DEBUG = os.getenv("DEBUG", "false").lower() == "true"

def debug_log(msg: str):
    if DEBUG:
        print(f"[DEBUG] {msg}")

# ================================
# 🧩 COMPATIBILIDAD CON RENDER
# ================================
def aplicar_nest_asyncio_si_es_necesario():
    """Permite compatibilidad entre Render y entornos locales."""
    try:
        import nest_asyncio
        loop = asyncio.get_event_loop()
        if "uvloop" not in str(type(loop)).lower():
            nest_asyncio.apply()
            debug_log("nest_asyncio aplicado correctamente (modo local).")
        else:
            debug_log("uvloop detectado, no se aplica nest_asyncio (modo Render).")
    except Exception as e:
        print(f"⚠️ No se aplicó nest_asyncio: {e}")

aplicar_nest_asyncio_si_es_necesario()

# ================================
# ⚙️ CONFIGURACIÓN DE ENTORNO
# ================================
URLS = {
    "satje": os.getenv("SATJE_URL", "https://satje.funcionjudicial.gob.ec/busquedaSentencias.aspx").strip(),
    "corte_constitucional": os.getenv("CORTE_CONSTITUCIONAL_URL", "http://buscador.corteconstitucional.gob.ec/buscador-externo/principal").strip(),
    # Se utiliza el buscador nuevo como URL principal de la Corte Nacional
    "corte_nacional": os.getenv("CORTE_NACIONAL_URL", "https://busquedasentencias.cortenacional.gob.ec/").strip(),
    "procesos_judiciales": os.getenv("PROCESOS_JUDICIALES_URL", "https://procesosjudiciales.funcionjudicial.gob.ec/busqueda").strip(),
}

PAGE_TIMEOUT_MS = 30_000
NAV_TIMEOUT_MS  = 35_000
MAX_ITEMS       = 10

# ================================
# Proxy opcional desde entorno
# ================================
def _proxy_config() -> Optional[dict]:
    """
    Construye la configuración de proxy si se definen:
    HTTP_PROXY/HTTPS_PROXY (server) y HTTP_PROXY_USER/HTTP_PROXY_PASS (auth opcional).
    """
    proxy = os.getenv("HTTP_PROXY") or os.getenv("HTTPS_PROXY")
    if not proxy:
        return None
    cfg = {"server": proxy}
    user = os.getenv("HTTP_PROXY_USER")
    pwd = os.getenv("HTTP_PROXY_PASS")
    if user:
        cfg["username"] = user
        if pwd:
            cfg["password"] = pwd
    return cfg

# ================================
# 🔧 UTILIDADES INTERNAS
# ================================
async def _first_selector(page, selectors: List[str]) -> Optional[str]:
    for sel in selectors:
        try:
            if await page.query_selector(sel):
                return sel
        except Exception:
            continue
    return None

async def _safe_inner_text(node, default="") -> str:
    try:
        txt = (await node.inner_text()).strip()
        return txt or default
    except Exception:
        return default

def _abs_url(base: str, href: str) -> str:
    try:
        return urljoin(base, href or "")
    except Exception:
        return href or ""

def _dedup(items: List[Dict[str, Any]], key: str = "url") -> List[Dict[str, Any]]:
    seen, out = set(), []
    for i in items:
        val = i.get(key)
        if val and val not in seen:
            seen.add(val)
            out.append(i)
    return out

async def _click_recaptcha_checkbox(page) -> bool:
    """
    Intenta clicar el checkbox de reCAPTCHA si está presente (no resuelve retos avanzados).
    """
    try:
        iframe = await page.wait_for_selector(
            "iframe[src*='recaptcha'], iframe[title*='reCAPTCHA']", timeout=5000
        )
    except Exception:
        return False

    try:
        frame = await iframe.content_frame()
        if not frame:
            return False
        debug_log("Intentando click en checkbox reCAPTCHA...")
        await frame.click("div.recaptcha-checkbox-border, span.recaptcha-checkbox", timeout=4000)
        try:
            await frame.wait_for_selector(
                "div.recaptcha-checkbox-checked, span[aria-checked='true']", timeout=3000
            )
            debug_log("reCAPTCHA marcado (checkbox en estado checked).")
        except Exception:
            debug_log("No se detectó estado 'checked' en reCAPTCHA (puede requerir reto adicional).")
        await page.wait_for_timeout(1200)
        return True
    except Exception:
        return False

# ================================
# 🔎 FUNCIONES DE BÚSQUEDA
# ================================
async def _buscar_satje(page, texto: str) -> List[Dict[str, Any]]:
    """SATJE – Función Judicial"""
    debug_log(f"Consultando SATJE con: {texto}")
    resultados = []
    await page.goto(URLS["satje"], wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)

    q_sel = await _first_selector(page, ["#txtBuscar", 'input[id*="Buscar"]'])
    b_sel = await _first_selector(page, ["#btnBuscar", 'button[id*="btnBuscar"]'])
    if not q_sel or not b_sel:
        return []

    await page.fill(q_sel, texto)
    await page.click(b_sel)
    try:
        await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT_MS)
    except PWTimeout:
        await page.wait_for_timeout(1500)

    nodes = await page.query_selector_all(".DataGridItemStyle, .card, tr, .resultado")
    for n in nodes[:MAX_ITEMS]:
        txt = await _safe_inner_text(n)
        for a in await n.query_selector_all("a"):
            href = await a.get_attribute("href")
            if href:
                resultados.append({
                    "fuente": "SATJE",
                    "titulo": txt.split("\n")[0][:140],
                    "descripcion": "Sentencia registrada en SATJE",
                    "url": _abs_url(page.url, href)
                })
    return _dedup(resultados)

async def _buscar_corte_constitucional(page, texto: str) -> List[Dict[str, Any]]:
    """Corte Constitucional - buscador externo"""
    debug_log(f"Consultando Corte Constitucional con: {texto}")
    resultados = []
    await page.goto(URLS["corte_constitucional"], wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)

    # Input principal y botón de búsqueda (ícono de lupa)
    q_sel = await _first_selector(page, [
        'input[placeholder*="Digite el texto"]',
        'input[placeholder*="Buscar"]',
        'input[name*="texto"]',
        'input[type="text"]'
    ])
    b_sel = await _first_selector(page, [
        'button:has-text("Buscar")',
        'button[aria-label*="Buscar"]',
        'button[type="submit"]',
        'button:has(svg)'
    ])
    if not q_sel or not b_sel:
        return []

    await page.fill(q_sel, texto[:250])
    await page.click(b_sel)
    try:
        await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT_MS)
    except PWTimeout:
        await page.wait_for_timeout(1500)

    # Tarjetas de resultado: anclas a detalles/PDF
    nodes = await page.query_selector_all("div, article, li, tr")
    for n in nodes[:MAX_ITEMS]:
        txt = await _safe_inner_text(n)
        for a in await n.query_selector_all("a"):
            href = await a.get_attribute("href")
            if href:
                resultados.append({
                    "fuente": "Corte Constitucional",
                    "titulo": txt.split("\n")[0][:140],
                    "descripcion": "Relatoría o sentencia Corte Constitucional",
                    "url": _abs_url(page.url, href)
                })
    return _dedup(resultados)

def _tipo_busqueda_corte_nacional(payload: Dict[str, Any]) -> str:
    """
    Determina el modo de búsqueda: aproximada (default) o por número de proceso.
    """
    modo = (payload.get("tipo_busqueda") or payload.get("modo") or "").lower()
    if "exact" in modo or "frase" in modo:
        return "exacta"
    if "proceso" in modo:
        return "numeroProceso"
    return "aproximada"


async def _buscar_corte_nacional(page, texto: str, payload: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """Corte Nacional - buscador nuevo (busquedasentencias.cortenacional.gob.ec)"""
    debug_log(f"Consultando Corte Nacional (nuevo) con: {texto}")
    resultados = []
    base = URLS["corte_nacional"].rstrip("/")
    query = quote(texto[:50])
    tipo_busqueda = _tipo_busqueda_corte_nacional(payload or {})
    resultados_url = f"{base}/resultados?query={query}&tipoBusqueda={tipo_busqueda}"
    debug_log(f"Corte Nacional: navegando directo a resultados {resultados_url}")
    await page.goto(resultados_url, wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
    try:
        await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT_MS)
        await page.wait_for_selector("app-resultado, a[href*='Proceso'], a[href*='proceso'], a[href*='.pdf'], .card, article, div.result-card", timeout=8000)
        if DEBUG:
            try:
                html_preview = (await page.content())[:1200]
                debug_log(f"Corte Nacional HTML preview: {html_preview}")
            except Exception:
                debug_log("Corte Nacional: no se pudo obtener HTML preview.")
    except PWTimeout:
        await page.wait_for_timeout(1500)

    # Extraer datos en el contexto de la página para capturar campos (proceso, juez, sala, fecha, pdf)
    try:
        raw_cards = await page.evaluate("""
        () => {
            const cards = Array.from(document.querySelectorAll(".resultado-item.card"));
            if (!cards.length) {
                // fallback a otras tarjetas genéricas
                return Array.from(document.querySelectorAll(".card.shadow-sm, .result-card, mat-card, div[role='listitem']")).map(c=>({cardHTML:c.innerHTML}));
            }
            return cards.map(card => {
                const q = (sel) => card.querySelector(sel);
                const qt = (sel) => {
                    const el = q(sel);
                    return el ? (el.textContent || "").trim() : "";
                };
                const qa = (sel) => {
                    const el = q(sel);
                    if (!el) return "";
                    return el.href || el.getAttribute("href") || "";
                };

                const numero = qt("strong.text-truncate, a[href*='Proceso'], a[href*='proceso']");
                const href = qa("a[href*='Proceso'], a[href*='proceso']");

                let pdfHref = qa("a[href$='.pdf'], a[href*='.pdf']");
                if (!pdfHref) {
                    const img = q("img[src*='pdf'], img[alt*='pdf']");
                    if (img) {
                        const a = img.closest("a");
                        if (a) pdfHref = a.href || a.getAttribute("href") || "";
                    }
                }

                const inner = card.innerText || card.textContent || "";
                const juezMatch = inner.match(/Juez\\/a:\\s*([^\\n]+)/i);
                const salaMatch = inner.match(/Sala:\\s*([^\\n]+)/i);
                const fechaMatch = inner.match(/\\d{1,2}\\s+de\\s+\\w+\\s+de\\s+\\d{4}/);

                const descNode = q("p");
                const descripcion = descNode ? (descNode.textContent || "").trim() : inner.trim();

            return {
                numero,
                href,
                pdfHref,
                juez: juezMatch ? juezMatch[1].trim() : qt("span.text-secondary.text-truncate"),
                sala: salaMatch ? salaMatch[1].trim() : (qt("span.text-secondary.text-wrap") || ""),
                fecha: fechaMatch ? fechaMatch[0].trim() : "",
                descripcion
            };
        });
        }
        """)
    except Exception:
        raw_cards = []

    # Intento adicional: extracción directa de tarjetas reales (.resultado-item.card)
    try:
        raw_cards = await page.evaluate("""
        () => {
            const cards = Array.from(document.querySelectorAll(".resultado-item.card"));
            if (!cards.length) return [];
            return cards.map(card => {
                const q = sel => card.querySelector(sel);
                const qt = sel => {
                    const el = q(sel);
                    return el ? (el.textContent || "").trim() : "";
                };

                const numero = qt("strong.text-truncate, a[href*='Proceso'], a[href*='proceso']");
                const inner  = (card.innerText || card.textContent || "").replace(/\\s+/g, " ").trim();
                const juezMatch  = inner.match(/Juez\\/?a?:\\s*([^\\n]+)/i);
                const salaMatch  = inner.match(/Sala:\\s*([^\\n]+)/i);
                const fechaMatch = inner.match(/\\d{1,2}\\s+de\\s+\\w+\\s+de\\s+\\d{4}/);
                const descNode = q("p");

                return {
                    numero,
                    href: "",
                    pdfHref: "",
                    juez: juezMatch ? juezMatch[1].trim() : qt("span.text-secondary.text-truncate"),
                    sala: salaMatch ? salaMatch[1].trim() : (qt("span.text-secondary.text-wrap") || ""),
                    fecha: fechaMatch ? fechaMatch[0].trim() : "",
                    descripcion: descNode ? (descNode.textContent || "").trim() : inner
                };
            });
        }
        """)
    except Exception:
        pass

    if not raw_cards:
        try:
            body_txt = (await page.inner_text("body"))[:400]
            debug_log(f"Corte Nacional: sin nodos de resultado, body preview: {body_txt}")
        except Exception:
            debug_log("Corte Nacional: sin nodos de resultado y no se pudo leer body.")

    for rc in raw_cards:
        numero_proceso = (rc.get("numero") or "").strip()
        href = rc.get("href") or ""
        descripcion = rc.get("descripcion") or ""
        pdf_href = rc.get("pdfHref") or ""
        juez = (rc.get("juez") or "").strip()
        sala = (rc.get("sala") or "").strip()
        fecha = (rc.get("fecha") or "").strip()

        # Fallbacks por regex sobre la descripción
        import re
        if not numero_proceso:
            m = re.search(r"Nro\\s*Proceso\\s*([0-9]+)", descripcion, re.IGNORECASE)
            if m:
                numero_proceso = m.group(1)
            else:
                m2 = re.search(r"(\\d{7,})", descripcion)
                if m2:
                    numero_proceso = m2.group(1)

        if not juez:
            m = re.search(r"Juez/a:\\s*([^\\n]+)", descripcion, re.IGNORECASE)
            if m:
                juez = m.group(1).strip()
        if not sala:
            m = re.search(r"Sala:\\s*([^\\n]+)", descripcion, re.IGNORECASE)
            if m:
                sala = m.group(1).strip()
        if not fecha:
            m = re.search(r"(\\d{1,2}\\s+de\\s+\\w+\\s+de\\s+\\d{4})", descripcion, re.IGNORECASE)
            if m:
                fecha = m.group(1).strip()

        resultados.append({
            "fuente": "Corte Nacional de Justicia (nuevo)",
            "titulo": (numero_proceso or descripcion.split("\\n")[0] if descripcion else "Sentencia Corte Nacional").strip()[:180],
            "descripcion": descripcion.split("\\n")[0][:400],
            "url": _abs_url(page.url, pdf_href or href or page.url),
            "pdf_url": _abs_url(page.url, pdf_href) if pdf_href else None,
            "numero_proceso": numero_proceso.strip(),
            "juez": juez,
            "sala": sala,
            "fecha": fecha
        })
    return _dedup(resultados)


async def _buscar_procesos_judiciales(page, texto: str) -> List[Dict[str, Any]]:
    """Buscador E-SATJE Procesos Judiciales (procesosjudiciales.funcionjudicial.gob.ec/busqueda)"""
    debug_log(f"Consultando Procesos Judiciales con: {texto}")
    resultados = []
    await page.goto(URLS["procesos_judiciales"], wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)

    q_sel = await _first_selector(page, [
        'input[placeholder*="palabras"]',
        'input[placeholder*="Buscar"]',
        'input[id*="form-search"]',
        'input[type="text"]'
    ])
    b_sel = await _first_selector(page, [
        'button[aria-label*="buscar"]',
        'button:has-text("Buscar")',
        'button[type="submit"]',
        'button.mat-primary',
        'button[aria-label*="Buscar"]'
    ])
    if not q_sel:
        return []

    await page.fill(q_sel, texto[:80])
    captcha_clicked = await _click_recaptcha_checkbox(page)
    if b_sel:
        debug_log("Procesos Judiciales: click primer Buscar.")
        await page.click(b_sel)
        if captcha_clicked:
            await page.wait_for_timeout(800)
            debug_log("Procesos Judiciales: click segundo Buscar (post-captcha).")
            await page.click(b_sel)
    else:
        await page.press(q_sel, "Enter")

    try:
        await page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT_MS)
    except PWTimeout:
        await page.wait_for_timeout(1500)

    # Los resultados suelen estar en tarjetas/enlaces; recolectamos anclas visibles
    nodes = await page.query_selector_all("a, .card, .resultado, tr")
    for n in nodes[:MAX_ITEMS]:
        try:
            anchor = await n.query_selector("a") if (await n.query_selector("a")) else n
            href = await anchor.get_attribute("href") if anchor else None
            txt = await _safe_inner_text(n)
            if not txt and not href:
                continue
            resultados.append({
                "fuente": "Procesos Judiciales",
                "titulo": (txt.split("\n")[0] if txt else "Proceso judicial").strip()[:180],
                "descripcion": txt[:200],
                "url": _abs_url(page.url, href) if href else page.url
            })
        except Exception:
            continue
    return _dedup(resultados)

# ================================
# 🚀 FUNCIÓN ASÍNCRONA PRINCIPAL
# ================================
async def _buscar_juris_async(texto: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    if not texto:
        return {"error": "Debe ingresar un texto de búsqueda."}

    launch_args = [
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--disable-gpu",
        "--disable-setuid-sandbox",
        "--disable-web-security"
    ]
    proxy_cfg = _proxy_config()
    if proxy_cfg:
        debug_log(f"Usando proxy: {proxy_cfg.get('server')}")

    debug_log("Lanzando navegador Chromium para consultas judiciales...")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=launch_args, proxy=proxy_cfg)
        context = await browser.new_context()
        page = await context.new_page()
        page.set_default_timeout(PAGE_TIMEOUT_MS)

        resultados = []
        try:
            # Consulta secuencial y controlada
            for fuente, funcion in [
                ("SATJE", _buscar_satje),
                ("Corte Constitucional", _buscar_corte_constitucional),
                ("Corte Nacional de Justicia", lambda p, t=texto: _buscar_corte_nacional(p, t, payload)),
                ("Procesos Judiciales", _buscar_procesos_judiciales),
            ]:
                try:
                    res = await funcion(page, texto)
                    resultados.extend(res)
                except Exception as e:
                    resultados.append({
                        "fuente": fuente,
                        "error": f"No disponible: {e}"
                    })

            resultados = _dedup(resultados)
            return {
                "mensaje": f"Consulta completada para '{texto}'.",
                "nivel_consulta": "Jurisprudencia",
                "resultado": resultados[:MAX_ITEMS]
            }

        finally:
            await context.close()
            await browser.close()
            debug_log("Cierre limpio del navegador Chromium completado.")

# ================================
# ⚙️ UTILIDAD DE EJECUCIÓN BLOQUEANTE
# ================================
def _run_async_blocking(coro):
    """
    Ejecuta la corrutina en un bucle nuevo y aislado para evitar conflictos con uvloop/nest_asyncio.
    """
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)
    finally:
        loop.close()
        asyncio.set_event_loop(None)

# ================================
# 🌐 INTERFACES INDIVIDUALES
# ================================
async def _buscar_fuente_individual(func, texto: str, fuente: str) -> Dict[str, Any]:
    """
    Reutiliza la lógica de navegación para una sola fuente (evita duplicar browsers).
    """
    launch_args = [
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--disable-gpu",
        "--disable-setuid-sandbox",
        "--disable-web-security"
    ]
    proxy_cfg = _proxy_config()
    resultados = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=launch_args, proxy=proxy_cfg)
        context = await browser.new_context()
        page = await context.new_page()
        page.set_default_timeout(PAGE_TIMEOUT_MS)
        try:
            res = await func(page, texto)
            resultados.extend(res)
            resultados = _dedup(resultados)
            return {
                "mensaje": f"Consulta completada para '{texto}'.",
                "nivel_consulta": fuente,
                "resultado": resultados[:MAX_ITEMS]
            }
        finally:
            await context.close()
            await browser.close()
            debug_log("Cierre limpio del navegador Chromium (individual) completado.")

def consultar_corte_nacional(payload: Dict[str, Any]) -> Dict[str, Any]:
    texto = (payload.get("texto") or payload.get("palabras_clave") or "").strip()
    if not texto:
        return {"error": "Debe proporcionar un texto válido para búsqueda.", "nivel_consulta": "Corte Nacional"}
    try:
        return _run_async_blocking(_buscar_fuente_individual(lambda p, t=texto: _buscar_corte_nacional(p, t, payload), texto, "Corte Nacional"))
    except PWTimeout as te:
        return {"error": f"Tiempo de espera agotado: {te}", "nivel_consulta": "Corte Nacional"}
    except Exception as e:
        return {"error": f"Error general al consultar Corte Nacional: {e}", "nivel_consulta": "Corte Nacional"}

def consultar_procesos_judiciales(payload: Dict[str, Any]) -> Dict[str, Any]:
    texto = (payload.get("texto") or payload.get("palabras_clave") or "").strip()
    if not texto:
        return {"error": "Debe proporcionar un texto válido para búsqueda.", "nivel_consulta": "Procesos Judiciales"}
    try:
        return _run_async_blocking(_buscar_fuente_individual(_buscar_procesos_judiciales, texto, "Procesos Judiciales"))
    except PWTimeout as te:
        return {"error": f"Tiempo de espera agotado: {te}", "nivel_consulta": "Procesos Judiciales"}
    except Exception as e:
        return {"error": f"Error general al consultar Procesos Judiciales: {e}", "nivel_consulta": "Procesos Judiciales"}

# ================================
# 🧠 INTERFAZ PÚBLICA PARA FASTAPI
# ================================
def consultar_jurisprudencia(payload: Dict[str, Any]) -> Dict[str, Any]:
    texto = (payload.get("texto") or payload.get("palabras_clave") or "").strip()
    if not texto:
        return {"error": "Debe proporcionar un texto válido para búsqueda."}

    try:
        return _run_async_blocking(_buscar_juris_async(texto, payload))
    except PWTimeout as te:
        return {"error": f"Tiempo de espera agotado: {te}", "nivel_consulta": "Jurisprudencia"}
    except Exception as e:
        return {"error": f"Error general al consultar jurisprudencia: {e}", "nivel_consulta": "Jurisprudencia"}
